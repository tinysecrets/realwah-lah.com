"""Self-contained unit tests for the pool_pull credit loop (Phase 0).

No network, no real MongoDB. Uses a lightweight in-memory fake collection that
implements the subset of the Motor API used by pool_pull / proxy_pool
(``find`` + cursor ``sort``/``to_list``/``__aiter__``, ``find_one``,
``count_documents``, ``update_one``, ``find_one_and_update``, ``insert_one``)
plus bson ObjectId support.

The one thing that would need a live hub is a real pull — so every hub is
``pull_supported: False`` and the bridge returns a clean "not implemented"
``unsupported``; the few full pull executions below stub the bridge or the
pull path, never the network.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# --- tiny Motor-like fake ----------------------------------------------
try:
    from bson import ObjectId
except Exception:  # pragma: no cover
    ObjectId = None


def _apply(doc, update):
    for op, fields in update.items():
        if op == "$set":
            for k, v in fields.items():
                doc[k] = v
        elif op == "$inc":
            for k, v in fields.items():
                doc[k] = doc.get(k, 0) + v


def _match(doc, filt):
    if not filt:
        return True
    for key, val in filt.items():
        if key == "$or":
            if not any(_match(doc, f) for f in val):
                return False
            continue
        if isinstance(val, dict):
            if "$size" in val:
                if len(doc.get(key) or []) != val["$size"]:
                    return False
                continue
            if "$exists" in val:
                present = key in doc
                if present != bool(val["$exists"]):
                    return False
                continue
            if "$ne" in val:
                if doc.get(key) == val["$ne"]:
                    return False
                continue
            if "$gte" in val:
                if (doc.get(key) or "") < val["$gte"]:
                    return False
                continue
            if "$lte" in val:
                if (doc.get(key) or "") > val["$lte"]:
                    return False
                continue
        got = doc.get(key)
        if key == "_id" and got is not None:
            if str(got) != str(val):
                return False
        elif got != val:
            return False
    return True


class _Result:
    def __init__(self, matched=0, deleted=0):
        self.matched_count = matched
        self.modified_count = matched
        self.deleted_count = deleted


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)
        self._it = iter(self.docs)

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        return self.docs[:n]


class FakeColl:
    def __init__(self):
        self.docs = []

    def find(self, filt=None, projection=None):
        """Motor-style cursor factory — ``find()`` is synchronous, iteration is not."""
        return _Cursor([d for d in self.docs if _match(d, filt or {})])

    async def find_one(self, filt=None, projection=None):
        for d in self.docs:
            if _match(d, filt or {}):
                return d
        return None

    async def count_documents(self, filt=None):
        return sum(1 for d in self.docs if _match(d, filt or {}))

    async def update_one(self, filt, update, upsert=False):
        for d in self.docs:
            if _match(d, filt or {}):
                _apply(d, update)
                return _Result(1)
        if upsert:
            nd = dict(filt or {})
            self.docs.append(nd)
            return _Result(1)
        return _Result(0)

    async def find_one_and_update(self, filt, update, **kwargs):
        for d in self.docs:
            if _match(d, filt or {}):
                _apply(d, update)
                return d
        return None

    async def insert_one(self, doc):
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return _Result(1)

    async def delete_one(self, filt):
        for i, d in enumerate(self.docs):
            if _match(d, filt or {}):
                del self.docs[i]
                return _Result(1, deleted=1)
        return _Result(0)


class FakeDb(dict):
    def __init__(self):
        super().__init__()
        object.__setattr__(self, "_cols", {})

    def __getattr__(self, name):
        return self[name]

    def __getitem__(self, name):
        cols = object.__getattribute__(self, "_cols")
        return cols.setdefault(name, FakeColl())


# --- helpers ------------------------------------------------------------
def _iso(dt=None):
    return (dt or datetime.now(timezone.utc)).isoformat()


def _proxy(**over):
    doc = {
        "_id": ObjectId(),
        "label": "seat-1",
        "username": "op@x.com",
        "password_enc": "",
        "base_url": "https://sugarsweeps.com",
        "hub_type": "sugar_sweeps",
        "supported_platforms": ["fire_kirin"],
        "pull_supported": True,
        "status": "active",
        "balance_cached": 0.0,
        "daily_volume_sent": 0.0,
        "daily_cap": 5000.0,
        "per_transfer_cap": 500.0,
        "daily_reset_at": _iso(),
        "last_used_at": None,
        "consecutive_failures": 0,
        "cooldown_until": None,
        "lock_reason": None,
        "created_at": _iso(),
    }
    doc.update(over)
    return doc


# --- hub capability defaults ---------------------------------------------
def test_hub_registry_pull_supported_defaults_off():
    from services.hub_registry import HUB_CONFIGS, list_hubs

    for name, hub in HUB_CONFIGS.items():
        assert hub.get("pull_supported") is False, name
    for hub in list_hubs():
        assert hub["pull_supported"] is False


def test_hub_pull_supported_resolution():
    from services import proxy_pool

    assert proxy_pool.hub_pull_supported({"hub_type": "sugar_sweeps"}) is False
    assert (
        proxy_pool.hub_pull_supported({"hub_type": "sugar_sweeps", "pull_supported": True})
        is True
    )
    assert (
        proxy_pool.hub_pull_supported({"hub_type": "sugar_sweeps", "pull_supported": False})
        is False
    )


def test_public_view_exposes_pull_supported():
    from services import proxy_pool

    v = proxy_pool.public_view(_proxy(pull_supported=True))
    assert v["pull_supported"] is True


# --- bridge pull ---------------------------------------------------------
def test_http_pull_unsupported_without_path():
    from services.hub_http_bridge import HttpHubBridge

    async def _t():
        b = HttpHubBridge("bitbetwin", "op@x.com", "pw")
        ok, msg, _ = await b.pull("player@x.com", 25, "juwa")
        return ok, msg

    ok, msg = asyncio.run(_t())
    assert ok is False
    assert "not implemented" in msg.lower()


def test_build_pull_body_flat_shape():
    from services.hub_http_bridge import HttpHubBridge

    b = HttpHubBridge("sugar_sweeps", "op@x.com", "pw")
    body = b._build_pull_body("gameuser", 12.0, "fire_kirin")
    assert body == {"username": "gameuser", "amount": 12, "platform": "fire_kirin"}


def test_build_pull_body_cart_hub_keeps_amount_platform():
    from services.hub_http_bridge import HttpHubBridge

    b = HttpHubBridge("bitbetwin", "op@x.com", "pw")
    body = b._build_pull_body("player@x.com", 10.0, "juwa")
    assert body["amount"] == 10
    assert body["platform"] == "juwa"


def test_http_pull_uses_configured_path_and_body(monkeypatch):
    from services.hub_http_bridge import HttpHubBridge

    class _Resp:
        status_code = 200
        text = '{"ok":true}'

    class _Client:
        def __init__(self):
            self.posts = []

        async def post(self, url, json=None, headers=None):
            self.posts.append((url, json, headers))
            return _Resp()

    async def _run():
        b = HttpHubBridge("sugar_sweeps", "op@x.com", "pw")
        try:
            b.api_paths["pull"] = "/api/P2PTransfers/pull"
            client = _Client()

            async def _get_client():
                return client

            async def _ping():
                return True, "ok", b.diagnostic

            monkeypatch.setattr(b, "_get_client", _get_client)
            monkeypatch.setattr(b, "ping", _ping)
            ok, msg, _ = await b.pull("gameuser", 40, "fire_kirin")
            return ok, msg, client.posts
        finally:
            b.api_paths.pop("pull", None)

    ok, msg, posts = asyncio.run(_run())
    assert ok is True
    assert len(posts) == 1
    url, body, headers = posts[0]
    assert url == "https://sugarsweeps.com/api/proxy/api/P2PTransfers/pull"
    assert headers["Authorization"] == "Bearer None" or "Bearer" in headers["Authorization"]
    assert body == {"username": "gameuser", "amount": 40, "platform": "fire_kirin"}


def test_http_pull_aborts_when_ping_fails(monkeypatch):
    from services.hub_http_bridge import HttpHubBridge

    async def _run():
        b = HttpHubBridge("bitbetwin", "op@x.com", "pw")
        try:
            monkeypatch.setattr(b, "api_paths", {"pull": "/api/orders/pull"})
            client_spy = []

            async def _get_client():
                client_spy.append(1)
                return None

            async def _ping():
                return False, "Auth rejected (401)", b.diagnostic

            monkeypatch.setattr(b, "_get_client", _get_client)
            monkeypatch.setattr(b, "ping", _ping)
            ok, msg, _ = await b.pull("player@x.com", 10, "juwa")
            return ok, msg, len(client_spy)
        finally:
            pass

    ok, msg, posts = asyncio.run(_run())
    assert ok is False
    assert "401" in msg
    assert posts == 0


def test_build_pull_body_flat_shape():
    from services.hub_http_bridge import HttpHubBridge

    b = HttpHubBridge("sugar_sweeps", "op@x.com", "pw")
    body = b._build_pull_body("gameuser", 12.0, "fire_kirin")
    assert body == {"username": "gameuser", "amount": 12, "platform": "fire_kirin"}


def test_build_pull_body_cart_hub_keeps_amount_platform():
    from services.hub_http_bridge import HttpHubBridge

    b = HttpHubBridge("bitbetwin", "op@x.com", "pw")
    body = b._build_pull_body("player@x.com", 10.0, "juwa")
    assert body["amount"] == 10
    assert body["platform"] == "juwa"


def test_generic_bridge_pull_unsupported():
    from services.hub_bridge import GenericHubBridge

    async def _t():
        b = GenericHubBridge("bitplay", "u", "p")
        ok, msg, _ = await b.pull("p", 10, "fire_kirin")
        return ok, msg

    ok, msg = asyncio.run(_t())
    assert ok is False
    assert "not implemented" in msg.lower()


# --- select_proxy require_pull -------------------------------------------
def test_select_proxy_require_pull_filters():
    from services import proxy_pool

    db = FakeDb()
    db[proxy_pool.COLLECTION].docs = [
        _proxy(label="no-pull", pull_supported=False),
        _proxy(label="pull", pull_supported=True),
        _proxy(label="pull2", pull_supported=True),
    ]

    async def _t():
        return await proxy_pool.select_proxy(db, 50, platform="fire_kirin", require_pull=True)

    p, reason = asyncio.run(_t())
    assert p is not None
    assert p["label"] in ("pull", "pull2")
    assert reason == "selected"


def test_select_proxy_require_pull_none_available():
    from services import proxy_pool

    db = FakeDb()
    db[proxy_pool.COLLECTION].docs = [
        _proxy(label="no-pull", pull_supported=False),
    ]

    async def _t():
        return await proxy_pool.select_proxy(db, 50, platform="fire_kirin", require_pull=True)

    p, reason = asyncio.run(_t())
    assert p is None
    assert "pull" in reason.lower()


# --- execute_pool_pull ---------------------------------------------------
@pytest.fixture()
def pool_env(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("PROXY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("POOL_PULL_ENABLED", raising=False)
    return


def test_execute_pool_pull_done_path(monkeypatch, pool_env):
    from routes.distributor_pool import execute_pool_pull
    from services import pool_pull, proxy_pool
    from services.crypto_vault import encrypt
    import services.hub_bridge as hb_mod

    class _FakeBridge:
        def __init__(self):
            self.closed = False
            self.pulled = None

        async def pull(self, **kw):
            self.pulled = kw
            return True, "Pull OK (HTTP 200)", {}

        async def close(self):
            self.closed = True

    fake = _FakeBridge()

    def _fake_make_bridge(**kw):
        return fake

    monkeypatch.setattr(hb_mod, "make_bridge", _fake_make_bridge)

    db = FakeDb()
    db[proxy_pool.COLLECTION].docs = [
        _proxy(password_enc=encrypt("pw"), pull_supported=True),
    ]

    async def _t():
        return await execute_pool_pull(
            db, recipient_username="gameuser", amount=50, platform="fire_kirin",
            ref_kind="redemption", ref_id="rx1", user_id="u1",
        )

    ok, msg, detail = asyncio.run(_t())
    assert ok is True
    assert detail["pull_status"] == "done"
    assert fake.closed is True
    assert fake.pulled == {"recipient": "gameuser", "amount": 50, "platform": "fire_kirin"}

    proxy = db[proxy_pool.COLLECTION].docs[0]
    assert proxy["daily_volume_sent"] == 0.0        # pull is not outbound volume
    assert proxy.get("consecutive_failures", 0) == 0

    logs = db["pool_pulls"].docs
    assert len(logs) == 1
    assert logs[0]["status"] == "done"
    assert logs[0]["ref_id"] == "rx1"
    assert logs[0]["user_id"] == "u1"
    assert logs[0]["proxy_id"] == detail["proxy_id"]
    assert detail["pull_log_id"] == logs[0]["id"]


def test_execute_pool_pull_skipped_when_no_pull_seat(pool_env):
    from routes.distributor_pool import execute_pool_pull
    from services import proxy_pool

    db = FakeDb()
    db[proxy_pool.COLLECTION].docs = [
        _proxy(password_enc="", pull_supported=False),
    ]

    async def _t():
        return await execute_pool_pull(
            db, recipient_username="gameuser", amount=50, platform="fire_kirin",
        )

    ok, msg, detail = asyncio.run(_t())
    assert ok is False
    assert detail["pull_status"] == "skipped"
    assert "pull" in msg.lower()
    assert "pool_pulls" not in db  # no attempt recorded


# --- run_redemption_pull ------------------------------------------------
def test_run_redemption_pull_skips_without_funded_platform(pool_env):
    from services import pool_pull

    db = FakeDb()
    db.redemption_requests.docs = [{"id": "rx1", "game_credits": 500}]
    user = {"_id": "u1", "game_username": "sugarabc123"}

    res = asyncio.run(
        pool_pull.run_redemption_pull(db, {"id": "rx1", "game_credits": 500}, user)
    )
    assert res["status"] == "skipped_no_platform"
    assert res["reason"] == "no_funded_platform"

    red = db.redemption_requests.docs[0]
    assert red["pool_pull_status"] == "skipped_no_platform"
    assert red["pool_pull_message"] == "no_funded_platform"
    assert red["pool_pull_started_at"]

    logs = db["pool_pulls"].docs
    assert len(logs) == 1
    assert logs[0]["status"] == "skipped_no_platform"


def test_run_redemption_pull_unsupported_without_pull_endpoint(pool_env):
    from services import pool_pull, proxy_pool
    from services.crypto_vault import encrypt

    db = FakeDb()
    db.redemption_requests.docs = [{"id": "rx2", "game_credits": 500}]
    db.btc_deposits.docs = [
        {"user_id": "u1", "status": "completed", "platform": "fire_kirin",
         "completed_at": "2026-01-01T00:00:00+00:00"},
    ]
    db[proxy_pool.COLLECTION].docs = [
        _proxy(label="pull-seat", password_enc=encrypt("pw"), pull_supported=True),
    ]
    user = {"_id": "u1", "game_username": "sugarabc123"}

    res = asyncio.run(
        pool_pull.run_redemption_pull(db, {"id": "rx2", "game_credits": 500}, user)
    )
    assert res["status"] == "unsupported"
    assert "not implemented" in res["message"].lower()

    red = db.redemption_requests.docs[0]
    assert red["pool_pull_status"] == "unsupported"
    assert red["pool_pull_detail"]["pull_status"] == "unsupported"

    # Seat was NOT punished — unsupported capability is not a seat failure.
    proxy = db[proxy_pool.COLLECTION].docs[0]
    assert proxy.get("consecutive_failures", 0) == 0

    logs = db["pool_pulls"].docs
    assert len(logs) == 1
    assert logs[0]["status"] == "unsupported"
    assert logs[0]["recipient_username"] == "sugarabc123"
    assert logs[0]["platform"] == "fire_kirin"


# --- dispatch gate -------------------------------------------------------
def test_dispatch_redemption_pull_gated_by_flag(monkeypatch):
    from services import pool_pull

    db = FakeDb()
    db.redemption_requests.docs = [{"id": "rx3", "game_credits": 100}]
    user = {"_id": "u1", "game_username": "sugarabc123"}
    redemption = {"id": "rx3", "game_credits": 100}

    monkeypatch.setenv("POOL_PULL_ENABLED", "false")
    assert pool_pull.dispatch_redemption_pull(db, redemption, user) is None

    monkeypatch.setenv("POOL_PULL_ENABLED", "1")
    async def _t():
        task = pool_pull.dispatch_redemption_pull(db, redemption, user)
        assert task is not None
        try:
            return await task
        finally:
            task.cancel()

    res = asyncio.run(_t())
    assert res["status"] == "skipped_no_platform"


def test_dispatch_redemption_pull_requires_known_user(monkeypatch):
    from services import pool_pull

    db = FakeDb()
    monkeypatch.setenv("POOL_PULL_ENABLED", "1")
    assert (
        pool_pull.dispatch_redemption_pull(db, {"id": "rx-x", "game_credits": 1}, {})
        is None
    )
    assert (
        pool_pull.dispatch_redemption_pull(db, {"id": "rx-x", "game_credits": 1}, None)
        is None
    )


def test_safe_run_turns_crash_into_failed_status(monkeypatch):
    from services import pool_pull

    async def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(pool_pull, "run_redemption_pull", _boom)

    db = FakeDb()
    db.redemption_requests.docs = [{"id": "rx-crash", "game_credits": 10}]

    res = asyncio.run(
        pool_pull._safe_run(db, {"id": "rx-crash", "game_credits": 10}, {"_id": "u1"})
    )
    assert res["status"] == "failed"
    assert "crash" in res["message"]
    red = db.redemption_requests.docs[0]
    assert red["pool_pull_status"] == "failed"
    assert "crash" in red["pool_pull_message"]


# --- rebalancer: balance floor + capacity alert --------------------------
def test_pool_health_enforces_balance_floor(monkeypatch):
    from services import proxy_pool

    db = FakeDb()
    db[proxy_pool.COLLECTION].docs = [
        _proxy(label="low", status="active", balance_cached=30.0),   # below floor
        _proxy(label="fine", status="active", balance_cached=500.0),
        _proxy(label="unknown", status="active", balance_cached=0.0),  # untouched
        _proxy(pull_supported=True, label="disabled-already", status="disabled", balance_cached=10.0),
    ]
    health = asyncio.run(proxy_pool.pool_health(db))
    assert health["balance_floor"] == 50.0
    # low was disabled by the enforcement pass, so no active seat is *left* below floor
    assert health["active_below_floor"] == 0
    assert len(health["disabled_below_floor_ids"]) == 1
    # low was disabled; fine + unknown still active
    assert health["disabled_below_floor_ids"] == [str(db[proxy_pool.COLLECTION].docs[0]["_id"])]
    statuses = {d["label"]: d["status"] for d in db[proxy_pool.COLLECTION].docs}
    assert statuses["low"] == "disabled"
    assert statuses["fine"] == "active"
    assert statuses["unknown"] == "active"


def test_capacity_alert_fires_once_per_day(monkeypatch):
    from services import proxy_pool

    db = FakeDb()
    docs = []

    def _fake_insert(doc):
        docs.append(doc)
        return type("R", (), {"inserted_id": doc.get("id")})()

    async def _fake_find_one(filt=None, projection=None):
        for d in docs:
            if all(d.get(k) == filt[k] for k in filt or {}):
                return d
        return None

    async def _fake_insert_one(doc):
        _fake_insert(doc)

    monkeypatch.setattr(db["admin_alerts"], "insert_one", _fake_insert_one)
    monkeypatch.setattr(db["admin_alerts"], "find_one", _fake_find_one)

    health = {
        "active": 2,
        "daily_capacity_total": 10000.0,
        "daily_capacity_remaining_pct": 12.5,
    }
    r1 = asyncio.run(proxy_pool.maybe_emit_capacity_alert(db, health))
    assert r1["alerted"] is True
    assert len(docs) == 1
    assert docs[0]["type"] == "pool_capacity"
    assert docs[0]["status"] == "open"
    assert docs[0]["daily_capacity_remaining_pct"] == 12.5

    r2 = asyncio.run(proxy_pool.maybe_emit_capacity_alert(db, health))
    assert r2["alerted"] is False
    assert r2["reason"] == "already_open_today"
    assert len(docs) == 1

    healthy = dict(health, daily_capacity_remaining_pct=75.0)
    r3 = asyncio.run(proxy_pool.maybe_emit_capacity_alert(db, healthy))
    assert r3["alerted"] is False
    assert r3["reason"] == "above_threshold"


# --- KPI ------------------------------------------------------------------
def test_pool_pull_kpis_aggregates():
    from services import pool_pull

    db = FakeDb()
    now = datetime.now(timezone.utc)
    db.redemption_requests.docs = [
        {"game_credits": 20, "created_at": now.isoformat()},
        {"game_credits": 30, "created_at": now.isoformat()},
    ]
    db[pool_pull.POOL_PULL_COLLECTION].docs = [
        {"ref_kind": "redemption", "status": "done", "amount": 10, "created_at": now.isoformat()},
        {"ref_kind": "redemption", "status": "failed", "amount": 15, "created_at": now.isoformat()},
        {"ref_kind": "redemption", "status": "unsupported", "amount": 25, "created_at": now.isoformat()},
        {"ref_kind": "redemption", "status": "skipped_no_platform", "amount": 9, "created_at": now.isoformat()},
        {"ref_kind": "redemption", "status": "done", "amount": 500, "created_at": (now - timedelta(hours=48)).isoformat()},
    ]
    kpis = asyncio.run(pool_pull.pool_pull_kpis(db, window_hours=24))
    assert kpis["redemption_credits"] == 50.0
    assert kpis["pull_attempted_credits"] == 50.0   # 10+15+25; skipped + stale excluded
    assert kpis["pull_done_credits"] == 10.0
    assert kpis["pull_success_rate"] == 0.2
    assert kpis["recycled_credit_ratio"] == 0.2
    assert kpis["window_hours"] == 24


# --- rebalancer: sweep-to-lowest (playbook rule a) -------------------------
def test_sweep_plans_move_surplus_to_lowest_seat(monkeypatch):
    monkeypatch.delenv("POOL_REBALANCE_ENABLED", raising=False)
    from services import proxy_pool

    db = FakeDb()
    db[proxy_pool.COLLECTION].docs = [
        _proxy(label="a-rich", balance_cached=1000.0),
        _proxy(label="b-mid", balance_cached=300.0),
        _proxy(label="c-poor", balance_cached=50.0),
    ]
    plan = asyncio.run(proxy_pool.sweep_credits_to_lowest(db, dry_run=True))
    assert plan["dry_run"] is True
    assert plan["enabled"] is False
    assert len(plan["planned"]) == 2
    # every plan row targets the single lowest seat (c-poor)
    assert {p["target_label"] for p in plan["planned"]} == {"c-poor"}
    # surplus = source_balance - target_balance - margin(25); don't exceed per-cap
    row = plan["planned"][0]
    assert row["amount"] > 0
    assert row["amount"] <= 500.0  # per_transfer_cap
    assert plan["executed"] == []
    assert plan["failed"] == []


def test_sweep_needs_two_known_balance_seats(monkeypatch):
    monkeypatch.delenv("POOL_REBALANCE_ENABLED", raising=False)
    from services import proxy_pool

    db = FakeDb()
    db[proxy_pool.COLLECTION].docs = [
        _proxy(label="sole-seat", balance_cached=1000.0),
    ]
    plan = asyncio.run(proxy_pool.sweep_credits_to_lowest(db, dry_run=True))
    assert plan["planned"] == []
    assert any("only one" in s for s in plan["skipped"])


def test_sweep_leaves_unknown_balances_untouched(monkeypatch):
    monkeypatch.delenv("POOL_REBALANCE_ENABLED", raising=False)
    from services import proxy_pool

    db = FakeDb()
    db[proxy_pool.COLLECTION].docs = [
        _proxy(label="known-rich", balance_cached=1000.0),
        _proxy(label="unknown-zero", balance_cached=0.0),
        _proxy(label="unknown-missing", balance_cached=None),
        _proxy(label="lowest-known", balance_cached=40.0),
    ]
    plan = asyncio.run(proxy_pool.sweep_credits_to_lowest(db, dry_run=True))
    labels = {p["source_label"] for p in plan["planned"]}
    assert labels == {"known-rich"}  # unknown seats are not sweep sources
    assert plan["planned"][0]["target_label"] == "lowest-known"


def test_sweep_gated_off_by_default_no_transfers(monkeypatch):
    monkeypatch.delenv("POOL_REBALANCE_ENABLED", raising=False)
    from services import proxy_pool

    db = FakeDb()
    db[proxy_pool.COLLECTION].docs = [
        _proxy(label="a-rich", balance_cached=1000.0),
        _proxy(label="b-poor", balance_cached=40.0),
    ]
    result = asyncio.run(proxy_pool.run_rebalance(db, dry_run=False))
    assert result["sweep"]["enabled"] is False
    assert result["sweep"]["executed"] == []
    assert result["sweep"]["failed"] == []


def test_rebalance_runs_floor_then_sweep_and_alert(monkeypatch):
    monkeypatch.delenv("POOL_REBALANCE_ENABLED", raising=False)
    from services import proxy_pool

    db = FakeDb()
    db[proxy_pool.COLLECTION].docs = [
        _proxy(label="under-floor", balance_cached=20.0),
        _proxy(title="x", label="rich", balance_cached=1000.0),
        _proxy(label="poor", balance_cached=100.0),
    ]
    result = asyncio.run(proxy_pool.run_rebalance(db, dry_run=True))
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert len(result["disabled_below_floor_ids"]) == 1
    statuses = {d["label"]: d["status"] for d in db[proxy_pool.COLLECTION].docs}
    assert statuses["under-floor"] == "disabled"
    assert len(result["sweep"]["planned"]) == 1
    assert result["sweep"]["planned"][0]["target_label"] == "poor"


def test_sweep_executes_transfer_and_audits(pool_env, monkeypatch):
    """Real (non-dry-run) sweep moves credits and leaves a pool_sweeps trail."""
    monkeypatch.setenv("POOL_REBALANCE_ENABLED", "true")
    from services import proxy_pool
    from services.crypto_vault import encrypt
    import services.hub_bridge as hb_mod

    transferred = {}

    class _FakeBridge:
        def __init__(self):
            self.closed = False

        async def transfer(self, **kw):
            transferred.update(kw)
            return True, "Transfer OK", {}

        async def close(self):
            self.closed = True

    fake = _FakeBridge()
    monkeypatch.setattr(hb_mod, "make_bridge", lambda **kw: fake)

    db = FakeDb()
    db[proxy_pool.COLLECTION].docs = [
        _proxy(label="rich", balance_cached=1000.0, password_enc=encrypt("pw")),
        _proxy(label="poor", balance_cached=100.0, password_enc=encrypt("pw")),
    ]
    result = asyncio.run(proxy_pool.sweep_credits_to_lowest(db, dry_run=False))
    assert result["enabled"] is True
    assert result["dry_run"] is False
    assert len(result["executed"]) == 1
    assert result["failed"] == []
    # credited balance was moved: rich pays down, poor fills up
    balances = {d["label"]: d["balance_cached"] for d in db[proxy_pool.COLLECTION].docs}
    assert balances["rich"] < 1000.0
    assert balances["poor"] > 100.0
    # audit trail exists in pool_sweeps
    logs = db["pool_sweeps"].docs
    assert len(logs) == 1
    assert logs[0]["type"] == "rebalance"
    assert logs[0]["ok"] is True
    assert transferred["amount"] == result["executed"][0]["amount"]
    assert fake.closed is True

    # cleanup: POOL_REBALANCE_ENABLED is stale now; remove to avoid cross-test leakage
    monkeypatch.delenv("POOL_REBALANCE_ENABLED")