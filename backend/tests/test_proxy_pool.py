"""Tests for Distributor Proxy Pool (Hybrid Buffer Strategy).

Goes through the live backend HTTP API, same style as test_jit_features.py.
Covers: CRUD, list, round-robin selection via manual-transfer endpoint,
caps, cooldown, lock/unlock, auto-reset of daily volume, and health.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://wahlah-deploy.preview.emergentagent.com")
API = f"{BASE_URL}/api"
POOL = f"{API}/ext/pool/admin"

ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@wah-lah.com")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "SugarCity2024!")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def user_session() -> requests.Session:
    """Non-admin — used for authz tests."""
    email = f"pool_u_{int(time.time())}@test.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "Passw0rd!2024",
        "age_verified": True, "accepted_terms": True,
    })
    assert r.status_code in (200, 201), r.text
    return _login(email, "Passw0rd!2024")


@pytest.fixture
def created_proxies(admin_session):
    """Yield a list of created proxy IDs and clean them up afterwards."""
    ids: list[str] = []
    yield ids
    for pid in ids:
        try:
            admin_session.delete(f"{POOL}/proxies/{pid}")
        except Exception:
            pass


def _create(admin_session, ids: list[str], **kw) -> dict:
    payload = {
        "label": kw.get("label", f"t-{uuid.uuid4().hex[:6]}"),
        "username": kw.get("username", f"u-{uuid.uuid4().hex[:6]}"),
        "password": kw.get("password", "secret"),
        "base_url": kw.get("base_url", "https://sugarsweeps.com"),
        "per_transfer_cap": kw.get("per_transfer_cap", 500),
        "daily_cap": kw.get("daily_cap", 5000),
    }
    r = admin_session.post(f"{POOL}/proxies", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    ids.append(data["id"])
    return data


# =========================================================
# Auth guard
# =========================================================
class TestAdminGuard:
    def test_anon_cannot_list_proxies(self):
        r = requests.get(f"{POOL}/proxies")
        assert r.status_code in (401, 403)

    def test_non_admin_cannot_list_proxies(self, user_session):
        r = user_session.get(f"{POOL}/proxies")
        assert r.status_code in (401, 403)


# =========================================================
# CRUD
# =========================================================
class TestProxyCRUD:
    def test_create_and_list(self, admin_session, created_proxies):
        p = _create(admin_session, created_proxies, label="crud-01")
        assert p["status"] == "active"
        assert p["daily_cap"] == 5000.0
        assert p["per_transfer_cap"] == 500.0
        assert "password" not in p and "password_enc" not in p

        r = admin_session.get(f"{POOL}/proxies")
        assert r.status_code == 200
        labels = [x["label"] for x in r.json()]
        assert "crud-01" in labels

    def test_update_caps_and_label(self, admin_session, created_proxies):
        p = _create(admin_session, created_proxies)
        r = admin_session.patch(f"{POOL}/proxies/{p['id']}", json={"label": "renamed", "daily_cap": 9999})
        assert r.status_code == 200
        body = r.json()
        assert body["label"] == "renamed"
        assert body["daily_cap"] == 9999

    def test_update_status_only_allows_active_disabled(self, admin_session, created_proxies):
        p = _create(admin_session, created_proxies)
        r = admin_session.patch(f"{POOL}/proxies/{p['id']}", json={"status": "locked"})
        assert r.status_code == 400

    def test_disable_then_enable(self, admin_session, created_proxies):
        p = _create(admin_session, created_proxies)
        r = admin_session.patch(f"{POOL}/proxies/{p['id']}", json={"status": "disabled"})
        assert r.status_code == 200 and r.json()["status"] == "disabled"
        r = admin_session.patch(f"{POOL}/proxies/{p['id']}", json={"status": "active"})
        assert r.status_code == 200 and r.json()["status"] == "active"

    def test_delete(self, admin_session, created_proxies):
        p = _create(admin_session, created_proxies, label="gone-soon")
        r = admin_session.delete(f"{POOL}/proxies/{p['id']}")
        assert r.status_code == 200 and r.json() == {"deleted": True}
        created_proxies.remove(p["id"])
        # listing should not include it anymore
        r = admin_session.get(f"{POOL}/proxies")
        assert p["id"] not in [x["id"] for x in r.json()]


# =========================================================
# Selection via manual-transfer endpoint
# =========================================================
class TestPoolSelectionAndTransfer:
    def test_empty_pool_manual_transfer_reports_no_proxies(self, admin_session, created_proxies):
        # IMPORTANT: Do NOT delete pre-existing proxies (admin may have real ones).
        # Instead: disable every existing proxy, run the test, re-enable afterwards.
        existing = admin_session.get(f"{POOL}/proxies").json()
        restore = []  # proxies to re-enable after the test
        for x in existing:
            if x.get("status") == "active":
                admin_session.patch(f"{POOL}/proxies/{x['id']}", json={"status": "disabled"})
                restore.append(x["id"])
        try:
            r = admin_session.post(f"{POOL}/transfer", json={
                "recipient_username": "sugartest001", "amount": 50, "platform": "fire_kirin",
            })
            assert r.status_code == 200
            body = r.json()
            assert body["ok"] is False
            assert ("No proxies" in body["message"]) or ("proxies are" in body["message"].lower())
        finally:
            for pid in restore:
                admin_session.patch(f"{POOL}/proxies/{pid}", json={"status": "active"})

    def test_per_transfer_cap_blocks(self, admin_session, created_proxies):
        # Disable pre-existing active proxies so only the small-cap test proxy is eligible.
        existing = admin_session.get(f"{POOL}/proxies").json()
        restore = []
        for x in existing:
            if x.get("status") == "active":
                admin_session.patch(f"{POOL}/proxies/{x['id']}", json={"status": "disabled"})
                restore.append(x["id"])
        try:
            _create(admin_session, created_proxies, label="small", per_transfer_cap=100, daily_cap=5000)
            r = admin_session.post(f"{POOL}/transfer", json={
                "recipient_username": "sugartest001", "amount": 200, "platform": "fire_kirin",
            })
            assert r.status_code == 200
            assert r.json()["ok"] is False
            assert "cap" in r.json()["message"].lower()
        finally:
            for pid in restore:
                admin_session.patch(f"{POOL}/proxies/{pid}", json={"status": "active"})

    def test_disabled_proxies_excluded(self, admin_session, created_proxies):
        p = _create(admin_session, created_proxies, label="offline")
        admin_session.patch(f"{POOL}/proxies/{p['id']}", json={"status": "disabled"})
        r = admin_session.post(f"{POOL}/transfer", json={
            "recipient_username": "sugartest001", "amount": 50, "platform": "fire_kirin",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is False


# =========================================================
# Health
# =========================================================
class TestPoolHealth:
    def test_health_reflects_pool_state(self, admin_session, created_proxies):
        # Use disable rather than delete so we don't nuke admin's real proxies.
        existing = admin_session.get(f"{POOL}/proxies").json()
        restore = []
        for x in existing:
            if x.get("status") == "active":
                admin_session.patch(f"{POOL}/proxies/{x['id']}", json={"status": "disabled"})
                restore.append(x["id"])
        try:
            _create(admin_session, created_proxies, label="h1", daily_cap=1000)
            _create(admin_session, created_proxies, label="h2", daily_cap=2000)
            p3 = _create(admin_session, created_proxies, label="h3", daily_cap=3000)
            admin_session.patch(f"{POOL}/proxies/{p3['id']}", json={"status": "disabled"})

            r = admin_session.get(f"{POOL}/health")
            assert r.status_code == 200
            h = r.json()
            # test-created proxies: 2 active + 1 disabled (+ any pre-existing disabled ones)
            assert h["active"] == 2
            assert h["daily_capacity_remaining"] == 3000.0
        finally:
            for pid in restore:
                admin_session.patch(f"{POOL}/proxies/{pid}", json={"status": "active"})


# =========================================================
# Ping (expected to fail because Playwright browsers not installed)
# =========================================================
class TestPing:
    def test_ping_returns_graceful_error_without_browsers(self, admin_session, created_proxies):
        p = _create(admin_session, created_proxies, label="ping-test")
        r = admin_session.post(f"{POOL}/proxies/{p['id']}/ping")
        # Should not 500; should return structured {ok, message}
        assert r.status_code == 200
        body = r.json()
        assert "ok" in body and "message" in body
        # ok may be True (chromium launches & redirects) OR False (login fails):
        # both are valid as long as we got past the launch step without a 500.


# =========================================================
# Multi-hub support
# =========================================================
class TestMultiHub:
    def test_list_hubs(self, admin_session):
        r = admin_session.get(f"{POOL}/hubs")
        assert r.status_code == 200
        hub_types = [h["hub_type"] for h in r.json()]
        for expected in ["sugar_sweeps", "bitbetwin", "bitplay", "bitspinwin", "bitofgold", "win777"]:
            assert expected in hub_types

    def test_create_with_hub_populates_supported_platforms(self, admin_session, created_proxies):
        r = admin_session.post(f"{POOL}/proxies", json={
            "label": "bbw-01", "username": "u", "password": "pw",
            "hub_type": "bitbetwin",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        created_proxies.append(data["id"])
        assert data["hub_type"] == "bitbetwin"
        assert "fire_kirin" in data["supported_platforms"]
        assert data["base_url"] == "https://bitbetwin.cc"

    def test_platform_filter_in_selection(self, admin_session, created_proxies):
        # Disable (not delete) existing proxies so admin's real pool is untouched
        existing = admin_session.get(f"{POOL}/proxies").json()
        restore = []
        for x in existing:
            if x.get("status") == "active":
                admin_session.patch(f"{POOL}/proxies/{x['id']}", json={"status": "disabled"})
                restore.append(x["id"])
        try:
            # Add a proxy on bitplay (supports fire_kirin) but not vegas_x
            r = admin_session.post(f"{POOL}/proxies", json={
                "label": "bp-filter-test", "username": "u", "password": "pw",
                "hub_type": "bitplay",
            })
            assert r.status_code == 200
            created_proxies.append(r.json()["id"])

            # Transfer to fire_kirin: SHOULD select a proxy (transfer fails on bad creds but that's fine)
            r1 = admin_session.post(f"{POOL}/transfer", json={
                "recipient_username": "sugar_test", "amount": 50, "platform": "fire_kirin",
            })
            assert r1.status_code == 200
            body1 = r1.json()
            assert "No active proxy supports" not in body1["message"]

            # Transfer to vegas_x: no proxy supports this → clean error
            r2 = admin_session.post(f"{POOL}/transfer", json={
                "recipient_username": "sugar_test", "amount": 50, "platform": "vegas_x",
            })
            assert r2.status_code == 200
            body2 = r2.json()
            assert body2["ok"] is False
            assert "supports platform" in body2["message"] or "vegas_x" in body2["message"]
        finally:
            for pid in restore:
                admin_session.patch(f"{POOL}/proxies/{pid}", json={"status": "active"})

    def test_reject_unknown_hub(self, admin_session, created_proxies):
        r = admin_session.post(f"{POOL}/proxies", json={
            "label": "bad", "username": "u", "password": "pw", "hub_type": "not_a_real_hub",
        })
        assert r.status_code == 400


# =========================================================
# Redemption JIT gate
# =========================================================
class TestRedemptionGate:
    def _ensure_btc_on(self):
        """BTC is off by default (master switch). Enable for this test, restore after."""
        a = requests.Session()
        a.post(f"{API}/auth/login", json={"email": "admin@wah-lah.com", "password": "SugarCity2024!"})
        prior = a.get(f"{API}/ext/compliance/admin/feature-flags").json().get("btc_payouts_enabled", False)
        a.patch(f"{API}/ext/compliance/admin/feature-flags", json={"key": "btc_payouts_enabled", "value": True})
        time.sleep(11)
        return a, prior

    def test_redemption_blocked_without_platform_account(self):
        a, prior = self._ensure_btc_on()
        try:
            email = f"redeem_{int(time.time())}@test.com"
            r = requests.post(f"{API}/auth/register", json={
                "email": email, "password": "Passw0rd!2024", "age_verified": True, "accepted_terms": True,
            })
            assert r.status_code in (200, 201)
            s = _login(email, "Passw0rd!2024")
            # User has no platform_accounts yet → should get 409
            r = s.post(f"{API}/redemption/request", json={
                "game_credits": 5000, "btc_address": "bc1qtestaddress",
            })
            assert r.status_code == 409, r.text
            assert "Redemption held" in r.json()["detail"]
        finally:
            a.patch(f"{API}/ext/compliance/admin/feature-flags", json={"key": "btc_payouts_enabled", "value": prior})
            time.sleep(11)
