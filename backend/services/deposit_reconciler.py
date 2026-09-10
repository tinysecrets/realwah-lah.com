"""Deposit reconciler — guarantees Bitcoin deposits settle.

The deposit lifecycle is webhook-driven (BlockCypher calls
``POST /api/webhooks/bitcoin`` when a tx confirms). If that webhook is ever
missed — subscription failure, BlockCypher downtime, a deploy racing the
callback — the deposit sits in ``pending`` forever and the customer never gets
their credits. The OnDuty watchdog flags these (``stale_pending_deposits``) but
nothing could recover them.

This service closes that gap. A background loop re-queries BlockCypher and
settles any deposit whose funds are actually confirmed on-chain:

1. If the deposit already remembers a ``tx_hash`` (a webhook saw it early), it
   re-polls that tx until its confirmations reach the required count.
2. Otherwise it fetches the deposit address digest and matches confirmed
   inbound transactions against the expected satoshi amount within a tolerance.

Settlement uses ``CurrencyService.complete_btc_purchase`` which is idempotent
and atomically claims the deposit, so the reconciler can race a late webhook
without ever double-crediting.

Unresolvable deposits (no funds, ambiguous, amount mismatch) stay ``pending`` so
the watchdog keeps alerting, and surface in the admin deposit-list endpoint for
manual resolution.

Knobs (env):
  DEPOSIT_RECONCILE_ENABLED        default "true"   — run the loop at all
  DEPOSIT_RECONCILE_INTERVAL_MIN   default "10"     — seconds between passes
  BTC_RECONCILE_MATCH_TOLERANCE    default "0.10"   — ±10% value match window
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from services import btc_processor
from services.currency_service import CurrencyService

logger = logging.getLogger(__name__)

# Only touch deposits older than this — young ones are still waiting for
# confirmations and the webhook.
DEFAULT_MIN_AGE_SECONDS = 15 * 60

# A deposit whose on-chain value is within this window of the expected amount
# (configurable to absorb small price drift between checkout and confirmation).
MATCH_TOLERANCE = float(os.getenv("BTC_RECONCILE_MATCH_TOLERANCE", "0.10"))


def pick_deposit_tx(
    txrefs: list[dict],
    expected_satoshis: Optional[int],
    tolerance: float = MATCH_TOLERANCE,
) -> tuple[Optional[str], Optional[int], str]:
    """Select the confirmed inbound tx that funds a deposit.

    Args:
        txrefs: BlockCypher address-digest txrefs (see
            ``btc_processor.fetch_address_txrefs``).
        expected_satoshis: the satoshi amount the checkout quoted.
        tolerance: how far a tx value may deviate and still count (0.10 = 10%).

    Returns:
        ``(tx_hash, value_satoshis, note)``. ``tx_hash`` is ``None`` when there
        is nothing to settle and note explains why:

        * ``match``          — exactly one confirmed inbound tx near the target
        * ``no_funds``       — no confirmed inbound tx to the address at all
        * ``unconfirmed``    — inbound tx exists but confirmations < 1
        * ``amount_mismatch``— funds arrived but nowhere near the quoted amount
        * ``ambiguous``      — multiple distinct tx hashes match the amount

    Outbound txrefs (value <= 0) are never considered.
    """
    effective = int(expected_satoshis or 0)
    seen: list[tuple[str, int, int]] = []
    for tx in txrefs or []:
        value = int(tx.get("value") or 0)
        conf = int(tx.get("confirmations") or 0)
        if value <= 0:
            continue
        if conf < 1:
            continue
        seen.append((str(tx.get("tx_hash") or ""), value, conf))

    if not seen:
        return None, None, "no_funds"

    if effective > 0:
        candidates = [
            (h, v)
            for h, v, _c in seen
            if abs(1.0 - v / effective) <= tolerance
        ]
    else:
        candidates = [(h, v) for h, v, _c in seen]

    if not candidates:
        # Money touched the address but not at the quoted amount — surface it
        # for a human; do NOT auto-settle a partial/incorrect deposit.
        best = max(seen, key=lambda t: t[1])
        return best[0], best[1], "amount_mismatch"

    hashes = {h for h, _v in candidates}
    if len(hashes) > 1:
        return None, None, "ambiguous"

    tx_hash, value = candidates[0]
    return tx_hash, value, "match"


async def _settle(db, deposit: dict, tx_hash: str, confirmations: int) -> dict:
    """Complete a deposit via the idempotent settle path.

    Returns a per-deposit result dict. ``completed`` is True when the deposit
    reached ``completed`` state (either now or already so).
    """
    result = {
        "deposit_id": deposit.get("id"),
        "tx_hash": tx_hash,
        "confirmations": max(confirmations, 1),
    }
    try:
        cs = CurrencyService(db)
        ok, msg = await cs.complete_btc_purchase(
            deposit_id=deposit.get("id"),
            tx_hash=tx_hash,
            confirmations=max(confirmations, 1),
        )
    except Exception as exc:  # noqa: BLE001 — record and continue the pass
        logger.exception("Reconcile settle failed for %s", deposit.get("id"))
        result["completed"] = False
        result["message"] = f"settle error: {exc}"
        return result
    result["completed"] = ok
    result["message"] = msg
    return result


async def _reconcile_one(db, deposit: dict) -> dict:
    """Reconcile a single pending/old-settling deposit against the chain."""
    deposit_id = deposit.get("id")
    address = deposit.get("btc_address")
    expected = int(deposit.get("btc_satoshis") or 0)
    required = btc_processor.MIN_CONFIRMATIONS
    recorded_hash = deposit.get("tx_hash") or ""
    recorded_conf = int(deposit.get("confirmations") or 0)

    # 1) If a webhook already saw a tx_hash, re-poll that specific tx.
    if recorded_hash and recorded_conf < required:
        now_conf = await btc_processor.fetch_tx_confirmation_count(recorded_hash)
        if now_conf < 0:
            return {
                "deposit_id": deposit_id,
                "completed": False,
                "message": "could not reach block provider",
                "note": "poll_failed",
            }
        await db.btc_deposits.update_one(
            {"id": deposit_id}, {"$set": {"confirmations": now_conf}}
        )
        if now_conf >= required:
            return await _settle(db, deposit, recorded_hash, now_conf)
        return {
            "deposit_id": deposit_id,
            "completed": False,
            "message": f"confirmed {now_conf}/{required}",
            "note": "unconfirmed",
        }

    # 2) Otherwise scan the deposit address for confirmed inbound funds.
    txrefs = await btc_processor.fetch_address_txrefs(address)
    matched_hash, value, note = pick_deposit_tx(txrefs, expected, MATCH_TOLERANCE)

    if matched_hash and note in ("match", "amount_mismatch"):
        return await _settle(db, deposit, matched_hash, required)

    # Nothing to settle yet — park the reason on the deposit and back off.
    await db.btc_deposits.update_one(
        {"id": deposit_id},
        {
            "$inc": {"reconcile_attempts": 1},
            "$set": {
                "reconcile_note": note,
                "last_reconcile_at": datetime.now(timezone.utc).isoformat(),
            },
        },
    )
    return {
        "deposit_id": deposit_id,
        "completed": False,
        "message": f"waiting: {note}",
        "note": note,
    }


async def run_reconcile_pass(
    db,
    min_age_seconds: int = DEFAULT_MIN_AGE_SECONDS,
    limit: int = 20,
) -> dict:
    """Scan unresolved deposits and settle the ones with confirmed funds.

    Includes ``pending`` deposits older than ``min_age_seconds`` plus
    ``settling`` deposits whose in-flight claim is similarly stale (a crashed
    settle must be retried, never left half-claimed).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=min_age_seconds)).isoformat()
    cursor = db.btc_deposits.find(
        {
            "$or": [
                {"status": "pending", "created_at": {"$lte": cutoff}},
                {"status": "settling", "settling_at": {"$lte": cutoff}},
            ]
        }
    ).sort("created_at", 1).limit(limit)

    deposits = await cursor.to_list(length=limit)
    results = []
    for deposit in deposits:
        results.append(await _reconcile_one(db, deposit))

    completed = [r for r in results if r.get("completed")]
    waiting = [r for r in results if not r.get("completed")]
    return {
        "scanned": len(deposits),
        "settled": len(completed),
        "completed": [r["deposit_id"] for r in completed],
        "waiting": [r["deposit_id"] for r in waiting],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


class DepositReconciler:
    """Long-lived background task that keeps deposits settled, restart-safe."""

    def __init__(self, db):
        self.db = db
        self.last_report: Optional[dict] = None
        self._task: Optional[asyncio.Task] = None
        self.enabled = os.getenv("DEPOSIT_RECONCILE_ENABLED", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        self._interval = max(60, int(os.getenv("DEPOSIT_RECONCILE_INTERVAL_MIN", "10"))) * 60

    def start(self) -> None:
        if not self.enabled:
            logger.info("Deposit reconciler disabled (DEPOSIT_RECONCILE_ENABLED=false).")
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        logger.info(
            "Deposit reconciler started (every %ss, settling confirmed-but-uncredited deposits).",
            self._interval,
        )
        while True:
            try:
                report = await run_reconcile_pass(self.db)
                self.last_report = report
                if report["settled"]:
                    logger.info("Reconcile pass settled %d deposits: %s", report["settled"], report["completed"])
                elif report["scanned"]:
                    logger.info("Reconcile pass scanned %d deposits, none ready.", report["scanned"])
            except Exception:  # noqa: BLE001 — reconciler must never die
                logger.exception("Deposit reconcile pass crashed")
            await asyncio.sleep(self._interval)