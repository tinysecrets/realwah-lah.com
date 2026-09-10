"""Unit tests for the durable settlement stage machine (Phase 1, item 1).

Deterministic, network-free: the full CurrencyService stack is tested against a
FakeCollection that understands $or / $set / $push filters. Covers:
  - stage transition happy path (PENDING → … → COMPLETED)
  - expected_prior guard rejects concurrent duplicate advances
  - migration path for pre-existing deposits missing settlement_stage
  - RETRYABLE_FAILURE reset and re-claim
  - $push appends stage_history correctly
"""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("BTC_MIN_CONFIRMATIONS", "1")
os.environ.setdefault("DEPOSIT_RECONCILE_ENABLED", "false")

import pytest  # noqa: E402

from services.currency_service import CurrencyService, SETTLEMENT_STAGES  # noqa: E402


# ---------------------------------------------------------------------------
# Fake MongoDB helpers (subset of ops used by CurrencyService)
# ---------------------------------------------------------------------------

class _UpdateResult:
    def __init__(self, modified: int):
        self.modified_count = modified


def _match_or(doc: dict, or_clauses: list) -> bool:
    """Evaluate a Mongo-style $or against a document."""
    for clause in or_clauses:
        match = True
        for key, cond in clause.items():
            if isinstance(cond, dict) and "$exists" in cond:
                exists = key in doc
                match = match and (exists == cond["$exists"])
            else:
                match = match and (doc.get(key) == cond)
        if match:
            return True
    return False


class FakeCollection:
    """In-memory collection that supports find_one, insert_one, and update_one
    with $set, $push, and $or filters (the subset CurrencyService uses)."""

    def __init__(self, docs: list | None = None):
        self.docs: dict[str, dict] = {}
        self.updates: list = []
        for d in (docs or []):
            self.docs[d["id"]] = dict(d)

    # -- read --
    async def find_one(self, query: dict | None = None) -> dict | None:
        if not query:
            return next(iter(self.docs.values()), None)
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    async def insert_one(self, doc: dict):
        self.docs[doc["id"]] = dict(doc)

    # -- write --
    async def update_one(self, filter_doc: dict, update: dict) -> _UpdateResult:
        self.updates.append((filter_doc, update))
        target = None
        for doc in self.docs.values():
            # Check $or first
            if "$or" in filter_doc:
                if not _match_or(doc, filter_doc["$or"]):
                    continue
                target = doc
                break
            # Plain equality
            if all(doc.get(k) == v for k, v in filter_doc.items() if k != "$or"):
                target = doc
                break

        if target is None:
            return _UpdateResult(0)

        # Apply $set
        for k, v in update.get("$set", {}).items():
            target[k] = v
        # Apply $push
        for k, v in update.get("$push", {}).items():
            if k not in target:
                target[k] = []
            target[k].append(v)
        # Apply $unset
        for k in update.get("$unset", {}):
            target.pop(k, None)
        return _UpdateResult(1)

    # -- helpers for tests --
    def get(self, doc_id: str) -> dict | None:
        return self.docs.get(doc_id)

    def make_deposit(self, doc_id: str = "dep_1", **overrides) -> dict:
        doc = {
            "id": doc_id,
            "user_id": "u1",
            "user_email": "a@b.com",
            "amount_usd": 25.0,
            "sugar_tokens": 2500,
            "btc_address": "bc1test",
            "btc_satoshis": 41667,
            "btc_usd_rate": 600.0,
            "payment_reference": None,
            "deposit_index": None,
            "platform": None,
            "status": "pending",
            "confirmations": 0,
            "tx_hash": None,
            "created_at": "2026-09-01T00:00:00+00:00",
            "expires_at": "2026-09-02T00:00:00+00:00",
            "completed_at": None,
            "webhook_id": None,
            "settlement_stage": "PENDING",
            "stage_entered_at": "2026-09-01T00:00:00+00:00",
            "stage_history": [{"stage": "PENDING", "entered_at": "2026-09-01T00:00:00+00:00", "reason": "deposit created"}],
            "pool_transfer_status": "pending",
        }
        doc.update(overrides)
        return doc


class FakeDB:
    def __init__(self, deposits: list | None = None):
        self.btc_deposits = FakeCollection(deposits or [])

    def __getitem__(self, name: str):
        # Mirror Motor's db[collection] access used by CurrencyService.
        return getattr(self, name)


# ---------------------------------------------------------------------------
# Tests: _advance_settlement_stage
# ---------------------------------------------------------------------------

