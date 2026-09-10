"""Self-contained tests for the public proof endpoints.

Covers GET /api/public/stats and GET /api/public/payouts/recent:
- figures computed from real rows (no hardcoding)
- ONLY completed money-out counts (approved BTC / fulfilled gift cards)
- player identities masked; no PII leaks (emails, addresses, user ids)
- newest-first ordering + limit honored
- empty database yields honest zeros + empty feed (never fake numbers)

Registered in conftest.SELF_CONTAINED_FILES so it always runs in CI.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.public_stats import (
    build_public_stats_router,
    clear_public_stats_cache,
    mask_name,
)


# --------------------------------------------------------------------------
# Fake async mongo (minimal surface: find/to_list + count_documents)
# --------------------------------------------------------------------------
def _matches(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    for k, v in query.items():
        if isinstance(v, dict):
            for op, ov in v.items():
                if op == "$ne" and doc.get(k) == ov:
                    return False
                elif op != "$ne":
                    raise AssertionError(f"unsupported op {op}")
            continue
        if doc.get(k) != v:
            return False
    return True


class FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    async def to_list(self, length: int = 100):
        return list(self._docs[:length])


class FakeCollection:
    def __init__(self, docs: List[Dict[str, Any]] | None = None):
        self.docs = list(docs or [])

    def find(self, query: Dict[str, Any] | None = None):
        query = query or {}
        return FakeCursor([d for d in self.docs if _matches(d, query)])

    async def count_documents(self, query: Dict[str, Any]) -> int:
        return sum(1 for d in self.docs if _matches(d, query))

    async def insert_one(self, doc: Dict[str, Any]):
        self.docs.append(doc)


class FakeDB:
    def __init__(self):
        self._cols: Dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self._cols.setdefault(name, FakeCollection())


@pytest.fixture()
def db():
    clear_public_stats_cache()
    return FakeDB()


@pytest.fixture()
def client(db):
    app = FastAPI()
    app.include_router(build_public_stats_router(db=db))
    return TestClient(app)


def _seed(db: FakeDB) -> None:
    users = db["users"]
    users.docs.extend([
        {"_id": "u1", "email": "jane@x.com", "role": "user"},
        {"_id": "u2", "email": "bob@x.com", "role": "user"},
        {"_id": "a1", "email": "boss@x.com", "role": "admin"},
    ])
    games = db["games"]
    games.docs.extend([
        {"name": "Fire Kirin", "is_active": True},
        {"name": "Juwa", "is_active": True},
        {"name": "Retired", "is_active": False},
    ])
    db["redemption_requests"].docs.extend([
        {"user_email": "jane@x.com", "amount_usd": 120.0,
         "status": "approved", "completed_at": "2026-09-02T10:00:00+00:00",
         "btc_address": "bc1qsecret", "user_id": "u1"},
        {"user_email": "bob@x.com", "amount_usd": 50.0,
         "status": "approved", "completed_at": "2026-09-03T10:00:00+00:00",
         "btc_address": "bc1qsecret2", "user_id": "u2"},
        # NOT paid — must never appear in public proof.
        {"user_email": "mallory@x.com", "amount_usd": 9999.0,
         "status": "pending", "created_at": "2026-09-04T10:00:00+00:00"},
        {"user_email": "mallory@x.com", "amount_usd": 888.0,
         "status": "hold_admin_review", "created_at": "2026-09-04T11:00:00+00:00"},
    ])
    db["gift_card_redemptions"].docs.extend([
        {"user_email": "jane@x.com", "amount_usd": 25.0, "brand_label": "Amazon",
         "status": "fulfilled", "fulfilled_at": "2026-09-05T10:00:00+00:00",
         "code": "SECRET-CODE", "user_id": "u1"},
        {"user_email": "mallory@x.com", "amount_usd": 777.0,
         "status": "pending", "created_at": "2026-09-06T10:00:00+00:00"},
    ])


class TestPublicStats:
    def test_live_figures_from_real_rows(self, client, db):
        _seed(db)
        r = client.get("/public/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["players"] == 2            # admin excluded
        assert body["platforms"] == 2          # inactive excluded
        assert body["payouts_count"] == 3      # 2 BTC + 1 gift card
        assert body["paid_out_usd"] == 195.0   # 120 + 50 + 25
        assert body["updated_at"]

    def test_pending_and_held_never_count(self, client, db):
        _seed(db)
        body = client.get("/public/stats").json()
        assert body["paid_out_usd"] < 1000  # the 9999/888/777 must not leak in

    def test_empty_db_is_honest_zeros(self, client):
        body = client.get("/public/stats").json()
        assert body["players"] == 0
        assert body["paid_out_usd"] == 0
        assert body["payouts_count"] == 0


class TestRecentPayouts:
    def test_newest_first_masked_no_pii(self, client, db):
        _seed(db)
        r = client.get("/public/payouts/recent")
        assert r.status_code == 200
        payouts = r.json()["payouts"]
        assert r.json()["count"] == 3
        # Newest first: gift card (Sep 5) → bob BTC (Sep 3) → jane BTC (Sep 2)
        assert [p["amount_usd"] for p in payouts] == [25.0, 50.0, 120.0]
        assert payouts[0]["method"] == "Amazon"
        assert payouts[1]["method"] == "BTC"
        assert payouts[1]["name"] == "b***"
        assert payouts[2]["name"] == "j***"
        blob = r.text
        for secret in ("jane@x.com", "bob@x.com", "mallory@x.com",
                       "bc1qsecret", "SECRET-CODE", '"user_id"', '"user_email"'):
            assert secret not in blob

    def test_limit_honored(self, client, db):
        _seed(db)
        payouts = client.get("/public/payouts/recent?limit=2").json()["payouts"]
        assert len(payouts) == 2

    def test_empty_db_is_empty_feed(self, client):
        body = client.get("/public/payouts/recent").json()
        assert body == {"payouts": [], "count": 0}


class TestMaskName:
    def test_masks(self):
        assert mask_name("Jane@x.com") == "j***"
        assert mask_name("") == "a player"
        assert mask_name(None) == "a player"
        assert mask_name("not-an-email") == "a player"
