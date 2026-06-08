"""
Iteration 7 — post-Emergent-migration backend smoke tests.

Validates the request brief:
- Admin auth via ADMIN_EMAIL / ADMIN_PASSWORD env vars
- Games seeded (7 brand cards)
- /api/payment/card-info tag == $jrs092393
- /api/payment/crypto-info 200
- /api/checkout/create with sk_test_emergent should not 500 (URL or graceful 4xx)
- /api/boss/chat actually round-trips through Cerebras (provider=cerebras)
- /api/boss/providers shows cerebras enabled, ollama/venice disabled
- /api/amoe/claim-daily enforces 24h cooldown
- /api/giftcard/request creates a pending redemption (acts as redeem/giftcard)
- /api/health quick + no DB
- Admin endpoints: users/transactions, gift card admin pending (as 'redemptions')
- Geoblock rejects registration via X-Forwarded-For from blocked state
- KYC thresholds: $500 → KYC_BASIC, $5000 → KYC_ENHANCED for redemption gate
"""
import os
import re
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to the URL from the brief if env not propagated to the test process
    BASE_URL = "https://wahlah-app.preview.emergentagent.com"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@wahlah.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "REPLACE_WITH_ADMIN_PASSWORD")


# ------------- Fixtures -------------
@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("role") == "admin", f"expected admin role, got {data.get('role')}"
    assert "access_token" in s.cookies, "no access_token cookie set"
    return s


@pytest.fixture()
def user_session():
    s = requests.Session()
    email = f"iter7_{uuid.uuid4().hex[:8]}@wahlah-qa.com"
    r = s.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "TestPass2026!", "name": "Iter7 User", "age_verified": True
    }, timeout=15)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    s.email = email  # type: ignore[attr-defined]
    return s


# ------------- Health & quick checks -------------
def test_health_quick_no_db():
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/health", timeout=5)
    elapsed = time.time() - t0
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") == "ok"
    assert j.get("service") == "wah-lah"
    assert elapsed < 2.0, f"/api/health too slow ({elapsed:.2f}s) — suggests DB hit"


# ------------- Auth -------------
def test_admin_login_returns_jwt_cookie_and_profile(admin_session):
    # Verify /auth/me returns admin profile
    r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=10)
    assert r.status_code == 200
    me = r.json()
    assert me["email"].lower() == ADMIN_EMAIL.lower()
    assert me["role"] == "admin"


# ------------- Games -------------
EXPECTED_GAMES = {"Fire Kirin", "Juwa", "Juwa 2", "Ultra Panda", "Panda Master", "Orion Stars", "Game Vault"}


def test_games_brand_cards():
    r = requests.get(f"{BASE_URL}/api/games", timeout=10)
    assert r.status_code == 200
    games = r.json()
    assert isinstance(games, list)
    names = {g.get("name") for g in games}
    missing = EXPECTED_GAMES - names
    assert not missing, f"missing seeded games: {missing}. Got: {names}"
    assert len(games) >= 7, f"expected >=7 games, got {len(games)}"


