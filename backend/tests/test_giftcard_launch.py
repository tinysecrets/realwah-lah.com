"""
Iteration 5 Tests — Gift Card Redemption + Launch Checklist + Boss Genie new tools
====================================================================================
Covers:
- /api/giftcard/catalog
- /api/giftcard/request (success / insufficient credits / unsupported brand / over-max / feature-flag off)
- /api/giftcard/my-requests (code redacted while pending)
- /api/giftcard/my-requests/{rid} (code revealed only when fulfilled)
- /api/ext/giftcard/admin/pending  (admin only)
- /api/ext/giftcard/admin/fulfill/{rid}
- /api/ext/giftcard/admin/reject/{rid} (verifies refund)
- /api/ext/launch-checklist (summary + 6 checks + banner)
- /api/boss/chat with launch_readiness + list_pending_giftcards tools
- /game-logos/*.svg static asset serving
"""
import os
import uuid
import pytest
import requests
from pathlib import Path

# Load backend .env so DB_NAME/MONGO_URL resolve the same as the server.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://wahlah-deploy.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
EXT_API = f"{API}/ext"

ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@wah-lah.com")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "SugarCity2024!")

# --- Helpers --------------------------------------------------------------

def _login(session, email, password):
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password})
    return r

def _new_user_session(credits=0):
    """Register a fresh user and (optionally) credit their game_credits via a small admin trick:
    we use the BTC quote bypass trick? No — easier: bump credits via direct mongo from a fixture."""
    s = requests.Session()
    email = f"gctest_{uuid.uuid4().hex[:8]}@test.com"
    pwd = "TestPass123!"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": pwd, "age_verified": True})
    assert r.status_code == 200, f"register failed: {r.text}"
    uid = r.json().get("id") or r.json().get("_id")
    if credits > 0:
        _set_credits(uid, credits)
    return s, email, uid

def _admin_session():
    s = requests.Session()
    r = _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return s

def _set_credits(user_id, amount):
    """Set a user's game_credits directly via mongosh. Test-only utility."""
    import subprocess
    # Use motor URL from env
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")
    js = f'db.users.updateOne({{id:"{user_id}"}}, {{$set:{{game_credits:{int(amount)}}}}})'
    out = subprocess.run(
        ["mongosh", mongo_url + "/" + db_name, "--quiet", "--eval", js],
        capture_output=True, text=True, timeout=20,
    )
    # Fallback: try _id-based update via ObjectId
    if "matchedCount: 1" not in out.stdout and "matchedCount: 1" not in out.stderr:
        js2 = f'db.users.updateOne({{_id: ObjectId("{user_id}")}}, {{$set:{{game_credits:{int(amount)}}}}})'
        subprocess.run(["mongosh", mongo_url + "/" + db_name, "--quiet", "--eval", js2],
                       capture_output=True, text=True, timeout=20)

def _set_flag(name, value):
    """Use the admin PATCH /api/ext/admin/feature-flags endpoint — it invalidates
    the in-process flag cache server-side so reads pick up the new value immediately."""
    s = requests.Session()
    r = _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"admin login failed: {r.text}"
    r2 = s.patch(f"{EXT_API}/compliance/admin/feature-flags", json={"key": name, "value": value})
    if r2.status_code != 200:
        # tolerate older path naming during test
        raise AssertionError(f"set_flag({name},{value}) failed: {r2.status_code} {r2.text}")


# --- Catalog & static assets ---------------------------------------------

class TestCatalog:
    def test_catalog_returns_8_brands(self):
        r = requests.get(f"{API}/giftcard/catalog")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        ids = {x["id"] for x in data}
        expected = {"amazon", "visa", "xbox", "roblox", "doordash", "spotify", "walmart", "google_play"}
        assert ids == expected, f"Brand mismatch: {ids}"
        for b in data:
            assert "min" in b and "max" in b and "label" in b
        # spot check caps
        amazon = next(x for x in data if x["id"] == "amazon")
        spotify = next(x for x in data if x["id"] == "spotify")
        assert amazon["max"] == 500
        assert spotify["max"] == 100

class TestGameLogos:
    @pytest.mark.parametrize("name", ["panda_master", "orion_stars", "game_vault"])
    def test_logo_serves_200(self, name):
        r = requests.get(f"{BASE_URL}/game-logos/{name}.svg")
        assert r.status_code == 200, f"logo {name}: {r.status_code}"
        assert "svg" in r.headers.get("content-type", "").lower() or r.text.strip().startswith("<")