class TestAdvanceSettlementStage:
    """Tests for the internal stage transition method."""

    def _svc(self, db: FakeDB) -> CurrencyService:
        return CurrencyService(db)

    @pytest.mark.asyncio
    async def test_unconditional_advance(self):
        """Stage advances without expected_prior always succeeds."""
        dep = FakeCollection().make_deposit()
        db = FakeDB([dep])
        svc = self._svc(db)

        ok = await svc._advance_settlement_stage("dep_1", "VERIFYING", reason="test")
        assert ok is True

        doc = db.btc_deposits.get("dep_1")
        assert doc["settlement_stage"] == "VERIFYING"
        assert doc["status"] == "settling"
        assert len(doc["stage_history"]) == 2
        assert doc["stage_history"][1]["stage"] == "VERIFYING"

    @pytest.mark.asyncio
    async def test_expected_prior_guard_accepts(self):
        """Stage advances when expected_prior matches current stage."""
        dep = FakeCollection().make_deposit(settlement_stage="SETTLING")
        db = FakeDB([dep])
        svc = self._svc(db)

        ok = await svc._advance_settlement_stage(
            "dep_1", "LEDGER_COMMITTED", expected_prior="SETTLING"
        )
        assert ok is True

        doc = db.btc_deposits.get("dep_1")
        assert doc["settlement_stage"] == "LEDGER_COMMITTED"

    @pytest.mark.asyncio
    async def test_expected_prior_guard_rejects(self):
        """Stage advance fails when expected_prior does not match."""
        dep = FakeCollection().make_deposit(settlement_stage="PENDING")
        db = FakeDB([dep])
        svc = self._svc(db)

        ok = await svc._advance_settlement_stage(
            "dep_1", "LEDGER_COMMITTED", expected_prior="SETTLING"
        )
        assert ok is False

        doc = db.btc_deposits.get("dep_1")
        assert doc["settlement_stage"] == "PENDING"

    @pytest.mark.asyncio
    async def test_migration_missing_settlement_stage(self):
        """Pre-migration deposit with no settlement_stage field can be claimed."""
        dep = FakeCollection().make_deposit()
        dep.pop("settlement_stage", None)
        dep.pop("stage_entered_at", None)
        dep.pop("stage_history", None)
        db = FakeDB([dep])
        svc = self._svc(db)

        ok = await svc._advance_settlement_stage(
            "dep_1", "SETTLING", expected_prior="PENDING"
        )
        assert ok is True

        doc = db.btc_deposits.get("dep_1")
        assert doc["settlement_stage"] == "SETTLING"
        assert doc["status"] == "settling"

    @pytest.mark.asyncio
    async def test_completed_sets_coarse_status(self):
        """COMPLETED stage sets coarse status to 'completed'."""
        dep = FakeCollection().make_deposit(settlement_stage="BONUS_COMMITTED")
        db = FakeDB([dep])
        svc = self._svc(db)

        ok = await svc._advance_settlement_stage(
            "dep_1", "COMPLETED", expected_prior="BONUS_COMMITTED"
        )
        assert ok is True

        doc = db.btc_deposits.get("dep_1")
        assert doc["status"] == "completed"

    @pytest.mark.asyncio
    async def test_retryable_failure_keeps_settling_coarse(self):
        """RETRYABLE_FAILURE keeps coarse status as 'settling' so reconciler retries."""
        dep = FakeCollection().make_deposit(settlement_stage="SETTLING")
        db = FakeDB([dep])
        svc = self._svc(db)

        ok = await svc._advance_settlement_stage(
            "dep_1", "RETRYABLE_FAILURE", expected_prior="SETTLING"
        )
        assert ok is True

        doc = db.btc_deposits.get("dep_1")
        assert doc["status"] == "settling"

    @pytest.mark.asyncio
    async def test_invalid_stage_rejected(self):
        """Unknown stage name is rejected."""
        dep = FakeCollection().make_deposit()
        db = FakeDB([dep])
        svc = self._svc(db)

        ok = await svc._advance_settlement_stage("dep_1", "NOT_A_STAGE")
        assert ok is False

    @pytest.mark.asyncio
    async def test_stage_history_grows(self):
        """Each transition appends to stage_history (immutable log)."""
        dep = FakeCollection().make_deposit()
        db = FakeDB([dep])
        svc = self._svc(db)

        await svc._advance_settlement_stage("dep_1", "VERIFYING")
        await svc._advance_settlement_stage("dep_1", "SETTLING")
        await svc._advance_settlement_stage("dep_1", "LEDGER_COMMITTED")
        await svc._advance_settlement_stage("dep_1", "BONUS_COMMITTED")
        await svc._advance_settlement_stage("dep_1", "COMPLETED")

        doc = db.btc_deposits.get("dep_1")
        stages = [e["stage"] for e in doc["stage_history"]]
        assert stages == ["PENDING", "VERIFYING", "SETTLING", "LEDGER_COMMITTED", "BONUS_COMMITTED", "COMPLETED"]


# ---------------------------------------------------------------------------
# Tests: concurrent advance (race condition)
# ---------------------------------------------------------------------------

class TestConcurrentAdvance:
    """Simulate two concurrent callers racing to claim SETTLING."""

    @pytest.mark.asyncio
    async def test_only_one_wins(self):
        dep = FakeCollection().make_deposit(settlement_stage="VERIFYING")
        db = FakeDB([dep])
        svc = CurrencyService(db)

        # Both callers try SETTLING from VERIFYING. Only one should succeed
        # because the FakeCollection's update_one modifies in place, so the
        # second call sees SETTLING (not VERIFYING) and the guard rejects it.
        r1 = await svc._advance_settlement_stage(
            "dep_1", "SETTLING", expected_prior="VERIFYING"
        )
        r2 = await svc._advance_settlement_stage(
            "dep_1", "SETTLING", expected_prior="VERIFYING"
        )

        assert r1 is True
        assert r2 is False

        doc = db.btc_deposits.get("dep_1")
        assert doc["settlement_stage"] == "SETTLING"


