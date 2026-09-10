"""Self-contained unit tests for the Self-Distributor service.

No live backend needed: uses an in-memory fake DB that mirrors the subset of
the pymongo API the service touches. Registered in conftest.SELF_CONTAINED_FILES
so it always runs in CI. Plain sync tests (no pytest-asyncio) using asyncio.run.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import self_distributor as sd  # noqa: E402


def run(awaitable):
    return asyncio.run(awaitable)


class FakeResult:
    def __init__(self, modified_count=0, upserted_id=None, inserted_id=None):
        self.modified_count = modified_count
        self.upserted_id = upserted_id
        self.inserted_id = inserted_id


def _matches(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    """Tiny query matcher: exact field equality + _id handling."""
    for k, v in query.items():
        if k == "_id":
            if str(doc.get("_id")) != str(v) and doc.get("_id") != v:
                return False
        elif k not in doc or doc[k] != v:
            return False
    return True


class FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs

    def sort(self, _key, _dir=-1):
        return self

    def limit(self, _n):
        return self

    async def to_list(self, _n: int) -> List[Dict[str, Any]]:
        return list(self.docs)


class FakeCollection:
    def __init__(self, name: str):
        self.name = name
        self.docs: List[Dict[str, Any]] = []
        self._counter = 0

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc: Dict[str, Any]):
        from bson import ObjectId

        self._counter += 1
        entry = dict(doc)
        entry.setdefault("_id", ObjectId())
        self.docs.append(entry)
        return FakeResult(inserted_id=entry["_id"])

    async def update_one(self, query: Dict[str, Any], update: Any, upsert=False):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return FakeResult(modified_count=1)
        if upsert:
            merged = dict(query)
            merged.update(update.get("$set", {}))
            return await self.insert_one(merged)
        return FakeResult(modified_count=0)

    async def count_documents(self, query: Dict[str, Any]) -> int:
        return sum(1 for d in self.docs if _matches(d, query))

    def find(self, query: Dict[str, Any], projection: Optional[Dict] = None):
        return FakeCursor([dict(d) for d in self.docs if _matches(d, query)])


class FakeDB:
    def __init__(self):
        self.distribution_settings = FakeCollection("distribution_settings")
        self.distribution_tasks = FakeCollection("distribution_tasks")
        self.btc_deposits = FakeCollection("btc_deposits")
        self.users = FakeCollection("users")


async def _make_task(db, **overrides):
    kw = dict(
        deposit_id="dep-1",
        user_id="60f7c5b2e4b0a1b2c3d4e5f6",
        user_email="p@x.com",
        platform="fire_kirin",
        recipient_username="player1",
        amount_credits=500,
        tx_hash="abc123",
    )
    kw.update(overrides)
    await db.btc_deposits.insert_one({
        "id": kw["deposit_id"],
        "platform": kw["platform"],
        "user_id": kw["user_id"],
        "pool_transfer_status": "pending",
    })
    return await sd.create_manual_task(db, **kw)


class TestMode:
    def test_default_is_auto(self):
        assert run(sd.get_mode(FakeDB())) == "auto"

    def test_set_manual_and_read_back(self):
        db = FakeDB()
        settings = run(sd.set_mode(db, "manual", updated_by="admin@wah-lah.com"))
        assert settings["mode"] == "manual"
        assert run(sd.get_mode(db)) == "manual"
        assert run(sd.get_settings(db))["updated_by"] == "admin@wah-lah.com"

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValueError):
            run(sd.set_mode(FakeDB(), "sideways"))

    def test_bad_persisted_mode_falls_back_to_auto(self):
        db = FakeDB()
        run(sd.set_mode(db, "manual"))
        db.distribution_settings.docs[0]["mode"] = "banana"
        assert run(sd.get_mode(db)) == "auto"


class TestTasks:
    def test_create_task_fields_and_status(self):
        db = FakeDB()
        task_id = run(_make_task(db))
        assert task_id is not None
        task = db.distribution_tasks.docs[0]
        assert task["status"] == "awaiting_send"
        assert task["deposit_id"] == "dep-1"
        assert task["recipient_username"] == "player1"
        assert task["amount_credits"] == 500.0
        assert task["platform"] == "fire_kirin"

    def test_create_is_idempotent_per_deposit(self):
        db = FakeDB()
        first = run(_make_task(db))
        second = run(_make_task(db))
        assert first == second  # same task returned, not a duplicate
        assert len(db.distribution_tasks.docs) == 1

    def test_list_tasks_filters_by_status(self):
        db = FakeDB()
        run(_make_task(db))
        pending = run(sd.list_tasks(db, status="awaiting_send"))
        assert len(pending) == 1 and pending[0]["id"] is not None
        assert run(sd.list_tasks(db, status="done")) == []

    def test_confirm_sent_completes_task_and_deposit(self):
        db = FakeDB()
        task_id = run(_make_task(db))
        ok, msg = run(sd.confirm_sent(db, task_id, "admin@wah-lah.com", note="sent on kirin"))
        assert ok
        task = db.distribution_tasks.docs[0]
        assert task["status"] == "done"
        assert task["confirmed_by"] == "admin@wah-lah.com"
        deposit = run(db.btc_deposits.find_one({"id": "dep-1"}))
        assert deposit["pool_transfer_status"] == "done"
        assert deposit["self_distributor"]["task_id"] == task_id

    def test_confirm_twice_rejected(self):
        db = FakeDB()
        task_id = run(_make_task(db))
        assert run(sd.confirm_sent(db, task_id, "admin@wah-lah.com"))[0]
        ok, msg = run(sd.confirm_sent(db, task_id, "admin@wah-lah.com"))
        assert not ok
        assert "already" in msg

    def test_mark_failed(self):
        db = FakeDB()
        task_id = run(_make_task(db))
        ok, _ = run(sd.mark_failed(db, task_id, "admin@wah-lah.com", reason="player typo"))
        assert ok
        assert db.distribution_tasks.docs[0]["status"] == "failed"
        deposit = run(db.btc_deposits.find_one({"id": "dep-1"}))
        assert deposit["pool_transfer_status"] == "failed"

    def test_unknown_task_not_confirmed(self):
        db = FakeDB()
        ok, msg = run(sd.confirm_sent(db, "nope", "admin@wah-lah.com"))
        assert not ok and msg == "Task not found"


class TestSummary:
    def test_summary_counts(self):
        db = FakeDB()
        for i in range(2):
            run(_make_task(db, deposit_id=f"dep-{i}"))
        run(sd.confirm_sent(db, db.distribution_tasks.docs[0]["id"], "admin@wah-lah.com"))
        s = run(sd.summary(db))
        assert s["statuses"]["awaiting_send"] == 1
        assert s["statuses"]["done"] == 1
        assert s["statuses"]["total"] == 2
        assert s["pending_credits"] == 500.0
        assert s["mode"] == "auto"