# --- Gift card request validation ---------------------------------------

class TestGiftCardRequestValidation:
    def setup_method(self):
        _set_flag("giftcard_redemption_enabled", True)
        self.s, self.email, self.uid = _new_user_session(credits=200)

    def test_insufficient_credits_returns_400(self):
        s, email, uid = _new_user_session(credits=0)
        r = s.post(f"{API}/giftcard/request", json={
            "brand": "amazon", "amount_credits": 25, "recipient_email": email,
        })
        assert r.status_code == 400, r.text
        assert "Insufficient" in r.json().get("detail", "")

    def test_unsupported_brand_returns_400(self):
        r = self.s.post(f"{API}/giftcard/request", json={
            "brand": "bogus", "amount_credits": 10, "recipient_email": self.email,
        })
        assert r.status_code == 400
        assert "Unsupported" in r.json().get("detail", "")

    def test_above_brand_max_amazon_returns_400(self):
        r = self.s.post(f"{API}/giftcard/request", json={
            "brand": "amazon", "amount_credits": 600, "recipient_email": self.email,
        })
        assert r.status_code == 400
        assert "Maximum" in r.json().get("detail", "")

    def test_above_brand_max_spotify_returns_400(self):
        r = self.s.post(f"{API}/giftcard/request", json={
            "brand": "spotify", "amount_credits": 150, "recipient_email": self.email,
        })
        assert r.status_code == 400
        assert "Maximum" in r.json().get("detail", "")

    def test_feature_flag_off_returns_503(self):
        _set_flag("giftcard_redemption_enabled", False)
        try:
            r = self.s.post(f"{API}/giftcard/request", json={
                "brand": "amazon", "amount_credits": 10, "recipient_email": self.email,
            })
            assert r.status_code == 503, r.text
        finally:
            _set_flag("giftcard_redemption_enabled", True)


# --- Successful request + my-requests ------------------------------------

class TestGiftCardRequestSuccess:
    def setup_method(self):
        _set_flag("giftcard_redemption_enabled", True)
        self.s, self.email, self.uid = _new_user_session(credits=200)

    def test_request_success_debits_and_creates(self):
        r = self.s.post(f"{API}/giftcard/request", json={
            "brand": "amazon", "amount_credits": 25, "recipient_email": self.email,
        })
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["status"] == "pending"
        assert doc["brand"] == "amazon"
        assert doc["amount_usd"] == 25
        assert "id" in doc
        rid = doc["id"]

        # my-requests should list it with code redacted
        r2 = self.s.get(f"{API}/giftcard/my-requests")
        assert r2.status_code == 200
        items = r2.json()
        assert any(x["id"] == rid for x in items)
        for it in items:
            assert "code" not in it  # projected out

        # detail should hide code while pending
        r3 = self.s.get(f"{API}/giftcard/my-requests/{rid}")
        assert r3.status_code == 200
        assert r3.json().get("code") in (None, "")

        # me endpoint should reflect debit (200 - 25 = 175)
        me = self.s.get(f"{API}/auth/me").json()
        assert me.get("game_credits") == 175, f"expected 175, got {me.get('game_credits')}"


# --- Admin endpoints ------------------------------------------------------

