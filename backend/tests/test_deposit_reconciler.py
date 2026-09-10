"""Unit tests for the deposit reconciler.

Deterministic, network-free: BlockCypher calls and the real settle path are
monkeypatched. Covers the on-chain matching rules and the reconciliation pass
against a fake collection.
"""
from __future__ import annotations

import os

os.environ.setdefault("BTC_MIN_CONFIRMATIONS", "1")
os.environ.setdefault("DEPOSIT_RECONCILE_ENABLED", "false")

import pytest  # noqa: E402

from services import deposit_reconciler  # noqa: E402
from services.deposit_reconciler import pick_deposit_tx  # noqa: E402


class TestPickDepositTx:
    def test_perfect_match(self):
        txrefs = [{"tx_hash": "tx1", "value": 41667, "confirmations": 2}]
        assert pick_deposit_tx(txrefs, 41667) == ("tx1", 41667, "match")

    def test_within_tolerance(self):
        txrefs = [{"tx_hash": "tx1", "value": 43750, "confirmations": 1}]  # +5%
        assert pick_deposit_tx(txrefs, 41667, tolerance=0.10) == ("tx1", 43750, "match")

    def test_outbound_ignored(self):
        txrefs = [{"tx_hash": "tx1", "value": -5000, "confirmations": 5}]
        assert pick_deposit_tx(txrefs, 41667) == (None, None, "no_funds")

    def test_unconfirmed_ignored(self):
        txrefs = [{"tx_hash": "tx1", "value": 41667, "confirmations": 0}]
        assert pick_deposit_tx(txrefs, 41667) == (None, None, "no_funds")

    def test_amount_mismatch_surfaces(self):
        txrefs = [{"tx_hash": "tx1", "value": 125000, "confirmations": 3}]
        assert pick_deposit_tx(txrefs, 41667) == ("tx1", 125000, "amount_mismatch")

    def test_ambiguous_multiple_hashes(self):
        txrefs = [
            {"tx_hash": "tx1", "value": 41667, "confirmations": 2},
            {"tx_hash": "tx2", "value": 42000, "confirmations": 1},
        ]
        assert pick_deposit_tx(txrefs, 41667) == (None, None, "ambiguous")

    def test_empty(self):
        assert pick_deposit_tx([], 41667) == (None, None, "no_funds")

    def test_no_expected_uses_any_confirmed_inbound(self):
        txrefs = [{"tx_hash": "tx9", "value": 300, "confirmations": 6}]
        assert pick_deposit_tx(txrefs, 0) == ("tx9", 300, "match")


class FakeUpdateResult:
    def __init__(self, modified):
        self.modified_count = 1 if modified else 0


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, _key, _direction):
        return self

    def limit(self, _n):
        return self

    async def to_list(self, length=None):
        return self._docs[:length] if length is not None else self._docs


class FakeCollection:
    def __init__(self, docs):
        self.docs = docs
        self.updates = []

    def find(self, query=None):
        return FakeCursor(self.docs)

    async def update_one(self, filter, update):
        self.updates.append((filter, update))
        # Pretend the deposit still matched unless the filter is "impossible".
        return FakeUpdateResult(self.docs)


def _fake_complete(deposit_id, tx_hash, confirmations):
    async def inner(*args, **kwargs):
        return True, "settled-ok"
    return inner


@pytest.fixture
def deposit_factory():
    def make(**overrides):
        doc = {
            "id": "dep_1",
            "user_id": "u1",
            "user_email": "a@b.com",
            "amount_usd": 25.0,
            "btc_satoshis": 41667,
            "btc_address": "bc1abc",
            "status": "pending",
            "platform": None,
            "tx_hash": None,
            "confirmations": 0,
            "created_at": "2026-09-01T00:00:00+00:00",
        }
        doc.update(overrides)
        return doc

    return make


def test_pass_settles_address_match(monkeypatch, deposit_factory):
    db = type("DB", (), {"btc_deposits": FakeCollection([deposit_factory()])})()
    deposit_reconciler.CurrencyService.complete_btc_purchase = _fake_complete(
        "dep_1", "tx_matched", 1
    )

    async def fake_txrefs(address, limit=10):
        return [{"tx_hash": "tx_matched", "value": 41667, "confirmations": 2}]

    monkeypatch.setattr(deposit_reconciler.btc_processor, "fetch_address_txrefs", fake_txrefs)

    report = deposit_reconciler.run_reconcile_pass(db, min_age_seconds=0)
    assert asyncio_run(report)["settled"] == 1


def test_pass_repolls_recorded_tx(monkeypatch, deposit_factory):
    db = type("DB", (), {"btc_deposits": FakeCollection([deposit_factory(tx_hash="tx_rec", confirmations=0)])})()
    deposit_reconciler.CurrencyService.complete_btc_purchase = _fake_complete(
        "dep_1", "tx_rec", 3
    )

    async def fake_conf(tx_hash):
        assert tx_hash == "tx_rec"
        return 3

    monkeypatch.setattr(deposit_reconciler.btc_processor, "fetch_tx_confirmation_count", fake_conf)

    report = asyncio_run(deposit_reconciler.run_reconcile_pass(db, min_age_seconds=0))
    assert report["settled"] == 1
    assert report["completed"] == ["dep_1"]


def test_pass_waits_when_no_funds(monkeypatch, deposit_factory):
    col = FakeCollection([deposit_factory()])
    db = type("DB", (), {"btc_deposits": col})()

    async def fake_no_funds(address, limit=10):
        return []

    monkeypatch.setattr(
        deposit_reconciler.btc_processor,
        "fetch_address_txrefs",
        fake_no_funds,
    )

    report = asyncio_run(deposit_reconciler.run_reconcile_pass(db, min_age_seconds=0))
    assert report["settled"] == 0
    assert report["scanned"] == 1
    assert report["waiting"] == ["dep_1"]
    # The reason is parked on the deposit for the admin UI.
    assert col.updates, "expected an update recording the wait state"
    set_op = col.updates[0][1]
    assert set_op["$inc"]["reconcile_attempts"] == 1
    assert set_op["$set"]["reconcile_note"] == "no_funds"


def test_pass_handles_provider_failure(monkeypatch, deposit_factory):
    db = type("DB", (), {"btc_deposits": FakeCollection([deposit_factory(tx_hash="tx_x", confirmations=0)])})()

    async def fake_fail(tx_hash):
        return -1

    monkeypatch.setattr(
        deposit_reconciler.btc_processor, "fetch_tx_confirmation_count", fake_fail
    )

    report = asyncio_run(deposit_reconciler.run_reconcile_pass(db, min_age_seconds=0))
    assert report["settled"] == 0

    # private helper checked directly for the failure note
    async def single():
        col = db.btc_deposits
        r = await deposit_reconciler._reconcile_one(db, col.docs[0])
        return r

    result = asyncio_run(single())
    assert result["message"] == "could not reach block provider"


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)