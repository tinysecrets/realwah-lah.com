"""AML (Bank Secrecy Act) event recording + threshold monitoring.

Records a timestamped event on every material money-movement action
(deposit, redemption, payout approval, KYC decision). Admin dashboards
query aggregations over this collection.

Two automatic triggers:
  CTR_THRESHOLD_USD (default $10,000) — single day cash-equivalent aggregate
  → raises an admin_alerts row of type "ctr_candidate"

  Pattern heuristic — ≥ 3 redemptions for same user within 24h
  → raises an admin_alerts row of type "sar_candidate"

A compliance officer reviews these before filing with FinCEN. We never
auto-file SAR/CTR forms — that's a human judgment call per BSA rules.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CTR_THRESHOLD_USD = float(os.environ.get("CTR_THRESHOLD_USD", "10000"))
SAR_FREQ_WINDOW_HOURS = int(os.environ.get("SAR_FREQ_WINDOW_HOURS", "24"))
SAR_FREQ_THRESHOLD = int(os.environ.get("SAR_FREQ_THRESHOLD", "3"))


async def record_aml_event(
    db,
    *,
    user_id: str,
    event_type: str,  # deposit | redemption_request | redemption_paid | kyc_decision
    amount_usd: float,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    now = datetime.now(timezone.utc)
    await db["aml_events"].insert_one({
        "user_id": user_id,
        "event_type": event_type,
        "amount_usd": float(amount_usd or 0),
        "metadata": metadata or {},
        "created_at": now.isoformat(),
        "created_date": now.date().isoformat(),
    })
    # Fire threshold checks in-line (cheap — single day aggregation).
    await check_ctr_threshold(db, user_id)
    await check_sar_frequency(db, user_id)


async def check_ctr_threshold(db, user_id: str) -> Optional[float]:
    """If user's same-day money-movement ≥ CTR_THRESHOLD_USD, raise admin alert.

    Returns the aggregated amount if triggered, None otherwise.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    pipeline = [
        {"$match": {"user_id": user_id, "created_date": today, "event_type": {"$in": ["deposit", "redemption_request", "redemption_paid"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}},
    ]
    agg = await db["aml_events"].aggregate(pipeline).to_list(1)
    if not agg:
        return None
    total = float(agg[0].get("total", 0))
    if total < CTR_THRESHOLD_USD:
        return None
    # Dedupe: one CTR alert per user per day.
    existing = await db["admin_alerts"].find_one({
        "type": "ctr_candidate",
        "user_id": user_id,
        "created_date": today,
    })
    if existing:
        return total
    await db["admin_alerts"].insert_one({
        "type": "ctr_candidate",
        "user_id": user_id,
        "amount_usd": total,
        "message": f"Aggregate same-day money movement ${total:,.2f} ≥ CTR threshold ${CTR_THRESHOLD_USD:,.2f}. Review for FinCEN Form 112 filing.",
        "status": "open",
        "severity": "high",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_date": today,
    })
    logger.warning(f"CTR candidate: user={user_id} amount=${total:.2f}")
    return total


async def check_sar_frequency(db, user_id: str) -> Optional[int]:
    """If user has ≥ SAR_FREQ_THRESHOLD redemption requests in SAR_FREQ_WINDOW_HOURS,
    raise a SAR-candidate alert for officer review."""
    window_start = (datetime.now(timezone.utc) - timedelta(hours=SAR_FREQ_WINDOW_HOURS)).isoformat()
    count = await db["aml_events"].count_documents({
        "user_id": user_id,
        "event_type": "redemption_request",
        "created_at": {"$gte": window_start},
    })
    if count < SAR_FREQ_THRESHOLD:
        return None
    # Dedupe: one SAR alert per user per window.
    existing = await db["admin_alerts"].find_one({
        "type": "sar_candidate",
        "user_id": user_id,
        "status": "open",
    })
    if existing:
        return count
    await db["admin_alerts"].insert_one({
        "type": "sar_candidate",
        "user_id": user_id,
        "message": f"{count} redemption attempts in {SAR_FREQ_WINDOW_HOURS}h window ≥ threshold {SAR_FREQ_THRESHOLD}. Officer to determine SAR filing.",
        "status": "open",
        "severity": "medium",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    logger.warning(f"SAR candidate (frequency): user={user_id} count={count}")
    return count