class TestAdminGiftCardEndpoints:
    def setup_method(self):
        _set_flag("giftcard_redemption_enabled", True)
        self.user_s, self.user_email, self.uid = _new_user_session(credits=300)
        # Create a request as user
        r = self.user_s.post(f"{API}/giftcard/request", json={
            "brand": "xbox", "amount_credits": 30, "recipient_email": self.user_email,
        })
        assert r.status_code == 200, r.text
        self.rid = r.json()["id"]
        self.admin_s = _admin_session()

    def test_non_admin_forbidden_pending(self):
        r = self.user_s.get(f"{EXT_API}/giftcard/admin/pending")
        assert r.status_code in (401, 403), f"got {r.status_code}: {r.text}"

    def test_admin_pending_lists_request(self):
        r = self.admin_s.get(f"{EXT_API}/giftcard/admin/pending")
        assert r.status_code == 200, r.text
        items = r.json()
        assert any(x["id"] == self.rid for x in items)
        assert all(x["status"] == "pending" for x in items)

    def test_admin_fulfill_sets_code_and_user_can_view(self):
        code = f"TEST-CODE-{uuid.uuid4().hex[:8]}"
        r = self.admin_s.post(f"{EXT_API}/giftcard/admin/fulfill/{self.rid}",
                              json={"code": code, "notes": "test fulfill"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "fulfilled"

        # User should now see the code
        d = self.user_s.get(f"{API}/giftcard/my-requests/{self.rid}")
        assert d.status_code == 200
        body = d.json()
        assert body["status"] == "fulfilled"
        assert body["code"] == code

    def test_admin_reject_refunds_credits(self):
        # New request to reject
        r = self.user_s.post(f"{API}/giftcard/request", json={
            "brand": "spotify", "amount_credits": 20, "recipient_email": self.user_email,
        })
        assert r.status_code == 200, r.text
        rid2 = r.json()["id"]
        before = self.user_s.get(f"{API}/auth/me").json().get("game_credits")
        rej = self.admin_s.post(f"{EXT_API}/giftcard/admin/reject/{rid2}",
                                json={"reason": "test reject path"})
        assert rej.status_code == 200, rej.text
        body = rej.json()
        assert body["status"] == "rejected"
        assert body["refunded_credits"] == 20
        after = self.user_s.get(f"{API}/auth/me").json().get("game_credits")
        assert after == before + 20, f"refund mismatch before={before} after={after}"


# --- Launch checklist ----------------------------------------------------

class TestLaunchChecklist:
    def test_non_admin_forbidden(self):
        s, _, _ = _new_user_session()
        r = s.get(f"{EXT_API}/launch-checklist")
        assert r.status_code in (401, 403)

    def test_admin_returns_summary_and_six_checks(self):
        s = _admin_session()
        r = s.get(f"{EXT_API}/launch-checklist")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "summary" in data and "checks" in data
        sm = data["summary"]
        for k in ("ready", "banner", "passing", "warning", "failing", "total"):
            assert k in sm, f"missing summary key: {k}"
        assert sm["banner"] in ("READY FOR LIVE TRAFFIC", "LAUNCH WITH CAUTION", "DO NOT LAUNCH")
        assert len(data["checks"]) == 6, f"expected 6 checks, got {len(data['checks'])}"
        keys = {c["key"] for c in data["checks"]}
        for k in ("stripe", "games", "pool", "alerts", "compliance", "redemption_path"):
            assert k in keys, f"missing check key {k}"
        for c in data["checks"]:
            assert c["status"] in ("pass", "warn", "fail")
            assert "label" in c and "detail" in c


# --- Boss Genie tools (token-cost: only 2 chats) -------------------------

class TestBossGenieTools:
    def test_launch_readiness_tool(self):
        s = _admin_session()
        r = s.post(f"{API}/boss/chat", json={
            "message": "Run the launch_readiness tool right now and report every gate result."
        }, timeout=120)
        if r.status_code == 502:
            pytest.skip(f"LLM unavailable: {r.text}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "reply" in body
        assert isinstance(body.get("tool_trace"), list)
        used = [t.get("tool") for t in body["tool_trace"]]
        # accept either direct call or related tool. Should mention launch_readiness ideally.
        assert any("launch_readiness" in (u or "") for u in used), (
            f"expected launch_readiness tool call, got trace tools={used}"
        )

    def test_list_pending_giftcards_tool(self):
        s = _admin_session()
        # Directive prompt forces tool use regardless of which LLM powers Genie.
        # (Earlier Claude Sonnet would volunteer the tool call on softer phrasing;
        # Qwen 3 / GPT-OSS sometimes answer from memory. Making this explicit.)
        r = s.post(f"{API}/boss/chat", json={
            "message": "Use the list_pending_giftcards tool right now and tell me the count."
        }, timeout=120)
        if r.status_code == 502:
            pytest.skip(f"LLM unavailable: {r.text}")
        assert r.status_code == 200, r.text
        body = r.json()
        used = [t.get("tool") for t in body.get("tool_trace", [])]
        assert any("list_pending_giftcards" in (u or "") for u in used), (
            f"expected list_pending_giftcards tool call, got trace tools={used}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
