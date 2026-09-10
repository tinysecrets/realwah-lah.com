"""Self-contained tests for the unified money feed.

Proves the Ledger fix at the source-of-truth layer (services.money_feed)
rather than at the UI symptom:
- every rail normalizes (incl. the previously missing giftcard kind)
- player scoping resolves str ids, legacy ObjectIds, and email fallback
- other players' rows never leak into a scoped feed
- private fields (btc_address, actor) strip for players, stay for admins
- admin feed and player Ledger are the same function (parity by construction)
- summary math + kind validation

Registered in conftest.SELF_CONTAINED_FILES so it always runs in CI.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bson import ObjectId

from services.money_feed import VALID_KINDS, get_feed, normalize_tx, summarize


def run(awaitable):
    return asyncio.run(awaitable)


# --------------------------------------------------------------------------
# Fake async mongo (subset: find().sort().limit().to_list())
# --------------------------------------------------------------------------
class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, _key, _direction):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, length):
        return list(self._docs[:length])


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, _query=None):
        return FakeCursor(self.docs)


class FakeDB:
    def __init__(self, seed):
        self._cols = {k: FakeCollection(v) for k, v in seed.items()}

    def __getitem__(self, name):
        return self._cols.setdefault(name, FakeCollection())


UID = "507f1f77bcf86cd799439011"  # str(ObjectId(...)) shaped, like JWT sub
OID = ObjectId(UID)
OTHER = "507f1f77bcf86cd799439022"


def _seed():
    """Fixtures mirror the real insert shapes (reconcile, redemption,
    giftcard, adjustment writers)."""
    return {
        "sugar_token_purchases": [
            {"id": "p1", "user_id": UID, "user_email": "a@x.com",
             "amount_usd": 25.0, "sugar_tokens": 2500,
             "purchase_type": "card", "status": "completed",
             "created_at": "2026-09-01T10:00:00+00:00"},
        ],
        "btc_deposits": [
            {"id": "b1", "user_id": OID, "user_email": "a@x.com",
             "amount_usd": 100.0, "net_usd": 90.0, "fee_usd": 10.0,
             "platform": "Fire Kirin", "tx_hash": "abc123",
             "pool_transfer_status": "done", "status": "completed",
             "created_at": "2026-09-02T10:00:00+00:00"},
            {"id": "b-other", "user_id": OTHER, "user_email": "zzz@x.com",
             "amount_usd": 999.0, "status": "completed",
             "created_at": "2026-09-02T11:00:00+00:00"},
        ],
        "manual_deposits": [
            {"id": "m1", "user_id": UID, "user_email": "a@x.com",
             "amount_usd": 25.0, "net_usd": 22.0, "fee_usd": 3.0,
             "receipt": "CA-1", "status": "completed",
             "created_at": "2026-09-03T10:00:00+00:00"},
        ],
        "redemption_requests": [
            {"id": "r1", "user_id": UID, "user_email": "a@x.com",
             "game_credits": 5000, "amount_usd": 50.0,
             "btc_address": "bc1qplayer", "status": "approved",
             "created_at": "2026-09-04T10:00:00+00:00"},
        ],
        "gift_card_redemptions": [
            {"id": "g1", "user_id": UID, "user_email": "a@x.com",
             "amount_usd": 25.0, "gross_usd": 25.0, "fee_usd": 1.25,
             "brand_label": "Amazon", "status": "fulfilled",
             "fulfilled_at": "2026-09-05T10:00:00+00:00",
             "created_at": "2026-09-05T09:00:00+00:00"},
        ],
        "bonus_credit_grants": [
            {"id": "gr1", "user_id": UID, "user_email": "a@x.com",
             "game_credits": 100, "grant_type": "amoe",
             "status": "granted", "created_at": "2026-09-06T10:00:00+00:00"},
        ],
        "credit_adjustments": [
            {"user_id": UID, "user_email": "a@x.com",
             "set": {}, "inc": {"game_credits": 500}, "note": "comp",
             "actor": "boss@x.com", "created_at": "2026-09-07T10:00:00+00:00"},
        ],
    }


class TestNormalize:
    def test_giftcard_kind_present(self):
        row = normalize_tx("giftcard", _seed()["gift_card_redemptions"][0])
        assert row["kind"] == "giftcard"
        assert row["amount_usd"] == 25.0
        assert row["brand"] == "Amazon"
        assert "giftcard" in VALID_KINDS

    def test_objectid_user_id_stringified(self):
        row = normalize_tx("btc_deposit", _seed()["btc_deposits"][0])
        assert row["user_id"] == UID


class TestFeed:
    def test_admin_sees_everything(self):
        feed = run(get_feed(FakeDB(_seed())))
        assert feed["total"] == 8  # 7 mine + 1 stranger's

    def test_player_scoped_to_own_rows(self):
        feed = run(get_feed(FakeDB(_seed()), user_id=UID,
                            user_email="a@x.com", strip_private=True))
        assert feed["total"] == 7
        assert all(r["user_id"] == UID for r in feed["transactions"])
        # newest first
        assert feed["transactions"][0]["kind"] == "adjustment"

    def test_legacy_objectid_rows_match_str_user_id(self):
        feed = run(get_feed(FakeDB(_seed()), user_id=UID, strip_private=True))
        kinds = {r["kind"] for r in feed["transactions"]}
        assert "btc_deposit" in kinds  # stored as ObjectId, still resolves

    def test_email_fallback_matches(self):
        seed = _seed()
        seed["btc_deposits"][0]["user_id"] = None  # id missing, email present
        feed = run(get_feed(FakeDB(seed), user_id="nobody",
                            user_email="a@x.com", strip_private=True))
        assert feed["total"] == 7

    def test_stranger_excluded(self):
        feed = run(get_feed(FakeDB(_seed()), user_id=UID, strip_private=True))
        blob = str(feed["transactions"])
        assert "zzz@x.com" not in blob
        assert "999" not in blob

    def test_private_fields_stripped_for_players(self):
        feed = run(get_feed(FakeDB(_seed()), user_id=UID, strip_private=True))
        blob = str(feed["transactions"])
        assert "bc1qplayer" not in blob
        assert "boss@x.com" not in blob

    def test_private_fields_kept_for_admins(self):
        feed = run(get_feed(FakeDB(_seed())))
        blob = str(feed["transactions"])
        assert "bc1qplayer" in blob
        assert "boss@x.com" in blob

    def test_kind_filter_and_pagination(self):
        db = FakeDB(_seed())
        only = run(get_feed(db, kind="giftcard"))
        assert only["total"] == 1
        page = run(get_feed(db, skip=7, limit=50))
        assert len(page["transactions"]) == 1
        assert page["total"] == 8

    def test_unknown_kind_rejected(self):
        with pytest.raises(ValueError):
            run(get_feed(FakeDB(_seed()), kind="nope"))


class TestSummary:
    def test_header_math(self):
        feed = run(get_feed(FakeDB(_seed()), user_id=UID, strip_private=True))
        s = summarize(feed["transactions"])
        assert s["deposited_usd"] == 125.0      # 100 BTC + 25 manual
        assert s["received_usd"] == 75.0        # 50 BTC + 25 gift card
        assert s["entries"] == 7
        assert s["pending_items"] == 0
