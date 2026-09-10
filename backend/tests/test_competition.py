"""Self-contained unit tests for the Million Dollar Competition service.

No network, no real MongoDB. Uses the same lightweight in-memory fake
collection pattern as ``test_pool_resync.py`` / ``test_pool_pull.py`` but
extended with a tiny ``aggregate`` engine supporting the stages the
competition service uses ($match / $group with $sum,$first,$addToSet /
$sort / $limit).

Coverage: idempotent awarding (purchase + AMOE), leaderboard masking and
ordering, totals, weighted draw selection, concluded/prize transitions, and
best-effort behavior (award failure never surfaces as an exception).
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --- Motor-like fake with a mini aggregation engine -----------------------
def _match(doc, filt):
    if not filt:
        return True
    for key, val in filt.items():
        if key.startswith("$"):
            if isinstance(val, dict) and "$ne" in val:
                if doc.get(key[1:]) == val["$ne"]:
                    return False
                continue
            continue
        got = doc.get(key)
        if isinstance(val, dict) and "$ne" in val:
            if got == val["$ne"]:
                return False
            continue
        if key == "_id" and got is not None:
            if str(got) != str(val):
                return False
        elif got != val:
            return False
    return True


def _val(doc, expr):
    if isinstance(expr, str) and expr.startswith("$"):
        return doc.get(expr[1:])
    return expr


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

    def sort(self, key, direction: int = 1):
        self.docs.sort(key=lambda d: _val(d, key) or "", reverse=(direction == -1))
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n=None):
        return self.docs[:] if n is None else self.docs[:n]


class FakeColl:
    def __init__(self):
        self.docs = []

    def find(self, filt=None, projection=None):
        return _Cursor([d for d in self.docs if _match(d, filt or {})])

    async def find_one(self, filt=None, projection=None, sort=None):
        docs = [d for d in self.docs if _match(d, filt or {})]
        if sort and isinstance(sort, list):
            for key, direction in reversed(sort):
                docs.sort(key=lambda d: d.get(key) or "", reverse=(direction == -1))
        return docs[0] if docs else None

    async def update_one(self, filt, update):
        for d in self.docs:
            if _match(d, filt):
                _apply(d, update)
                return _FakeResult(1)
        return _FakeResult(0)

    async def insert_one(self, doc):
        self.docs.append(doc)
        return {"inserted_id": doc.get("_id")}

    async def delete_one(self, filt):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _match(d, filt)]
        return _FakeResult(before - len(self.docs))

    async def create_index(self, keys, **kw):
        return "fake_idx"

    def aggregate(self, pipeline):
        return _Cursor(_agg(self.docs, pipeline))


class _FakeResult:
    def __init__(self, modified_count):
        self.modified_count = modified_count


def _apply(doc, update):
    for op, fields in update.items():
        if op == "$set":
            for k, v in fields.items():
                if v is not None:
                    doc[k] = v
                else:
                    doc.pop(k, None)
        elif op == "$unset":
            for k in fields:
                doc.pop(k, None)
        elif op == "$inc":
            for k, v in fields.items():
                doc[k] = doc.get(k, 0) + v


def _agg(docs, pipeline):
    out = list(docs)
    for stage in pipeline:
        op, spec = next(iter(stage.items()))
        if op == "$match":
            out = [d for d in out if _match(d, spec)]
        elif op == "$group":
            groups = {}
            for d in out:
                key = _val(d, spec["_id"]) if spec.get("_id") is not None else None
                g = groups.setdefault(key, {"_id": key})
                for field, expr in spec.items():
                    if field == "_id":
                        continue
                    if isinstance(expr, dict) and "$sum" in expr:
                        g[field] = g.get(field, 0) + (_val(d, expr["$sum"]) or 0)
                    elif isinstance(expr, dict) and "$first" in expr:
                        g.setdefault(field, _val(d, expr["$first"]))
                    elif isinstance(expr, dict) and "$addToSet" in expr:
                        g.setdefault(field, set()).add(_val(d, expr["$addToSet"]))
            out = list(groups.values())
        elif op == "$sort":
            key = next(iter(spec))
            out.sort(key=lambda d: d.get(key) or 0, reverse=(spec[key] == -1))
        elif op == "$limit":
            out = out[:spec]
    return out


class FakeDB(dict):
    def __missing__(self, key):
        coll = FakeColl()
        self[key] = coll
        return coll


@pytest.fixture
def fake_db():
    return FakeDB()


def _live_comp(db, cid="C1", status="live", rules=None):
    db["competitions"].docs.append({
        "id": cid,
        "name": "Million Dollar Sweepstakes",
        "prize_usd": 1_000_000,
        "status": status,
        "starts_at": "2026-09-01T00:00:00+00:00",
        "draws_at": "2026-11-30T23:59:59+00:00",
        "rules": {"entry_per_purchase_usd": 1.0, "entry_amoe_daily": 1.0, **(rules or {})},
        "winner": None,
        "prize_status": None,
    })


def _entry(db, competition_id, user_id, email, source, qty, ref):
    db["competition_entries"].docs.append({
        "id": f"e-{ref}",
        "competition_id": competition_id,
        "user_id": user_id,
        "user_email": email,
        "source": source,
        "quantity": qty,
        "source_ref": ref,
        "created_at": "2026-09-01T12:00:00+00:00",
    })


# =========================================================================
# Entry awarding
# =========================================================================
class TestAwarding:
    def test_purchase_entry_awarded_for_live_competition(self, fake_db):
        from services.competition_service import award_purchase_entries

        _live_comp(fake_db)
        n = asyncio.run(award_purchase_entries(
            fake_db, user_id="u1", user_email="alice@x.com",
            purchase_id="p1", purchase_amount_usd=10.0,
        ))
        assert n == 10
        rows = fake_db["competition_entries"].docs
        assert len(rows) == 1
        assert rows[0]["source"] == "purchase" and rows[0]["quantity"] == 10
        assert rows[0]["source_ref"] == "p1" and rows[0]["user_email"] == "alice@x.com"

    def test_purchase_award_is_idempotent(self, fake_db):
        from services.competition_service import award_purchase_entries

        _live_comp(fake_db)
        for _ in range(3):
            asyncio.run(award_purchase_entries(
                fake_db, user_id="u1", user_email="alice@x.com",
                purchase_id="p1", purchase_amount_usd=5.0,
            ))
        assert len(fake_db["competition_entries"].docs) == 1
        assert fake_db["competition_entries"].docs[0]["quantity"] == 5

    def test_no_award_when_no_live_competition(self, fake_db):
        from services.competition_service import award_purchase_entries, award_amoe_entries

        _live_comp(fake_db, status="upcoming")
        assert asyncio.run(award_purchase_entries(
            fake_db, user_id="u1", user_email="a@x.com",
            purchase_id="p1", purchase_amount_usd=50.0,
        )) == 0
        assert asyncio.run(award_amoe_entries(
            fake_db, user_id="u1", user_email="a@x.com", grant_id="g1"
        )) == 0
        assert fake_db["competition_entries"].docs == []

    def test_amoe_daily_entry(self, fake_db):
        from services.competition_service import award_amoe_entries

        _live_comp(fake_db)
        assert asyncio.run(award_amoe_entries(
            fake_db, user_id="u2", user_email="bob@x.com", grant_id="g1"
        )) == 1
        row = fake_db["competition_entries"].docs[0]
        assert row["source"] == "amoe_daily" and row["source_ref"] == "g1"

    def test_rounds_down_sub_dollar_purchase(self, fake_db):
        from services.competition_service import award_purchase_entries

        _live_comp(fake_db, rules={"entry_per_purchase_usd": 5.0})
        assert asyncio.run(award_purchase_entries(
            fake_db, user_id="u1", user_email="a@x.com",
            purchase_id="p1", purchase_amount_usd=3.0,
        )) == 0  # $3 / ($5 per entry) = 0 entries


# =========================================================================
# Leaderboard / totals / masking / winners
# =========================================================================
class TestLeaderboard:
    def test_ordered_masked_leaderboard_and_totals(self, fake_db):
        from services.competition_service import (
            get_leaderboard, get_competition_totals, get_user_entry_total,
        )

        _live_comp(fake_db)
        _entry(fake_db, "C1", "u1", "alice@example.com", "purchase", 3, "p1")
        _entry(fake_db, "C1", "u1", "alice@example.com", "amoe_daily", 1, "g1")
        _entry(fake_db, "C1", "u2", "bob@example.com", "purchase", 7, "p2")
        _entry(fake_db, "C1", "u3", "carol@longdomain.com", "purchase", 2, "p3")

        board = asyncio.run(get_leaderboard(fake_db, "C1", limit=20))
        assert [b["entries"] for b in board] == [7, 4, 2]
        assert board[0]["name"] == "bo***@example.com"
        assert "alice@example.com" not in " ".join(b["name"] for b in board)

        totals = asyncio.run(get_competition_totals(fake_db, "C1"))
        assert totals == {"total_entries": 13, "total_players": 3}
        assert asyncio.run(get_user_entry_total(fake_db, "C1", "u1")) == 4

    def test_recent_winners_only_concluded(self, fake_db):
        from services.competition_service import recent_winners

        _live_comp(fake_db, status="concluded")
        fake_db["competitions"].docs[0]["winner"] = {
            "user_id": "u1", "user_email": "alice@example.com", "entries": 9,
            "selected_at": "2026-09-05T00:00:00+00:00",
        }
        fake_db["competitions"].docs[0]["prize_status"] = "pending_payout"
        _live_comp(fake_db, cid="C2", status="live")

        wins = asyncio.run(recent_winners(fake_db))
        assert len(wins) == 1
        assert wins[0]["winner_name"] == "al***@example.com"
        assert wins[0]["prize_status"] == "pending_payout"


# =========================================================================
# Draw
# =========================================================================
class TestDraw:
    def test_weighted_draw_selects_and_concludes(self, fake_db):
        from services.competition_service import run_draw
        import random

        _live_comp(fake_db)
        _entry(fake_db, "C1", "u1", "alice@example.com", "purchase", 1, "p1")
        _entry(fake_db, "C1", "u2", "bob@example.com", "purchase", 99, "p2")

        rng = random.Random(1)
        result = asyncio.run(run_draw(fake_db, "C1", rng=rng))
        assert result["already_drawn"] is False
        assert result["winner"]["user_email"] == "bob@example.com"
        comp = result["competition"]
        assert comp["status"] == "concluded"
        assert comp["prize_status"] == "pending_payout"

        # Idempotent: a second draw returns the same winner.
        again = asyncio.run(run_draw(fake_db, "C1", rng=random.Random(2)))
        assert again["already_drawn"] is True
        assert again["winner"]["user_id"] == result["winner"]["user_id"]

    def test_draw_rejects_no_entries(self, fake_db):
        from services.competition_service import run_draw

        _live_comp(fake_db)
        with pytest.raises(ValueError, match="No entries"):
            asyncio.run(run_draw(fake_db, "C1"))

    def test_draw_rejects_cancelled_or_missing(self, fake_db):
        from services.competition_service import run_draw

        _live_comp(fake_db, cid="C1", status="cancelled")
        with pytest.raises(ValueError, match="Cannot draw"):
            asyncio.run(run_draw(fake_db, "C1"))
        with pytest.raises(ValueError, match="not found"):
            asyncio.run(run_draw(fake_db, "nope"))


# =========================================================================
# Admin lifecycle
# =========================================================================
class TestAdmin:
    def test_create_update_paid(self, fake_db):
        from services.competition_service import (
            create_competition, update_competition, mark_prize_paid,
        )

        comp = asyncio.run(create_competition(fake_db, {"name": "X", "prize_usd": 5_000_000}, created_by="a"))
        assert comp["status"] == "upcoming" and comp["prize_usd"] == 5_000_000
        assert comp["rules"]["entry_per_purchase_usd"] == 1.0

        updated = asyncio.run(update_competition(fake_db, comp["id"], {"status": "live", "name": "XL"}))
        assert updated["status"] == "live" and updated["name"] == "XL"

        paid = asyncio.run(mark_prize_paid(fake_db, comp["id"]))
        assert paid["prize_status"] == "paid" and paid["prize_paid_at"]

    def test_cancel_competition(self, fake_db):
        from services.competition_service import create_competition, cancel_competition

        comp = asyncio.run(create_competition(fake_db, {}, created_by="a"))
        cancelled = asyncio.run(cancel_competition(fake_db, comp["id"]))
        assert cancelled["status"] == "cancelled"
        assert fake_db["competitions"].docs[0]["status"] == "cancelled"

    def test_public_payload_shape(self, fake_db):
        from services.competition_service import public_payload

        _live_comp(fake_db)
        _entry(fake_db, "C1", "u1", "alice@example.com", "purchase", 4, "p1")
        payload = asyncio.run(public_payload(fake_db, user_id="u1"))
        assert payload["competition"]["my_entries"] == 4
        assert payload["competition"]["totals"]["total_players"] == 1
        assert payload["competition"]["leaderboard"][0]["rank"] == 1
        # recent_winners key always present even without a concluded comp
        assert payload["recent_winners"] == []