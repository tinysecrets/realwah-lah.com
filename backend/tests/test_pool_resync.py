"""Self-contained unit tests for the pool resync worker (nightly balance refresh).

No network, no real MongoDB, no Playwright. Uses a lightweight in-memory fake
collection like ``test_pool_pull.py``. Bridge reads are replaced entirely by a
stub with scripted ``(ok, balance, diag)`` results so the pass logic (done /
failed / unsupported classification, mark_failed attribution, no-clobber on
unknown, dry-run rebalance after the pass) is exercised deterministically.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --- tiny Motor-like fake ----------------------------------------------
def _match(doc, filt):
    if not filt:
        return True
    for key, val in filt.items():
        if isinstance(val, dict) and "$in" in val:
            if doc.get(key) not in val["$in"]:
                return False
            continue
        if key == "$in":
            if doc.get("status") not in val:
                return False
            continue
        got = doc.get(key)
        if key == "_id" and got is not None:
            if str(got) != str(val):
                return False
        elif got != val:
            return False
    return True


def _apply(doc, update):
    for op, fields in update.items():
        if op == "$set":
            for k, v in fields.items():
                if v is not None:
                    doc[k] = v
                else:  # $set None explodes on Mongo; emulate a delete
                    doc.pop(k, None)
        elif op == "$inc":
            for k, v in fields.items():
                doc[k] = doc.get(k, 0) + v


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

    def sort(self, key_or_tuple, direction: int = 1):
        if isinstance(key_or_tuple, tuple):
            key, direction = key_or_tuple[0], key_or_tuple[1]
        self.docs.sort(key=lambda d: str(d.get(key) or ""), reverse=(direction == -1))
        return self

    async def to_list(self, n=None):
        return self.docs[:] if n is None else self.docs[:n]


class FakeColl:
    def __init__(self):
        self.docs = []

    def find(self, filt=None, projection=None):
        return _Cursor([d for d in self.docs if _match(d, filt or {})])

    async def find_one(self, filt=None, projection=None):
        for d in self.docs:
            if _match(d, filt or {}):
                return d
        return None

    async def update_one(self, filt, update):
        for d in self.docs:
            if _match(d, filt):
                _apply(d, update)
                return
        return None

    async def insert_one(self, doc):
        self.docs.append(doc)
        return {"inserted_id": doc.get("_id")}


class FakeDB(dict):
    def __missing__(self, key):
        coll = FakeColl()
        self[key] = coll
        return coll


# --- scripted bridge stub ----------------------------------------------
class FakeBridge:
    def __init__(self, result):
        self._result = result
        self.closed = False

    async def get_balance(self):
        return self._result

    async def close(self):
        self.closed = True


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def patch_io(monkeypatch):
    """Replace decryption + bridge factory + rebalancer with injectables.

    ``results`` is a list of ``(ok, balance, diag)`` tuples consumed in seat
    lookup order (same order as `distributor_proxies` insertion).
    """

    def _install(results=None, rebalance=None):
        import services.pool_resync as pr

        script = iter(results or [])

        async def fake_creds(db, proxy_id):
            return {"username": "u", "password": "p", "base_url": "https://hub.test"}

        def fake_bridge(hub_type, username, password, base_url):
            try:
                result = next(script)
            except StopIteration:
                result = (True, 100.0, {"balance_supported": True, "steps": []})
            return FakeBridge(result)

        calls = {"mark_failed": [], "rebalance": []}

        async def fake_mark_failed(db, pid, reason):
            calls["mark_failed"].append((str(pid), str(reason)))

        async def fake_rebalance(db, dry_run=True):
            calls["rebalance"].append({"dry_run": dry_run})
            return {"ok": True, "dry_run": dry_run, "plan": []}

        monkeypatch.setattr(pr, "get_decrypted_credentials", fake_creds)
        monkeypatch.setattr(pr, "make_bridge", fake_bridge)
        monkeypatch.setattr(pr, "mark_failed", fake_mark_failed)
        monkeypatch.setattr(pr, "run_rebalance", rebalance or fake_rebalance)
        return calls

    return _install


def _make_proxy(_id, status="active", balance=0.0, label="seat"):
    return {
        "_id": _id,
        "id": _id,
        "label": label,
        "hub_type": "sugar_sweeps",
        "status": status,
        "balance_cached": balance,
        "consecutive_failures": 0,
    }


# =========================================================
# parse_money
# =========================================================
class TestParseMoney:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("$1,234.56", 1234.56),
            ("Balance: $75.50 CAD", 75.5),
            ("0", 0.0),
            ("123", 123.0),
            ("25.00", 25.0),
        ],
    )
    def test_valid(self, raw, expected):
        from services.hub_bridge import parse_money

        assert parse_money(raw) == expected

    @pytest.mark.parametrize("raw", ["", "abc", "N/A", "-5", "   ", None])
    def test_invalid(self, raw):
        from services.hub_bridge import parse_money

        assert parse_money(raw) is None


# =========================================================
# Bridge unsupported detection (no balance endpoint configured)
# =========================================================
class TestBridgeUnsupported:
    def test_generic_bridge_no_selector(self):
        from services.hub_bridge import GenericHubBridge

        bridge = GenericHubBridge("sugar_sweeps", "u", "p")
        # Simulate a hub with no balance selector (mutation must not touch the
        # shared registry dict, so copy).
        bridge.hub = {
            **bridge.hub,
            "selectors": {**bridge.hub.get("selectors", {}), "balance": []},
        }
        ok, value, diag = asyncio.run(bridge.get_balance())
        assert ok is False
        assert value is None
        assert diag["balance_supported"] is False

    def test_http_bridge_no_balance_path(self):
        from services.hub_http_bridge import HttpHubBridge

        bridge = HttpHubBridge("sugar_sweeps", "u", "p")
        ok, value, diag = asyncio.run(bridge.get_balance())
        assert ok is False
        assert value is None
        assert diag["balance_supported"] is False


# =========================================================
# Resync pass logic
# =========================================================
class TestResyncPass:
    def test_done_refreshes_balance_and_reactivates(self, fake_db, patch_io):
        from services import pool_resync as pr

        fake_db["distributor_proxies"].docs.extend([
            _make_proxy("p1", status="active", balance=0.0),
            _make_proxy("p2", status="cooldown", balance=99.0),
        ])
        calls = patch_io([
            (True, 250.0, {"balance_supported": True, "steps": []}),
            (True, 1250.5, {"balance_supported": True, "steps": []}),
        ])

        summary = asyncio.run(pr.resync_seat_balances(fake_db))

        assert summary["seats"] == 2
        assert summary["read"] == 2 and summary["failed"] == 0 and summary["unsupported"] == 0
        assert summary["cached_balance_total"] == 1500.5
        assert calls["mark_failed"] == []

        p1 = fake_db["distributor_proxies"].docs[0]
        assert p1["balance_cached"] == 250.0 and p1["status"] == "active"
        assert p1.get("cooldown_until") is None and p1["consecutive_failures"] == 0
        p2 = fake_db["distributor_proxies"].docs[1]
        assert p2["balance_cached"] == 1250.5 and p2["status"] == "active"

        # Audit row written to pool_resyncs.
        rows = fake_db["pool_resyncs"].docs
        assert len(rows) == 1
        assert len(rows[0]["results"]) == 2

        # Post-pass dry-run rebalance ran by default.
        assert calls["rebalance"] == [{"dry_run": True}]

    def test_failed_attributes_and_keeps_old_balance(self, fake_db, patch_io):
        from services import pool_resync as pr

        fake_db["distributor_proxies"].docs.extend([
            _make_proxy("p1", status="active", balance=0.0),
            _make_proxy("p2", status="active", balance=555.0),
        ])
        calls = patch_io([
            (False, "login rejected", {"balance_supported": True, "steps": []}),
            (False, None, {"balance_supported": True, "steps": [{"step": "balance_get", "error": "boom"}]}),
        ])

        summary = asyncio.run(pr.resync_seat_balances(fake_db))

        assert summary["failed"] == 2 and summary["read"] == 0
        assert len(calls["mark_failed"]) == 2
        assert "balance read failed: login rejected" in calls["mark_failed"][0][1]
        assert "boom" in calls["mark_failed"][1][1]

        # Old cached balances untouched on failure.
        assert fake_db["distributor_proxies"].docs[0]["balance_cached"] == 0.0
        assert fake_db["distributor_proxies"].docs[1]["balance_cached"] == 555.0

    def test_unsupported_not_a_failure(self, fake_db, patch_io):
        from services import pool_resync as pr

        fake_db["distributor_proxies"].docs.append(
            _make_proxy("p1", status="active", balance=0.0)
        )
        calls = patch_io([
            (False, None, {"balance_supported": False, "steps": []}),
        ])

        summary = asyncio.run(pr.resync_seat_balances(fake_db))

        assert summary["unsupported"] == 1 and summary["failed"] == 0
        assert calls["mark_failed"] == []
        # 0.0 stays 0.0 = "unknown", NOT marked failed/locked, failures not bumped.
        assert fake_db["distributor_proxies"].docs[0]["balance_cached"] == 0.0
        assert fake_db["distributor_proxies"].docs[0]["consecutive_failures"] == 0

    def test_rebalance_skipped_when_disabled(self, fake_db, patch_io, monkeypatch):
        from services import pool_resync as pr

        monkeypatch.setenv("POOL_RESYNC_RUN_REBALANCE", "false")
        fake_db["distributor_proxies"].docs.append(_make_proxy("p1", status="active"))
        calls = patch_io([
            (True, 100.0, {"balance_supported": True, "steps": []}),
        ])

        summary = asyncio.run(pr.resync_seat_balances(fake_db))
        assert summary["read"] == 1
        assert calls["rebalance"] == []

    def test_no_seats_is_graceful(self, fake_db, patch_io):
        from services import pool_resync as pr

        calls = patch_io()
        summary = asyncio.run(pr.resync_seat_balances(fake_db))
        assert summary["seats"] == 0 and summary["read"] == 0
        assert calls["rebalance"] == [{"dry_run": True}]


# =========================================================
# Worker scheduling / env knobs
# =========================================================
class TestWorker:
    def test_defaults_on_when_env_absent(self, monkeypatch):
        from services import pool_resync as pr

        monkeypatch.delenv("POOL_RESYNC_ENABLED", raising=False)
        monkeypatch.delenv("POOL_RESYNC_INTERVAL_MIN", raising=False)
        w = pr.PoolResyncWorker(FakeDB())
        assert w.enabled is True
        assert w._interval == 1440 * 60

    def test_interval_floor(self, monkeypatch):
        from services import pool_resync as pr

        monkeypatch.setenv("POOL_RESYNC_INTERVAL_MIN", "1")
        w = pr.PoolResyncWorker(FakeDB())
        assert w._interval == 3600

    def test_disabled_start_does_not_task(self, monkeypatch):
        from services import pool_resync as pr

        monkeypatch.setenv("POOL_RESYNC_ENABLED", "false")
        w = pr.PoolResyncWorker(FakeDB())
        w.start()
        assert w._task is None

    def test_start_creates_running_task(self, monkeypatch):
        from services import pool_resync as pr

        monkeypatch.delenv("POOL_RESYNC_ENABLED", raising=False)
        monkeypatch.setenv("POOL_RESYNC_INTERVAL_MIN", "1440")

        async def _scenario():
            w = pr.PoolResyncWorker(FakeDB())
            w.start()
            assert w._task is not None and not w._task.done()
            w._task.cancel()
            try:
                await w._task
            except asyncio.CancelledError:
                pass

        asyncio.run(_scenario())