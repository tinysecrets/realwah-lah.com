"""KYC state machine and tiered-threshold logic.

Two tiers:
  basic    — required for redemptions ≥ KYC_BASIC_THRESHOLD_USD ($500 default)
  enhanced — required for redemptions ≥ KYC_ENHANCED_THRESHOLD_USD ($5000 default)

KYC status per user per tier lives in `kyc_profiles`:
  {
    user_id, tier, status, method, inquiry_id?, uploaded_doc_id?,
    reviewer_id?, reviewer_notes?, decided_at?, created_at, updated_at,
    extracted_data? (from Persona)
  }

Statuses: not_started | pending | approved | declined | review
Methods: persona | manual_upload | admin_granted

Every status transition is recorded in `kyc_events` (immutable audit log,
compound index on (user_id, tier, created_at)).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

KYC_BASIC_THRESHOLD_USD = float(os.environ.get("KYC_BASIC_THRESHOLD_USD", "500"))
KYC_ENHANCED_THRESHOLD_USD = float(os.environ.get("KYC_ENHANCED_THRESHOLD_USD", "5000"))

TIER_BASIC = "basic"
TIER_ENHANCED = "enhanced"

STATUSES = ("not_started", "pending", "approved", "declined", "review")


def required_kyc_tier(amount_usd: float) -> Optional[str]:
    """Return the KYC tier required for the given redemption amount, or None."""
    if amount_usd >= KYC_ENHANCED_THRESHOLD_USD:
        return TIER_ENHANCED
    if amount_usd >= KYC_BASIC_THRESHOLD_USD:
        return TIER_BASIC
    return None


async def get_user_kyc_status(db, user_id: str, tier: str) -> Dict[str, Any]:
    doc = await db["kyc_profiles"].find_one({"user_id": user_id, "tier": tier}, {"_id": 0})
    if not doc:
        return {"user_id": user_id, "tier": tier, "status": "not_started"}
    return doc


async def is_user_cleared_for(db, user_id: str, amount_usd: float) -> tuple[bool, str, Optional[str]]:
    """Returns (cleared, reason, required_tier)."""
    tier = required_kyc_tier(amount_usd)
    if tier is None:
        return True, "below KYC threshold", None
    doc = await get_user_kyc_status(db, user_id, tier)
    status = doc.get("status")
    if status == "approved":
        # Enhanced approval implicitly satisfies basic.
        return True, "kyc_approved", tier
    if tier == TIER_BASIC:
        # Basic threshold met but enhanced approval also satisfies.
        enh = await get_user_kyc_status(db, user_id, TIER_ENHANCED)
        if enh.get("status") == "approved":
            return True, "enhanced_covers_basic", TIER_BASIC
    return False, f"kyc_{status}_for_{tier}", tier


async def record_kyc_event(
    db,
    *,
    user_id: str,
    tier: str,
    action: str,
    actor_id: Optional[str] = None,
    from_status: Optional[str] = None,
    to_status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    await db["kyc_events"].insert_one({
        "user_id": user_id,
        "tier": tier,
        "action": action,
        "actor_id": actor_id,
        "from_status": from_status,
        "to_status": to_status,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def upsert_kyc_profile(
    db,
    *,
    user_id: str,
    tier: str,
    status: str,
    method: str,
    actor_id: Optional[str] = None,
    inquiry_id: Optional[str] = None,
    uploaded_doc_id: Optional[str] = None,
    reviewer_notes: Optional[str] = None,
    extracted_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    assert status in STATUSES, f"invalid KYC status {status}"
    now = datetime.now(timezone.utc).isoformat()
    existing = await db["kyc_profiles"].find_one({"user_id": user_id, "tier": tier}) or {}
    update = {
        "user_id": user_id,
        "tier": tier,
        "status": status,
        "method": method,
        "updated_at": now,
    }
    if inquiry_id:
        update["inquiry_id"] = inquiry_id
    if uploaded_doc_id:
        update["uploaded_doc_id"] = uploaded_doc_id
    if reviewer_notes is not None:
        update["reviewer_notes"] = reviewer_notes
    if extracted_data is not None:
        update["extracted_data"] = extracted_data
    if status in ("approved", "declined"):
        update["decided_at"] = now
        update["reviewer_id"] = actor_id
    if not existing:
        update["created_at"] = now
    await db["kyc_profiles"].update_one(
        {"user_id": user_id, "tier": tier},
        {"$set": update},
        upsert=True,
    )
    await record_kyc_event(
        db,
        user_id=user_id,
        tier=tier,
        action=f"status_change:{method}",
        actor_id=actor_id,
        from_status=existing.get("status", "not_started"),
        to_status=status,
        metadata={"inquiry_id": inquiry_id, "uploaded_doc_id": uploaded_doc_id},
    )
    return update
