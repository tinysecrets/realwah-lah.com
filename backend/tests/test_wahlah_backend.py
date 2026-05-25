"""
WAH-LAH backend smoke + integration tests (iteration 6).

Covers: health, auth, games, currency, AMOE, packages, payment info,
admin endpoints, brute force protection, sub-routers (extensions,
distributor-pool, nerve-center, compliance) loaded, and Sugar Sweeps
P2P bot graceful 503 (bridge offline).
"""

import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://fly-ops.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@wah-lah.com"
ADMIN_PASSWORD = "WahLah2026!"


# ---------- shared fixtures ----------

@pytest.fixture(scope="session")
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    assert r.json().get("role") == "admin", "Seeded admin should have role=admin"
    return s


@pytest.fixture(scope="session")
def new_user():
    """Create a fresh user once for the session; return (client, email, user_dict)."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    email = f"test_{uuid.uuid4().hex[:10]}@wahlah-qa.com"
    password = "TestPass!2026"
    r = s.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "name": "Test User", "age_verified": True},
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"Register failed: {r.status_code} {r.text}")
    return s, email, r.json()


# ---------- /api root + health ----------

class TestSmoke:
    def test_health(self, anon_client):
        r = anon_client.get(f"{API}/health", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert body.get("service") == "wah-lah"

    def test_root(self, anon_client):
        r = anon_client.get(f"{API}/", timeout=10)
        assert r.status_code == 200
        assert "WAH-LAH" in r.json().get("message", "")


# ---------- Auth ----------

class TestAuth:
    def test_register_sets_cookies_and_returns_user(self, new_user):
        s, email, body = new_user
        assert body.get("email") == email
        assert body.get("role") == "user"
        assert body.get("age_verified") is True
        # Cookies set
        cookies = s.cookies.get_dict()
        assert "access_token" in cookies
        assert "refresh_token" in cookies
        # game credentials auto-generated
        assert body.get("game_username")
        assert body.get("game_password")

    def test_register_requires_age_verified(self, anon_client):
        email = f"test_{uuid.uuid4().hex[:10]}@wahlah-qa.com"
        r = anon_client.post(
            f"{API}/auth/register",
            json={"email": email, "password": "TestPass!2026", "age_verified": False},
            timeout=15,
        )
        assert r.status_code in (400, 422)

    def test_admin_login_returns_admin_role(self, admin_client):
        r = admin_client.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        me = r.json()
        assert me.get("email") == ADMIN_EMAIL
        assert me.get("role") == "admin"

    def test_me_without_cookie_returns_401(self, anon_client):
        # Use a fresh session w/o cookies
        s = requests.Session()
        r = s.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 401

    def test_brute_force_protection_triggers_429(self):
        # Use a unique email so we don't lock the real admin or pollute
        email = f"bf_{uuid.uuid4().hex[:10]}@wahlah-qa.com"
        s = requests.Session()
        last = None
        for _ in range(6):
            last = s.post(
                f"{API}/auth/login",
                json={"email": email, "password": "wrong-pw"},
                timeout=10,
            )
        assert last is not None
        # After 5 failed attempts, the 6th should return 429
        assert last.status_code in (429,), f"Expected 429 after brute force, got {last.status_code} {last.text}"


# ---------- Games ----------

class TestGames:
    def test_games_list_returns_seeded(self, anon_client):
        r = anon_client.get(f"{API}/games", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # seed should yield at least one game
        assert len(data) >= 1

    def test_games_all_requires_admin(self, anon_client, admin_client):
        # Anonymous → unauthorized
        r_anon = requests.get(f"{API}/games/all", timeout=10)
        assert r_anon.status_code in (401, 403)
        # Admin → 200
        r_adm = admin_client.get(f"{API}/games/all", timeout=10)
        assert r_adm.status_code == 200
        assert isinstance(r_adm.json(), list)


# ---------- Currency ----------

class TestCurrency:
    def test_balance_for_logged_in_user(self, new_user):
        s, _, _ = new_user
        r = s.get(f"{API}/currency/balance", timeout=10)
        assert r.status_code == 200
        body = r.json()
        # Expect dual-currency-ish keys
        keys = set(body.keys())
        assert keys & {"sugar_tokens", "game_credits", "credits"}, f"Unexpected balance shape: {body}"

    def test_balance_requires_auth(self):
        r = requests.get(f"{API}/currency/balance", timeout=10)
        assert r.status_code == 401


# ---------- AMOE ----------

class TestAMOE:
    def test_amoe_status_for_fresh_user(self, new_user):
        s, _, _ = new_user
        r = s.get(f"{API}/amoe/status", timeout=10)
        assert r.status_code == 200
        body = r.json()
        # eligibility flag should exist in some form
        assert any(k in body for k in ("eligible", "can_claim", "available")), f"AMOE status shape: {body}"

    def test_amoe_claim_daily_grants_credits(self, new_user):
        s, _, _ = new_user
        r = s.post(f"{API}/amoe/claim-daily", json={}, timeout=15)
        assert r.status_code in (200, 201), f"AMOE claim failed: {r.status_code} {r.text}"
        body = r.json()
        # Balance must reflect 100 free credits
        bal = s.get(f"{API}/currency/balance", timeout=10).json()
        granted = bal.get("game_credits", bal.get("credits", 0))
        assert granted >= 100, f"Expected >=100 credits after AMOE, got {granted}; claim body={body}"

    def test_amoe_claim_twice_blocked(self, new_user):
        s, _, _ = new_user
        # second claim same day must not double-grant
        r2 = s.post(f"{API}/amoe/claim-daily", json={}, timeout=15)
        # Either 4xx OR a 200 indicating already claimed — both acceptable as long as not silently re-granting
        if r2.status_code == 200:
            bal = s.get(f"{API}/currency/balance", timeout=10).json()
            assert bal.get("game_credits", bal.get("credits", 0)) < 250, "AMOE double-claim should not stack"
        else:
            assert r2.status_code in (400, 403, 409, 429)


# ---------- Packages + Payment info ----------

class TestPackagesAndPayments:
    def test_packages(self, anon_client):
        r = anon_client.get(f"{API}/packages", timeout=10)
        assert r.status_code == 200
        body = r.json()
        # Expect min_deposit + suggestions list
        assert "min_deposit" in body, f"packages payload: {body}"
        assert "suggestions" in body, f"packages payload: {body}"
        assert isinstance(body["suggestions"], list)

    def test_card_info(self, anon_client):
        r = anon_client.get(f"{API}/payment/card-info", timeout=10)
        assert r.status_code == 200
        body = r.json()
        # Should contain the configured CARD_PAYMENT_TAG ($WahLah)
        payload_str = str(body)
        assert "WahLah" in payload_str or "$" in payload_str, f"card-info: {body}"

    def test_crypto_info(self, anon_client):
        r = anon_client.get(f"{API}/payment/crypto-info", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)
        assert len(body) > 0


# ---------- Admin ----------

class TestAdmin:
    def test_admin_users_requires_admin(self, new_user, admin_client):
        s, _, _ = new_user
        # non-admin
        r = s.get(f"{API}/admin/users", timeout=10)
        assert r.status_code in (401, 403)
        # admin
        r2 = admin_client.get(f"{API}/admin/users", timeout=10)
        assert r2.status_code == 200
        assert isinstance(r2.json(), list)

    def test_admin_stats(self, admin_client):
        r = admin_client.get(f"{API}/admin/stats", timeout=15)
        assert r.status_code == 200
        body = r.json()
        # Should contain counts
        assert any(k in body for k in ("total_users", "users", "user_count")), f"stats: {body}"
        assert any(k in body for k in ("total_transactions", "transactions", "transaction_count")), f"stats: {body}"

    def test_p2p_transfer_graceful_503_when_bridge_offline(self, admin_client):
        """Bridge must be offline in this pod (no chromium). Endpoint must NOT 500."""
        r = admin_client.post(
            f"{API}/admin/p2p-transfer",
            json={"user_id": "000000000000000000000000", "platform_id": "demo", "player_id": "demo", "amount": 1},
            timeout=20,
        )
        # 503 = bridge offline (expected). 400/404 also acceptable if it validates first.
        # Critical: must NOT be 500.
        assert r.status_code != 500, f"P2P endpoint crashed: {r.status_code} {r.text}"
        assert r.status_code in (400, 401, 403, 404, 503), f"Unexpected p2p code: {r.status_code} {r.text}"


# ---------- Sub-routers loaded (not 404) ----------

class TestSubRoutersLoaded:
    """Confirm each sub-router is mounted (no 404)."""

    def _probe(self, path, client=None):
        url = f"{BASE_URL}{path}"
        sess = client or requests
        r = sess.get(url, timeout=10)
        # router loaded if not 404. 401/403/200/422/400 all confirm presence.
        assert r.status_code != 404, f"{path} returned 404 — router not loaded"
        return r

    def test_extensions_router(self, admin_client):
        # VIP tiers endpoint (admin or auth required)
        self._probe("/api/ext/vip/tiers", admin_client)

    def test_distributor_pool_router(self, admin_client):
        self._probe("/api/ext/pool/admin/health", admin_client)

    def test_nerve_center_router(self, admin_client):
        self._probe("/api/ext/nerve/overview", admin_client)

    def test_compliance_router(self, new_user):
        s, _, _ = new_user
        self._probe("/api/ext/compliance/kyc/status", s)
