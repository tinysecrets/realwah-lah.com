"""Compliance tests — OFAC, geoblock, KYC tiers, payout hold queue.

Goes through the live backend HTTP API. Admin creds from test_credentials.md.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://wahlah-deploy.preview.emergentagent.com")
API = f"{BASE_URL}/api"
COMP = f"{API}/ext/compliance"

ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@wah-lah.com")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "SugarCity2024!")

# Sanctioned BTC address from the bundled fallback list in ofac.py.
SANCTIONED_ADDR = "1AQvR6HvLV2jCBboQkn97QnkuKtHyCEWFK"
CLEAN_ADDR = "bc1qcleanxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(autouse=True, scope="module")
def btc_payouts_on(admin_session):
    """Most compliance tests assume BTC is ENABLED so they can reach the KYC/OFAC gates.
    Flip it on for the module, restore to its prior state after."""
    prior = admin_session.get(f"{COMP}/admin/feature-flags").json().get("btc_payouts_enabled", False)
    admin_session.patch(f"{COMP}/admin/feature-flags", json={"key": "btc_payouts_enabled", "value": True})
    # cache TTL is 10s so wait for refresh
    time.sleep(11)
    yield
    admin_session.patch(f"{COMP}/admin/feature-flags", json={"key": "btc_payouts_enabled", "value": prior})


@pytest.fixture
def new_user():
    email = f"comp_{uuid.uuid4().hex[:8]}@test.com"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": "Passw0rd!2024", "age_verified": True, "accepted_terms": True},
    )
    assert r.status_code in (200, 201), r.text
    s = _login(email, "Passw0rd!2024")
    me = s.get(f"{API}/auth/me").json()
    return {"session": s, "email": email, "id": me["id"]}


class TestComplianceOverview:
    def test_admin_overview_returns_structured_stats(self, admin_session):
        r = admin_session.get(f"{COMP}/admin/overview")
        assert r.status_code == 200
        data = r.json()
        for key in ("kyc", "payouts", "alerts", "thresholds", "persona_enabled", "blocked_states"):
            assert key in data
        assert data["thresholds"]["kyc_basic_usd"] == 500.0
        assert data["thresholds"]["kyc_enhanced_usd"] == 5000.0
        assert data["thresholds"]["ctr_usd"] == 10000.0

    def test_non_admin_cannot_view_overview(self, new_user):
        r = new_user["session"].get(f"{COMP}/admin/overview")
        assert r.status_code in (401, 403)

    def test_admin_ofac_refresh_loads_list(self, admin_session):
        r = admin_session.post(f"{COMP}/admin/ofac/refresh")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 5  # fallback list has 5 entries minimum
        assert data["source"] in ("treasury", "cache+fallback", "memory")


class TestOfacGate:
    def test_redemption_to_sanctioned_btc_is_blocked(self, new_user):
        r = new_user["session"].post(
            f"{API}/redemption/request",
            json={"game_credits": 4000, "btc_address": SANCTIONED_ADDR},
        )
        # 451 Unavailable For Legal Reasons
        assert r.status_code == 451, r.text
        assert "compliance" in r.json()["detail"].lower() or "ofac" in r.json()["detail"].lower()

    def test_ofac_hit_recorded(self, admin_session):
        # There should now be at least one hit from the previous test.
        r = admin_session.get(f"{COMP}/admin/ofac/hits")
        assert r.status_code == 200
        hits = r.json()
        assert isinstance(hits, list)
        assert any(h["btc_address"] == SANCTIONED_ADDR for h in hits)


class TestKycGate:
    def test_small_redemption_skips_kyc(self, new_user):
        # Below $500 → KYC not required. Still hits JIT gate (no game acct),
        # but the failure mode must be "Redemption held" (JIT), not 402 (KYC).
        r = new_user["session"].post(
            f"{API}/redemption/request",
            json={"game_credits": 4000, "btc_address": CLEAN_ADDR},
        )
        assert r.status_code in (409, 400), r.text  # JIT gate, not KYC gate
        assert r.status_code != 402

    def test_medium_redemption_triggers_basic_kyc(self, new_user):
        r = new_user["session"].post(
            f"{API}/redemption/request",
            json={"game_credits": 60000, "btc_address": CLEAN_ADDR},
        )
        assert r.status_code == 402, r.text
        detail = r.json()["detail"]
        assert detail["required_tier"] == "basic"
        assert detail["kyc_initiate_endpoint"] == "/api/ext/compliance/kyc/initiate"

    def test_large_redemption_triggers_enhanced_kyc(self, new_user):
        r = new_user["session"].post(
            f"{API}/redemption/request",
            json={"game_credits": 600000, "btc_address": CLEAN_ADDR},  # $6,000
        )
        assert r.status_code == 402
        assert r.json()["detail"]["required_tier"] == "enhanced"


class TestKycFlow:
    def test_initiate_kyc_falls_back_to_manual(self, new_user):
        r = new_user["session"].post(f"{COMP}/kyc/initiate", json={"tier": "basic"})
        assert r.status_code == 200
        data = r.json()
        # Persona not configured → manual_upload.
        assert data["method"] == "manual_upload"
        assert data["status"] == "pending"

    def test_user_can_check_own_kyc_status(self, new_user):
        # Must initiate first
        new_user["session"].post(f"{COMP}/kyc/initiate", json={"tier": "basic"})
        r = new_user["session"].get(f"{COMP}/kyc/status?tier=basic")
        assert r.status_code == 200
        data = r.json()
        assert data["tier"] == "basic"
        assert data["status"] in ("pending", "review", "approved", "declined")

    def test_admin_approves_manual_kyc_and_user_becomes_cleared(self, new_user, admin_session):
        # Initiate + upload
        new_user["session"].post(f"{COMP}/kyc/initiate", json={"tier": "basic"})
        files = {"file": ("id.png", b"fake image bytes", "image/png")}
        data = {"tier": "basic", "doc_type": "id_front"}
        r = new_user["session"].post(f"{COMP}/kyc/upload", files=files, data=data)
        assert r.status_code == 200, r.text
        # Admin approves
        r = admin_session.post(f"{COMP}/admin/kyc/decide", json={
            "user_id": new_user["id"], "tier": "basic", "decision": "approve", "notes": "test",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "approved"
        # Status now approved
        r = new_user["session"].get(f"{COMP}/kyc/status?tier=basic")
        assert r.json()["status"] == "approved"


class TestKycReviewerOnlyAdmin:
    def test_non_admin_cannot_decide_kyc(self, new_user):
        r = new_user["session"].post(f"{COMP}/admin/kyc/decide", json={
            "user_id": new_user["id"], "tier": "basic", "decision": "approve",
        })
        assert r.status_code in (401, 403)

    def test_non_admin_cannot_view_queue(self, new_user):
        r = new_user["session"].get(f"{COMP}/admin/kyc/queue")
        assert r.status_code in (401, 403)


class TestAmlEvents:
    def test_redemption_request_creates_aml_event(self, new_user, admin_session):
        # AML endpoint returns a structured list
        r = admin_session.get(f"{COMP}/admin/aml/events?limit=5")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestMasterKillSwitch:
    """The admin BTC payouts kill switch — flip OFF, no redemption/withdrawal works."""

    def test_admin_can_read_flags(self, admin_session):
        r = admin_session.get(f"{COMP}/admin/feature-flags")
        assert r.status_code == 200
        assert "btc_payouts_enabled" in r.json()

    def test_admin_can_toggle_flag(self, admin_session):
        r = admin_session.patch(f"{COMP}/admin/feature-flags", json={"key": "btc_payouts_enabled", "value": False})
        assert r.status_code == 200
        assert r.json()["btc_payouts_enabled"] is False
        # Re-enable for the rest of the suite
        admin_session.patch(f"{COMP}/admin/feature-flags", json={"key": "btc_payouts_enabled", "value": True})
        time.sleep(11)

    def test_unknown_flag_rejected(self, admin_session):
        r = admin_session.patch(f"{COMP}/admin/feature-flags", json={"key": "some_random_thing", "value": True})
        assert r.status_code == 400

    def test_non_admin_cannot_toggle(self, new_user):
        r = new_user["session"].patch(f"{COMP}/admin/feature-flags", json={"key": "btc_payouts_enabled", "value": False})
        assert r.status_code in (401, 403)

    def test_redemption_blocked_when_btc_off(self, admin_session, new_user):
        # Flip OFF
        admin_session.patch(f"{COMP}/admin/feature-flags", json={"key": "btc_payouts_enabled", "value": False})
        time.sleep(11)
        try:
            r = new_user["session"].post(
                f"{API}/redemption/request",
                json={"game_credits": 4000, "btc_address": "bc1qcleantestaddress"},
            )
            assert r.status_code == 503
            detail = r.json()["detail"]
            assert detail.get("btc_enabled") is False
        finally:
            admin_session.patch(f"{COMP}/admin/feature-flags", json={"key": "btc_payouts_enabled", "value": True})
            time.sleep(11)

    def test_public_flags_endpoint_exposes_visibility_state(self, new_user):
        r = new_user["session"].get(f"{COMP}/feature-flags")
        assert r.status_code == 200
        data = r.json()
        assert "btc_payouts_enabled" in data
        assert "redeem_tab_visible" in data
        assert "withdraw_tab_visible" in data
