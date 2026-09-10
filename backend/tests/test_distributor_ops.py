"""Self-contained unit + route tests for the distributor-operator core.

Covers the newly built money surface (no live backend needed):
- POST /api/admin/cashtag/reconcile — fee split, credit NET, ledger row,
  receipt idempotency, manual-mode queue dispatch, whale comp
- GET/PATCH /api/admin/users — safe projection, audited adjustments
- GET /api/admin/transactions — unified feed
- GET /api/admin/stats — morning-glance shape
- GET /api/payment/card-info — disclosure + disabled state
- Queue lifecycle — retry failed -> awaiting, cancel terminal, overdue math

Registered in conftest.SELF_CONTAINED_FILES so it always runs in CI.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services import revenue as revenue_engine
from services import self_distributor as sd
from services.currency_service import CurrencyService
from routes.distributor_admin import build_distributor_admin_router
from routes.payment import build_payment_router


def run(awaitable):
    return asyncio.run(awaitable)


# --------------------------------------------------------------------------
# Fake async mongo
# --------------------------------------------------------------------------
class FakeResult:
    def __init__(self, modified_count=0, upserted_id=None, inserted_id=None):
        self.modified_count = modified_count
        self.upserted_id = upserted_id
        self.inserted_id = inserted_id


def _matches(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    for k, v in query.items():
        if k == "$or":
            if not any(_matches(doc, sub) for sub in v):
                return False
            continue
        if isinstance(v, dict) and any(str(op).startswith("$") for op in v):
            for op, ov in v.items():
                if op in ("$regex", "$options"):
                    continue
                if op == "$ne":
                    if doc.get(k) == ov:
                        return False
                elif op == "$exists":
                    if (k in doc) != bool(ov):
                        return False
                elif op == "$gte":
                    if k not in doc or doc[k] < ov:
                        return False
                elif op == "$lte":
                    if k not in doc or doc[k] > ov:
                        return False
                elif op == "$gt":
                    if k not in doc or doc[k] <= ov:
                        return False
                elif op == "$lt":
                    if k not in doc or doc[k] >= ov:
                        return False
                elif op == "$in":
                    if doc.get(k) not in ov:
                        return False
                else:
                    return False
            # $regex handled alongside $options in the same dict
            if "$regex" in v:
                flags = re.IGNORECASE if "i" in str(v.get("$options", "")) else 0
                if not re.search(v["$regex"], str(doc.get(k) or ""), flags):
                    return False
            continue
        if k == "_id":
            if str(doc.get("_id")) != str(v) and doc.get("_id") != v:
                return False
        elif k not in doc or doc[k] != v:
            return False
    return True


class FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs

    def sort(self, key, direction=-1):
        reverse = direction < 0
        self.docs = sorted(self.docs, key=lambda d: d.get(key) or "", reverse=reverse)
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, _n: int) -> List[Dict[str, Any]]:
        return [dict(d) for d in self.docs]


class FakeCollection:
    def __init__(self, name: str):
        self.name = name
        self.docs: List[Dict[str, Any]] = []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                out = dict(d)
                if len(a) > 0 and isinstance(a[0], dict):  # projection
                    for f, inc in a[0].items():
                        if inc == 0:
                            out.pop(f, None)
                return out
        return None

    async def insert_one(self, doc):
        from bson import ObjectId

        entry = dict(doc)
        entry.setdefault("_id", ObjectId())
        self.docs.append(entry)
        return FakeResult(inserted_id=entry["_id"])

    async def update_one(self, query, update, upsert=False):
        if isinstance(update, list):  # aggregation-pipeline update: simulate applied
            for d in self.docs:
                if _matches(d, query):
                    return FakeResult(modified_count=1)
            return FakeResult(modified_count=0)
        for d in self.docs:
            if _matches(d, query):
                for f, v in (update.get("$set") or {}).items():
                    d[f] = v
                for f, v in (update.get("$inc") or {}).items():
                    d[f] = (d.get(f) or 0) + v
                for f, v in (update.get("$push") or {}).items():
                    d.setdefault(f, []).append(v)
                for f in (update.get("$unset") or {}):
                    d.pop(f, None)
                return FakeResult(modified_count=1)
        if upsert:
            merged = {k: v for k, v in query.items() if not k.startswith("$")}
            merged.update(update.get("$set") or {})
            return await self.insert_one(merged)
        return FakeResult(modified_count=0)

    async def count_documents(self, query) -> int:
        return sum(1 for d in self.docs if _matches(d, query))

    def find(self, query=None, projection=None):
        docs = [dict(d) for d in self.docs if _matches(d, query or {})]
        if isinstance(projection, dict):
            for d in docs:
                for f, inc in projection.items():
                    if inc == 0:
                        d.pop(f, None)
        return FakeCursor(docs)

    async def create_index(self, *a, **k):
        return "fake-index"


class FakeDB:
    def __init__(self):
        self.users = FakeCollection("users")
        self.games = FakeCollection("games")
        self.btc_deposits = FakeCollection("btc_deposits")
        self.manual_deposits = FakeCollection("manual_deposits")
        self.distribution_settings = FakeCollection("distribution_settings")
        self.distribution_tasks = FakeCollection("distribution_tasks")
        self.sugar_token_purchases = FakeCollection("sugar_token_purchases")
        self.bonus_credit_grants = FakeCollection("bonus_credit_grants")
        self.revenue_ledger = FakeCollection("revenue_ledger")
        self.revenue_settings = FakeCollection("revenue_settings")
        self.redemption_requests = FakeCollection("redemption_requests")
        self.credit_adjustments = FakeCollection("credit_adjustments")
        self.kyc_profiles = FakeCollection("kyc_profiles")
        self.admin_alerts = FakeCollection("admin_alerts")

    def __getitem__(self, name):
        return getattr(self, name)


@pytest.fixture()
def db():
    revenue_engine._RATE_CACHE.clear()
    return FakeDB()


async def _seed_user(db, **over):
    from bson import ObjectId

    doc = {
        "_id": ObjectId(),
        "email": "player@x.com",
        "name": "Player",
        "role": "user",
        "sugar_tokens": 0,
        "game_credits": 0,
        "password_hash": "hashed-secret",
        "twofa_secret": "totp-secret",
        "game_username": "sugarab123",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(over)
    await db.users.insert_one(doc)
    return doc


async def _seed_game(db, name="Fire Kirin"):
    from bson import ObjectId

    doc = {"_id": ObjectId(), "name": name, "is_active": True}
    await db.games.insert_one(doc)
    return doc


def _admin_app(db):
    app = FastAPI()

    async def _admin(request):
        return {"id": "admin1", "email": "admin@wah-lah.com", "role": "admin"}

    async def _user(request):
        return {"id": "u1", "email": "player@x.com", "role": "user"}

    app.include_router(build_distributor_admin_router(db=db, get_admin_user=_admin), prefix="/api")
    app.include_router(
        build_payment_router(db=db, get_current_user=_user, get_admin_user=_admin), prefix="/api"
    )
    return TestClient(app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Reconcile — the money endpoint
# --------------------------------------------------------------------------
class TestReconcile:
    def test_credits_net_and_queues_manual_task(self, db):
        async def seed():
            user = await _seed_user(db)
            await _seed_game(db)
            await sd.set_mode(db, "manual", updated_by="test")
            return user

        user = run(seed())
        c = _admin_app(db)
        r = c.post("/api/admin/cashtag/reconcile", json={
            "user_id": str(user["_id"]),
            "amount_usd": 25,
            "source": "cashapp",
            "receipt": "CA-001",
            "platform": "Fire Kirin",
            "note": "verified in app",
        })
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["gross_usd"] == 25
        assert j["fee_usd"] == 3.0          # 12% house keep
        assert j["net_usd"] == 22.0
        assert j["status"] == "completed"
        assert j["distribution_mode"] == "manual"
        assert j["pool_transfer_status"] == "awaiting_manual_send"
        assert j["distribution_task_id"]

        me = run(db.users.find_one({"_id": user["_id"]}))
        assert me["sugar_tokens"] == 2200   # NET credited, not gross
        assert me["game_credits"] == 2200
        task = run(db.distribution_tasks.find_one({"deposit_id": j["deposit_id"]}))
        assert task["recipient_username"] == "sugarab123"
        assert task["amount_credits"] == 2200
        # Platform denomination: games display DOLLARS, not internal credits.
        assert task["platform_amount"] == 22.0
        assert task["platform_unit"] == "USD"
        ledger = run(db.revenue_ledger.find_one({"ref_id": j["deposit_id"]}))
        assert ledger["kind"] == "cashtag" and ledger["fee_usd"] == 3.0

    def test_duplicate_receipt_is_idempotent(self, db):
        async def seed():
            user = await _seed_user(db)
            await sd.set_mode(db, "manual", updated_by="test")
            return user

        user = run(seed())
        c = _admin_app(db)
        body = {"user_id": str(user["_id"]), "amount_usd": 10,
                "source": "chime", "receipt": "CH-9"}
        r1 = c.post("/api/admin/cashtag/reconcile", json=body)
        r2 = c.post("/api/admin/cashtag/reconcile", json=body)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r2.json()["duplicate"] is True
        assert r2.json()["deposit_id"] == r1.json()["deposit_id"]
        me = run(db.users.find_one({"_id": user["_id"]}))
        assert me["sugar_tokens"] == 880  # credited once, not twice

    def test_whale_comp_skips_fee_and_is_audited(self, db):
        async def seed():
            user = await _seed_user(db)
            await sd.set_mode(db, "manual", updated_by="test")
            return user

        user = run(seed())
        c = _admin_app(db)
        r = c.post("/api/admin/cashtag/reconcile", json={
            "user_id": str(user["_id"]), "amount_usd": 500,
            "source": "cashapp", "receipt": "WHALE-1", "apply_fee": False,
            "note": "whale comp",
        })
        assert r.status_code == 200, r.text
        assert r.json()["fee_usd"] == 0
        assert r.json()["net_usd"] == 500
        me = run(db.users.find_one({"_id": user["_id"]}))
        assert me["sugar_tokens"] == 50000

    def test_rejects_unknown_user_platform_and_source(self, db):
        run(_seed_game(db))
        c = _admin_app(db)
        assert c.post("/api/admin/cashtag/reconcile", json={
            "user_email": "ghost@x.com", "amount_usd": 10}).status_code == 404
        user = run(_seed_user(db))
        r = c.post("/api/admin/cashtag/reconcile", json={
            "user_id": str(user["_id"]), "amount_usd": 10, "platform": "Nope"})
        assert r.status_code == 400 and "Fire Kirin" in r.text
        r = c.post("/api/admin/cashtag/reconcile", json={
            "user_id": str(user["_id"]), "amount_usd": 10, "source": "venmo"})
        assert r.status_code == 400
        r = c.post("/api/admin/cashtag/reconcile", json={
            "user_id": str(user["_id"]), "amount_usd": 0.5})
        assert r.status_code == 400

    def test_no_platform_keeps_local_balance(self, db):
        async def seed():
            user = await _seed_user(db)
            await sd.set_mode(db, "manual", updated_by="test")
            return user

        user = run(seed())
        c = _admin_app(db)
        r = c.post("/api/admin/cashtag/reconcile", json={
            "user_id": str(user["_id"]), "amount_usd": 20, "receipt": "NOPLAT"})
        assert r.status_code == 200
        assert r.json()["pool_transfer_status"] == "skipped_no_platform"


# --------------------------------------------------------------------------
# Users / transactions / stats
# --------------------------------------------------------------------------
class TestAdminReads:
    def test_users_list_strips_secrets(self, db):
        run(_seed_user(db, email="a@x.com"))
        run(_seed_user(db, email="b@x.com", role="admin"))
        c = _admin_app(db)
        r = c.get("/api/admin/users")
        assert r.status_code == 200
        j = r.json()
        assert j["total"] == 2
        for u in j["users"]:
            assert "password_hash" not in u and "twofa_secret" not in u
            assert u["id"]
        assert c.get("/api/admin/users", params={"q": "a@x"}).json()["total"] == 1
        assert c.get("/api/admin/users", params={"role": "admin"}).json()["total"] == 1

    def test_patch_adjusts_credits_with_audit(self, db):
        user = run(_seed_user(db))
        c = _admin_app(db)
        r = c.patch(f"/api/admin/users/{user['_id']}", json={
            "adjust_game_credits": 500, "note": "goodwill"})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["game_credits"] == 500
        audit = run(db.credit_adjustments.find_one({"user_id": str(user["_id"])}))
        assert audit["inc"] == {"game_credits": 500}
        assert audit["actor"] == "admin@wah-lah.com"
        r = c.patch(f"/api/admin/users/{user['_id']}", json={})
        assert r.status_code == 400

    def test_patch_game_accounts_and_role(self, db):
        user = run(_seed_user(db))
        c = _admin_app(db)
        r = c.patch(f"/api/admin/users/{user['_id']}", json={
            "game_username": "sugarab123",
            "game_password": "newpass",
            "game_accounts": {"fire_kirin": {"account_name": "sugarab123"}},
            "note": "player renamed account",
        })
        assert r.status_code == 200, r.text
        fresh = r.json()["user"]
        assert fresh["game_username"] == "sugarab123"
        assert fresh["game_accounts"]["fire_kirin"]["account_name"] == "sugarab123"
        r = c.patch(f"/api/admin/users/{user['_id']}", json={"role": "superuser"})
        assert r.status_code == 400

    def test_transactions_feed_and_stats(self, db):
        async def seed():
            user = await _seed_user(db)
            await _seed_game(db)
            await sd.set_mode(db, "manual", updated_by="test")
            return user

        user = run(seed())
        c = _admin_app(db)
        c.post("/api/admin/cashtag/reconcile", json={
            "user_id": str(user["_id"]), "amount_usd": 25, "receipt": "FEED-1",
            "platform": "Fire Kirin"})
        tx = c.get("/api/admin/transactions").json()
        kinds = {t["kind"] for t in tx["transactions"]}
        assert {"manual_deposit", "purchase", "grant"} <= kinds
        only = c.get("/api/admin/transactions", params={"kind": "manual_deposit"}).json()
        assert all(t["kind"] == "manual_deposit" for t in only["transactions"])
        stats = c.get("/api/admin/stats").json()
        assert stats["distribution_mode"] == "manual"
        assert stats["deposits_today"]["manual_count"] == 1
        assert stats["deposits_today"]["fees_usd"] == 3.0
        assert stats["distribution"]["awaiting_send"] == 1


# --------------------------------------------------------------------------
# Card info disclosure
# --------------------------------------------------------------------------
class TestCardInfo:
    def test_reports_tag_and_live_fee(self, db, monkeypatch):
        monkeypatch.setenv("CARD_PAYMENT_TAG", "$TestTag")
        c = _admin_app(db)
        j = c.get("/api/payment/card-info").json()
        assert j["enabled"] is True and j["tag"] == "$TestTag"
        assert j["fee_rate"] == 0.12 and "12%" in j["fee_disclosure"]

    def test_disabled_without_tag(self, db, monkeypatch):
        monkeypatch.delenv("CARD_PAYMENT_TAG", raising=False)
        c = _admin_app(db)
        j = c.get("/api/payment/card-info").json()
        assert j["enabled"] is False and j["tag"] == ""


# --------------------------------------------------------------------------
# Platform denomination
# --------------------------------------------------------------------------
class TestDenomination:
    def test_converters_are_inverse(self):
        from config.currency_config import (
            credits_to_platform_amount, platform_amount_to_credits)
        assert credits_to_platform_amount(2200) == 22.0
        assert credits_to_platform_amount(0) == 0.0
        assert platform_amount_to_credits(22.0) == 2200
        assert platform_amount_to_credits(22.55) == 2255

    def test_task_view_shows_send_instruction(self, db):
        tid = run(sd.create_manual_task(
            db, deposit_id="dep-x", user_id="u1", user_email="p@x.com",
            platform="Fire Kirin", recipient_username="sugarab123",
            amount_credits=2200))
        view = run(sd.get_task(db, tid))
        assert view["platform_amount"] == 22.0
        assert view["send_instruction"] == (
            "Send $22.00 to 'sugarab123' on Fire Kirin")

    def test_summary_reports_platform_totals(self, db):
        run(sd.create_manual_task(
            db, deposit_id="dep-y", user_id="u1", user_email="p@x.com",
            platform="Juwa", recipient_username="sugarab123",
            amount_credits=5000))
        summ = run(sd.summary(db))
        assert summ["pending_credits"] == 5000
        assert summ["pending_platform_amount"] == 50.0


# --------------------------------------------------------------------------
# Queue lifecycle upgrades
# --------------------------------------------------------------------------
class TestQueueLifecycle:
    def _task(self, db, **over):
        async def go():
            await db.btc_deposits.insert_one({
                "id": over.get("deposit_id", "dep-1"), "platform": "fire_kirin",
                "user_id": "u1", "pool_transfer_status": "awaiting_manual_send"})
            return await sd.create_manual_task(
                db, deposit_id=over.get("deposit_id", "dep-1"), user_id="u1",
                user_email="p@x.com", platform="fire_kirin",
                recipient_username="player1", amount_credits=500)
        return run(go())

    def test_retry_requeues_failed(self, db):
        tid = self._task(db)
        assert run(sd.mark_failed(db, tid, "a@x", "hub down"))[0] is True
        ok, msg = run(sd.retry_task(db, tid, "a@x"))
        assert ok is True
        assert run(sd.get_task(db, tid))["status"] == "awaiting_send"
        dep = run(db.btc_deposits.find_one({"id": "dep-1"}))
        assert dep["pool_transfer_status"] == "awaiting_manual_send"
        ok, msg = run(sd.retry_task(db, tid, "a@x"))
        assert ok is False  # only failed tasks retry

    def test_cancel_is_terminal(self, db):
        tid = self._task(db)
        assert run(sd.cancel_task(db, tid, "a@x", "duplicate"))[0] is True
        assert run(sd.get_task(db, tid))["status"] == "cancelled"
        assert run(sd.confirm_sent(db, tid, "a@x"))[0] is False
        assert run(sd.retry_task(db, tid, "a@x"))[0] is False

    def test_summary_flags_overdue_and_today(self, db, monkeypatch):
        monkeypatch.setenv("DISTRIBUTOR_OVERDUE_HOURS", "4")
        tid = self._task(db)
        old = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()

        async def age():
            for d in db.distribution_tasks.docs:
                if str(d["_id"]) == tid or d.get("id") == tid:
                    d["created_at"] = old
        run(age())
        s = run(sd.summary(db))
        assert s["overdue"]["count"] == 1
        assert s["overdue"]["credits"] == 500
        assert s["oldest_awaiting"]["overdue"] is True
        assert s["today"]["tasks_done"] == 0
        assert run(sd.confirm_sent(db, tid, "a@x"))[0] is True
        s = run(sd.summary(db))
        assert s["today"] == {"tasks_done": 1, "credits_sent": 500,
                         "platform_sent": 5.0, "fees_usd": 0.0}

    def test_confirm_completes_manual_deposit_too(self, db):
        async def seed():
            user = await _seed_user(db)
            await _seed_game(db)
            await sd.set_mode(db, "manual", updated_by="test")
            return user

        user = run(seed())
        c = _admin_app(db)
        r = c.post("/api/admin/cashtag/reconcile", json={
            "user_id": str(user["_id"]), "amount_usd": 25,
            "receipt": "MAN-1", "platform": "Fire Kirin"})
        task_id = r.json()["distribution_task_id"]
        assert run(sd.confirm_sent(db, task_id, "admin@wah-lah.com"))[0] is True
        dep = run(db.manual_deposits.find_one({"id": r.json()["deposit_id"]}))
        assert dep["pool_transfer_status"] == "done"