# ---------------------------------------------------------------------------
# Tests: full happy-path stage progression
# ---------------------------------------------------------------------------

class TestFullStagePath:
    """Walk through the entire stage machine for a fresh deposit."""

    @pytest.mark.asyncio
    async def test_pending_to_completed(self):
        dep = FakeCollection().make_deposit()
        db = FakeDB([dep])
        svc = CurrencyService(db)

        stages = [
            ("VERIFYING", {}),
            # VERIFYING was just recorded, so the settle-claim follows the
            # app's own reclaim path (guarded on VERIFYING), not PENDING.
            ("SETTLING", {"expected_prior": "VERIFYING"}),
            ("LEDGER_COMMITTED", {"expected_prior": "SETTLING"}),
            ("BONUS_COMMITTED", {"expected_prior": "LEDGER_COMMITTED"}),
            ("COMPLETED", {"expected_prior": "BONUS_COMMITTED"}),
        ]

        for stage, kwargs in stages:
            ok = await svc._advance_settlement_stage("dep_1", stage, **kwargs)
            assert ok is True, f"Failed to advance to {stage}"

        doc = db.btc_deposits.get("dep_1")
        assert doc["settlement_stage"] == "COMPLETED"
        assert doc["status"] == "completed"
        # PENDING + 5 transitions
        assert len(doc["stage_history"]) == 6
        assert [e["stage"] for e in doc["stage_history"]] == [
            "PENDING", "VERIFYING", "SETTLING", "LEDGER_COMMITTED",
            "BONUS_COMMITTED", "COMPLETED",
        ]


# ---------------------------------------------------------------------------
# Tests: retryable failure → re-claim
# ---------------------------------------------------------------------------

class TestRetryableFailure:
    """RETRYABLE_FAILURE should allow the deposit to be re-claimed."""

    @pytest.mark.asyncio
    async def test_failure_then_reclaim(self):
        dep = FakeCollection().make_deposit(settlement_stage="SETTLING")
        db = FakeDB([dep])
        svc = CurrencyService(db)

        # Fail
        ok = await svc._advance_settlement_stage(
            "dep_1", "RETRYABLE_FAILURE", expected_prior="SETTLING"
        )
        assert ok is True
        doc = db.btc_deposits.get("dep_1")
        assert doc["settlement_stage"] == "RETRYABLE_FAILURE"
        assert doc["status"] == "settling"

        # Re-claim: advance from RETRYABLE_FAILURE back to SETTLING
        ok = await svc._advance_settlement_stage(
            "dep_1", "SETTLING", expected_prior="RETRYABLE_FAILURE"
        )
        assert ok is True
        doc = db.btc_deposits.get("dep_1")
        assert doc["settlement_stage"] == "SETTLING"

    @pytest.mark.asyncio
    async def test_full_failure_reclaim_path(self):
        """Failure at LEDGER_COMMITTED → RETRYABLE_FAILURE → re-claim SETTLING → finish."""
        dep = FakeCollection().make_deposit(settlement_stage="SETTLING")
        db = FakeDB([dep])
        svc = CurrencyService(db)

        # Fail at ledger
        await svc._advance_settlement_stage(
            "dep_1", "LEDGER_COMMITTED", expected_prior="SETTLING"
        )
        await svc._advance_settlement_stage(
            "dep_1", "RETRYABLE_FAILURE", expected_prior="LEDGER_COMMITTED"
        )

        # Re-claim
        ok = await svc._advance_settlement_stage(
            "dep_1", "SETTLING", expected_prior="RETRYABLE_FAILURE"
        )
        assert ok is True

        # Continue
        await svc._advance_settlement_stage("dep_1", "LEDGER_COMMITTED", expected_prior="SETTLING")
        await svc._advance_settlement_stage("dep_1", "BONUS_COMMITTED", expected_prior="LEDGER_COMMITTED")
        await svc._advance_settlement_stage("dep_1", "COMPLETED", expected_prior="BONUS_COMMITTED")

        doc = db.btc_deposits.get("dep_1")
        assert doc["settlement_stage"] == "COMPLETED"
        assert doc["status"] == "completed"


# ---------------------------------------------------------------------------
# Tests: SETTLEMENT_STAGES constant
# ---------------------------------------------------------------------------

class TestSettlementStagesConstant:
    def test_expected_stages_present(self):
        expected = {
            "PENDING", "VERIFYING", "SETTLING", "LEDGER_COMMITTED",
            "BONUS_COMMITTED", "TRANSFER_PENDING", "COMPLETED", "RETRYABLE_FAILURE",
        }
        assert set(SETTLEMENT_STAGES) == expected

    def test_is_tuple(self):
        assert isinstance(SETTLEMENT_STAGES, tuple)
