"""Self-contained tests for the Concierge answer loop.

- Player Genie Q/A cycle (LLM mocked — no live provider in CI):
  ask -> reply -> history persists -> follow-up sees context
- Escalation: [ESCALATE] replies file a high-priority ticket, strip the tag
- Provider outage -> 503 with a human-readable reason (UI shows fallback)
- Operator respond appends to the thread; player reads it back owner-scoped
- Strangers cannot read each other's tickets

Registered in conftest.SELF_CONTAINED_FILES so it always runs in CI.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jwt
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.genie as genie_route
from routes.admin_analytics import get_analytics_routes
from routes.genie import build_genie_router
from routes.user_routes import get_user_routes


# --------------------------------------------------------------------------
# Fake async mongo
# --------------------------------------------------------------------------
class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, _k, _d):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, length):
        return list(self._docs[:length])


class FakeResult:
    def __init__(self, modified_count=0, inserted_id=None):
        self.modified_count = modified_count
        self.inserted_id = inserted_id


def _matches(doc, query):
    return all(doc.get(k) == v for k, v in (query or {}).items())


def _apply_projection(doc, proj):
    if not proj:
        return doc
    out = dict(doc)
    if proj.get("_id") == 0:
        out.pop("_id", None)
    include = [k for k, v in proj.items() if v == 1 and k != "_id"]
    if include:
        out = {k: out[k] for k in include if k in out}
        if proj.get("_id", 1) == 1 and "_id" in doc:
            out["_id"] = doc["_id"]
    return out


class FakeCollection:
    def __init__(self, docs=None):
        self.docs: List[Dict[str, Any]] = list(docs or [])

    def find(self, query=None, proj=None):
        return FakeCursor([_apply_projection(d, proj) for d in self.docs if _matches(d, query)])

    async def find_one(self, query=None, proj=None):
        for d in self.docs:
            if _matches(d, query):
                return _apply_projection(d, proj)
        return None

    async def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return FakeResult(inserted_id=doc["_id"])

    async def update_one(self, query, update):
        for d in self.docs:
            if _matches(d, query):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                for k, v in update.get("$push", {}).items():
                    d.setdefault(k, []).append(v)
                return FakeResult(modified_count=1)
        return FakeResult(modified_count=0)


class FakeDB:
    def __init__(self):
        self._cols: Dict[str, FakeCollection] = {}
        self.users = self.__getitem__("users")

    def __getitem__(self, name):
        # attribute-style (db.users) and item-style (db["users"]) share cols
        if name not in self._cols:
            self._cols[name] = FakeCollection()
            if name == "users":
                self.users = self._cols[name]
        return self._cols[name]

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self.__getitem__(name)


ADMIN_ID = ObjectId()
PLAYER_ID = ObjectId()
OTHER_ID = ObjectId()


@pytest.fixture()
def db():
    fake = FakeDB()
    fake.users.docs.extend([
        {"_id": ADMIN_ID, "email": "boss@x.com", "name": "Boss", "role": "admin"},
        {"_id": PLAYER_ID, "email": "player@x.com", "name": "P", "role": "user"},
        {"_id": OTHER_ID, "email": "stranger@x.com", "name": "S", "role": "user"},
    ])
    return fake


def _authed_client(app, user_id):
    client = TestClient(app)
    token = jwt.encode({"sub": str(user_id)}, "test-secret", algorithm="HS256")
    client.cookies.set("access_token", token)
    return client


@pytest.fixture()
def player_client(db, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    app = FastAPI()
    app.include_router(get_user_routes(db))
    return _authed_client(app, PLAYER_ID)


@pytest.fixture()
def admin_client(db, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    app = FastAPI()
    app.include_router(get_analytics_routes(db))
    return _authed_client(app, ADMIN_ID)


@pytest.fixture()
def genie_client(db):
    async def fake_user():
        return {"_id": PLAYER_ID, "email": "player@x.com", "name": "P"}

    app = FastAPI()
    app.include_router(build_genie_router(db, get_current_user=fake_user))
    return TestClient(app)


class TestGenieCycle:
    def test_ask_reply_history(self, genie_client, db, monkeypatch):
        async def fake_complete(messages):
            assert messages[0]["role"] == "system"
            return "Allow up to 24 hours for review.", "cerebras", "llama"

        monkeypatch.setattr(genie_route, "complete", fake_complete)
        r1 = genie_client.post("/genie/chat", json={"message": "Where is my payout?"})
        assert r1.status_code == 200
        body = r1.json()
        assert body["reply"].startswith("Allow up to 24 hours")
        assert body["provider"] == "cerebras"
        assert body["escalated"] is False
        sid = body["session_id"]

        # Follow-up in the same session sees the earlier exchange.
        seen = {}

        async def spy_complete(messages):
            seen["n"] = len(messages)
            return "Still the same answer.", "cerebras", "llama"

        monkeypatch.setattr(genie_route, "complete", spy_complete)
        r2 = genie_client.post("/genie/chat", json={"session_id": sid, "message": "Really?"})
        assert r2.status_code == 200
        assert seen["n"] == 4  # system + user + assistant + user

        hist = genie_client.get(f"/genie/history/{sid}").json()["messages"]
        assert [m["role"] for m in hist] == ["user", "assistant", "user", "assistant"]

    def test_escalation_files_ticket(self, genie_client, db, monkeypatch):
        async def fake_complete(_messages):
            return "[ESCALATE] Your deposit is past review — I've flagged a human.", "cerebras", "llama"

        monkeypatch.setattr(genie_route, "complete", fake_complete)
        body = genie_client.post("/genie/chat", json={"message": "My deposit is missing!"}).json()
        assert body["escalated"] is True
        assert not body["reply"].startswith("[ESCALATE]")
        assert body["ticket_id"]
        tickets = db["support_tickets"].docs
        assert len(tickets) == 1
        assert tickets[0]["priority"] == "high"
        assert tickets[0]["source"] == "genie"

    def test_provider_outage_is_503(self, genie_client, monkeypatch):
        async def boom(_messages):
            raise RuntimeError("No Genie provider configured.")

        monkeypatch.setattr(genie_route, "complete", boom)
        r = genie_client.post("/genie/chat", json={"message": "hi"})
        assert r.status_code == 503
        assert "provider" in r.json()["detail"].lower()


class TestTicketLoop:
    def _seed_ticket(self, db):
        tid = ObjectId()
        db["support_tickets"].docs.append({
            "_id": tid, "user_id": str(PLAYER_ID), "user_email": "player@x.com",
            "subject": "Missing credits", "message": "help", "status": "open",
            "priority": "normal", "created_at": "2026-09-01T00:00:00+00:00",
            "responses": [],
        })
        return str(tid)

    def test_respond_then_player_reads_back(self, admin_client, player_client, db):
        tid = self._seed_ticket(db)
        r = admin_client.post(f"/admin/analytics/support-tickets/{tid}/respond",
                              json={"message": "Credited — check your balance."})
        assert r.status_code == 200
        detail = player_client.get(f"/user/support/tickets/{tid}").json()
        assert detail["status"] == "pending"
        assert detail["responses"][-1]["message"].startswith("Credited")
        assert detail["responses"][-1]["by"] == "boss@x.com"

    def test_stranger_cannot_read(self, db, monkeypatch):
        self._seed_ticket(db)
        tid = db["support_tickets"].docs[0]["_id"]
        monkeypatch.setenv("JWT_SECRET", "test-secret")
        app = FastAPI()
        app.include_router(get_user_routes(db))
        stranger = _authed_client(app, OTHER_ID)
        assert stranger.get(f"/user/support/tickets/{tid}").status_code == 404

    def test_respond_validates(self, admin_client, db):
        assert admin_client.post(
            "/admin/analytics/support-tickets/not-an-id/respond",
            json={"message": "x"}).status_code == 422
        assert admin_client.post(
            f"/admin/analytics/support-tickets/{ObjectId()}/respond",
            json={"message": "x"}).status_code == 404