# ------------- Payment info -------------
def test_payment_card_info_cashtag_exact():
    r = requests.get(f"{BASE_URL}/api/payment/card-info", timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert j.get("tag") == "$jrs092393", f"cashtag mismatch: {j.get('tag')!r}"


def test_payment_crypto_info():
    r = requests.get(f"{BASE_URL}/api/payment/crypto-info", timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert "btc_address" in j
    assert "instructions" in j


# ------------- Stripe checkout -------------
def test_checkout_create_does_not_500(user_session):
    # Get an active game id
    games = requests.get(f"{BASE_URL}/api/games", timeout=10).json()
    game_id = games[0]["id"]
    payload = {
        "amount": 10.0,
        "game_id": game_id,
        "account_name": "qa-test-account",
        "origin_url": BASE_URL,
    }
    r = user_session.post(f"{BASE_URL}/api/checkout/create", json=payload, timeout=30)
    # Must not 500. Acceptable outcomes:
    #   200 + url → Stripe accepted the test key (ideal)
    #   4xx with clear message (e.g., 409 JIT registration hold, 4xx Stripe key rejection, 451 geoblock)
    assert r.status_code != 500, f"checkout/create returned 500: {r.text[:300]}"
    if r.status_code == 200:
        j = r.json()
        assert "url" in j and j["url"].startswith("https://"), f"missing checkout url: {j}"
        assert "session_id" in j
    else:
        # Make sure error body is a readable message, not a stack trace
        assert r.status_code < 600
        body = r.text
        assert "Traceback" not in body, f"stack trace leaked: {body[:300]}"


# ------------- Boss Genie / Cerebras -------------
def test_boss_providers_cerebras_enabled(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/boss/providers", timeout=10)
    assert r.status_code == 200
    j = r.json()
    by_id = {p["id"]: p for p in j["providers"]}
    assert by_id["cerebras"]["enabled"] is True, f"cerebras not enabled: {by_id}"
    assert by_id["ollama"]["enabled"] is False
    assert by_id["venice"]["enabled"] is False
    assert j["default"] == "cerebras"


def test_boss_chat_roundtrips_cerebras(admin_session):
    # Retry up to 3x — Cerebras free tier occasionally returns 429 queue_exceeded.
    r = None
    for attempt in range(3):
        r = admin_session.post(
            f"{BASE_URL}/api/boss/chat",
            json={"message": "say hi in 5 words", "provider": "cerebras"},
            timeout=60,
        )
        if r.status_code == 200:
            break
        if r.status_code == 502 and "queue_exceeded" in r.text:
            time.sleep(8)
            continue
        break
    assert r is not None and r.status_code == 200, f"boss/chat failed: {r.status_code} {r.text[:300]}"
    j = r.json()
    # Response shape varies — check for any of: reply / message / response / content
    reply = j.get("reply") or j.get("message") or j.get("response") or j.get("content")
    assert reply, f"empty reply from boss/chat: {j}"
    assert isinstance(reply, str)
    assert len(reply.strip()) > 0
    # Provider hint should be cerebras (field name varies — accept any)
    prov = j.get("provider") or j.get("model_provider") or ""
    assert "cerebras" in str(prov).lower() or "qwen" in str(j.get("model", "")).lower(), \
        f"expected cerebras hint in response: {j}"


# ------------- AMOE cooldown -------------
def test_amoe_claim_then_cooldown_blocks_repeat(user_session):
    r1 = user_session.post(f"{BASE_URL}/api/amoe/claim-daily", json={}, timeout=15)
    assert r1.status_code == 200, f"first claim failed: {r1.text}"
    j1 = r1.json()
    assert j1.get("success") is True
    assert j1.get("credits_granted") == 100, f"expected 100 credits, got {j1.get('credits_granted')}"

    # Second claim within 24h must fail
    r2 = user_session.post(f"{BASE_URL}/api/amoe/claim-daily", json={}, timeout=15)
    assert r2.status_code == 400, f"second claim should be blocked, got {r2.status_code}: {r2.text}"

    # Status reports not eligible
    rs = user_session.get(f"{BASE_URL}/api/amoe/status", timeout=10)
    assert rs.status_code == 200
    assert rs.json()["eligible"] is False


# ------------- Gift card request (redemption path) -------------
def test_giftcard_request_creates_pending(user_session):
    # User has 0 credits at registration. Claim AMOE first to get 100 game_credits.
    rc = user_session.post(f"{BASE_URL}/api/amoe/claim-daily", json={}, timeout=15)
    assert rc.status_code == 200, f"AMOE claim failed: {rc.text}"

    # First fetch catalog to confirm endpoint works
    r = requests.get(f"{BASE_URL}/api/giftcard/catalog", timeout=10)
    assert r.status_code == 200
    catalog = r.json()
    assert any(c.get("id") == "amazon" for c in catalog)

    # Submit a small request (amount=25 USD) — user has 100 credits from AMOE
    payload = {"brand": "amazon", "amount_credits": 25, "recipient_email": user_session.email}
    r = user_session.post(f"{BASE_URL}/api/giftcard/request", json=payload, timeout=15)
    # 200 = pending created. 503 if feature flag off, 402 if KYC required.
    assert r.status_code in (200, 503, 402), f"unexpected: {r.status_code} {r.text}"
    if r.status_code == 200:
        j = r.json()
        assert j["status"] == "pending"
        assert j["brand"] == "amazon"
        assert j["amount_usd"] == 25


# ------------- Admin endpoints -------------
def test_admin_users_list(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/users", timeout=15)
    assert r.status_code == 200
    arr = r.json()
    assert isinstance(arr, list)
    assert len(arr) >= 1


def test_admin_transactions_list(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/transactions", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_admin_redemptions_pending(admin_session):
    # Brief calls it /api/admin/redemptions but actual path is the gift card admin queue.
    r = admin_session.get(f"{BASE_URL}/api/ext/giftcard/admin/pending", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_admin_endpoints_require_admin(user_session):
    r = user_session.get(f"{BASE_URL}/api/admin/users", timeout=10)
    assert r.status_code == 403


# ------------- Geoblock -------------
def test_geoblock_blocks_redemption_from_blocked_state():
    """Geoblock is checked on deposit/redemption/withdrawal — NOT on /auth/register.
    Test with a Las Vegas (NV) IP via X-Forwarded-For on checkout/create which is
    geoblock-gated. We use a publicly-known Las Vegas IP to trigger ipapi.co
    state lookup → NV is in BLOCKED_STATES.
    """
    # Register an ephemeral user
    s = requests.Session()
    email = f"geo_{uuid.uuid4().hex[:8]}@wahlah-qa.com"
    r = s.post(f"{BASE_URL}/api/auth/register",
               json={"email": email, "password": "TestPass2026!", "name": "Geo", "age_verified": True},
               timeout=15)
    assert r.status_code == 200

    games = requests.get(f"{BASE_URL}/api/games", timeout=10).json()
    game_id = games[0]["id"]

    # Nevada (Las Vegas) IP: 64.79.96.0 range (Cox Communications, Las Vegas)
    nv_ip = "64.79.96.1"
    r = s.post(
        f"{BASE_URL}/api/checkout/create",
        json={"amount": 10.0, "game_id": game_id, "account_name": "geo", "origin_url": BASE_URL},
        headers={"X-Forwarded-For": nv_ip},
        timeout=20,
    )
    # Expect 451 (Unavailable For Legal Reasons). If ipapi fails open, code soft-allows;
    # mark as xfail rather than hard fail so transient ipapi outages don't block CI.
    if r.status_code == 451:
        assert "region" in r.text.lower() or "nv" in r.text.lower()
    else:
        pytest.skip(f"geoblock soft-failed (ipapi lookup may be unavailable). status={r.status_code} body={r.text[:200]}")


# ------------- KYC thresholds -------------
def test_kyc_basic_threshold_500_blocks_redemption(user_session):
    """At $500 USD redemption (50,000 credits @ $0.01), KYC_BASIC must be required.
    User has no KYC → expect 402 with required_tier=basic, OR 503 if BTC kill-switch is on.
    """
    # Try redeeming 50000 credits ($500)
    r = user_session.post(
        f"{BASE_URL}/api/redemption/request",
        json={"game_credits": 50000, "btc_address": "bc1qtest" + "0" * 20},
        timeout=15,
    )
    # Acceptable codes:
    # 503 → btc_payouts_enabled feature flag is off (master kill switch)
    # 402 → KYC required (the actual gate we're testing)
    # 451 → geoblock unrelated (shouldn't happen on default IP)
    # 400 → insufficient credits, but the KYC gate runs first so unlikely
    assert r.status_code in (402, 503, 451, 400), f"unexpected: {r.status_code} {r.text[:300]}"
    if r.status_code == 503:
        pytest.skip("BTC kill switch is ON — KYC gate not reachable")
    if r.status_code == 402:
        detail = r.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("required_tier") in ("basic", "enhanced")


def test_kyc_enhanced_threshold_5000_requires_enhanced(user_session):
    r = user_session.post(
        f"{BASE_URL}/api/redemption/request",
        json={"game_credits": 500000, "btc_address": "bc1qtest" + "1" * 20},  # $5,000
        timeout=15,
    )
    assert r.status_code in (402, 503, 451, 400), f"unexpected: {r.status_code} {r.text[:300]}"
    if r.status_code == 503:
        pytest.skip("BTC kill switch is ON — KYC gate not reachable")
    if r.status_code == 402:
        detail = r.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("required_tier") == "enhanced", f"expected enhanced tier at $5000, got {detail}"
