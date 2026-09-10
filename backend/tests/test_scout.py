"""Self-contained unit tests for the Scout Force intake route (routes/scout.py).

No network, no real MongoDB. Uses the same lightweight Motor-like fake as the
pool_pull tests, but locally defined so this file is fully self-contained.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from bson import ObjectId
except Exception:  # pragma: no cover
    ObjectId = None  # type: ignore

from fastapi import APIRouter

from routes.scout import build_scout_router


def _match(doc, filt):
    if not filt:
        return True
    for key, val in filt.items():
        if isinstance(val, dict):
            if "$ne" in val and doc.get(key) == val["$ne"]:
                return False
            continue
        if doc.get(key) != val:
            return False
    return True


class _Result:
    def __init__(self, matched=1):
        self.matched_count = matched


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        return self.docs[:n]


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

    async def insert_one(self, doc):
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return _Result()

    async def update_one(self, filt, update, upsert=False):
        for d in self.docs:
            if _match(d, filt or {}):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                return _Result()
        if upsert:
            self.docs.append(dict(filt or {}))
            return _Result()
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


@pytest.fixture
def fake_db():
    return FakeDb()


@pytest.fixture
def router(fake_db):
    return build_scout_router(db=fake_db, get_admin_user=None)


def test_build_router_registers_two_routes(router):
    assert isinstance(router, APIRouter)
    paths = {r.path for r in router.routes}
    assert "/admin/scout/leads" in paths
    assert len(router.routes) == 2


def test_receive_leads_unconfigured_returns_503(monkeypatch, router):
    monkeypatch.delenv("SCOUT_LEADS_TOKEN", raising=False)

    class Req:
        def __init__(self, body):
            self._body = body

        async def json(self):
            return self._body

        @property
        def headers(self):
            class H:
                def get(self, k, default=None):
                    return ""
            return H()

    with pytest.raises(Exception, match="503|configured"):
        asyncio.run(router.routes[0].endpoint(Req({"leads": []})))


def test_receive_leads_bad_token_401(monkeypatch, router):
    monkeypatch.setenv("SCOUT_LEADS_TOKEN", "secret-token")

    class Req:
        async def json(self):
            return {"scout": "north-america", "region": "NA", "leads": []}

        @property
        def headers(self):
            class H:
                def get(self, k, default=None):
                    return "Bearer wrong"
            return H()

    with pytest.raises(Exception):
        asyncio.run(router.routes[0].endpoint(Req()))


def test_receive_leads_ok(monkeypatch, router, fake_db):
    monkeypatch.setenv("SCOUT_LEADS_TOKEN", "s3cret")

    class Req:
        async def json(self):
            return {
                "scout": "asia-pacific",
                "region": "Asia & Pacific",
                "collected_at": "2026-09-06T02:00:00Z",
                "leads": [
                    {"name": "Happy Arcade", "url": "https://arcade.example", "kind": "venue", "score": 0.8},
                    {"name": "r/gaming", "url": "https://reddit.com/r/gaming", "kind": "community", "score": 0.5},
                ],
            }

        @property
        def headers(self):
            class H:
                def get(self, k, default=None):
                    return "Bearer s3cret"
            return H()

    r = asyncio.run(router.routes[0].endpoint(Req()))
    assert r["ok"] is True
    assert r["inserted"] == 2
    assert r["scout"] == "asia-pacific"
    leads = fake_db["scout_leads"].docs
    assert len(leads) == 2
    assert all(l["status"] == "new" for l in leads)
    alerts = fake_db["admin_alerts"].docs
    assert len(alerts) == 1
    assert alerts[0]["type"] == "scout_leads"
    assert alerts[0]["scout"] == "asia-pacific"
    assert alerts[0]["lead_count"] == 2


def test_receive_leads_dedupes_alert_per_scout_per_day(monkeypatch, router, fake_db):
    monkeypatch.setenv("SCOUT_LEADS_TOKEN", "s3cret")

    def mk_req():
        class Req:
            async def json(self):
                return {
                    "scout": "europe",
                    "region": "EU",
                    "leads": [
                        {"name": "Berlin Arcade", "url": "https://b.example", "kind": "venue", "score": 0.6},
                    ],
                }

            @property
            def headers(self):
                class H:
                    def get(self, k, default=None):
                        return "Bearer s3cret"
                return H()

        return Req()

    asyncio.run(router.routes[0].endpoint(mk_req()))
    asyncio.run(router.routes[0].endpoint(mk_req()))
    alerts = fake_db["admin_alerts"].docs
    assert len(alerts) == 1
    assert alerts[0]["lead_count"] == 2
    assert len(fake_db["scout_leads"].docs) == 2