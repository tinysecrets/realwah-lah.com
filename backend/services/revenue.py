"""
WAH-LAH Revenue Engine.

The platform makes money in three places, all configurable at runtime:

  1. CASHTAG_KEEP_RATE     — Cash App / Chime "convenience fee" applied when
                              admin marks a manual deposit as paid. Player who
                              sent $25 gets `25 * (1 - rate)` credits.
  2. GIFTCARD_FEE_RATE     — Redemption fee when player cashes out to a gift
                              card brand. Player asks for 25 credits → only
                              `25 * (1 - rate)` of card value gets fulfilled.
  3. BTC_FEE_RATE          — Same idea, on BTC redemption.

Defaults (env-driven; admins can override live via /api/admin/revenue/settings):
  CASHTAG_KEEP_RATE   = 0.12   (12%)
  GIFTCARD_FEE_RATE   = 0.05   (5%)
  BTC_FEE_RATE        = 0.10   (10%)

Every fee taken is written into `revenue_ledger` with:
  { kind, user_id, gross_usd, fee_usd, net_usd, ref_id, ref_kind, created_at }

so Justin can pull a real P&L at /api/admin/revenue/summary anytime.

Disclosure note: these fees ARE shown to the player on the relevant screen
(/api/payment/card-info for Cashtag, /api/giftcard/catalog for gift cards,
/api/redemption/quote for BTC). Hidden fees → chargebacks → dead Stripe
account. We disclose, we make money, we sleep at night.
"""
from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Literal

logger = logging.getLogger(__name__)

# In-memory cache of override rates. Refreshed from `revenue_settings` collection
# every time admin changes them. Falls back to env vars.
_RATE_CACHE: Dict[str, float] = {}


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _default_rate(kind: str) -> float:
    return {
        "cashtag": _env_float("CASHTAG_KEEP_RATE", 0.12),
        "giftcard": _env_float("GIFTCARD_FEE_RATE", 0.05),
        "btc": _env_float("BTC_FEE_RATE", 0.10),
    }.get(kind, 0.0)


async def get_rates(db) -> Dict[str, float]:
    """Load live rates from `revenue_settings` collection, fall back to env."""
    if _RATE_CACHE:
        return _RATE_CACHE.copy()
    doc = None
    try:
        doc = await db.revenue_settings.find_one({"_id": "current"})
    except Exception as e:
        logger.warning(f"revenue_settings fetch failed: {e}")
    rates = {
        "cashtag": (doc or {}).get("cashtag_keep_rate", _default_rate("cashtag")),
        "giftcard": (doc or {}).get("giftcard_fee_rate", _default_rate("giftcard")),
        "btc": (doc or {}).get("btc_fee_rate", _default_rate("btc")),
    }
    _RATE_CACHE.update(rates)
    return rates.copy()


async def set_rates(db, *, cashtag: Optional[float] = None,
                    giftcard: Optional[float] = None,
                    btc: Optional[float] = None,
                    updated_by: str = "system") -> Dict[str, float]:
    """Persist new rates and invalidate the cache."""
    update: Dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": updated_by,
    }
    if cashtag is not None:
        update["cashtag_keep_rate"] = max(0.0, min(0.5, float(cashtag)))
    if giftcard is not None:
        update["giftcard_fee_rate"] = max(0.0, min(0.5, float(giftcard)))
    if btc is not None:
        update["btc_fee_rate"] = max(0.0, min(0.5, float(btc)))

    await db.revenue_settings.update_one(
        {"_id": "current"},
        {"$set": update},
        upsert=True,
    )
    _RATE_CACHE.clear()  # force reload next call
    return await get_rates(db)


def apply_fee(gross_usd: float, rate: float) -> Dict[str, float]:
    """Split a gross dollar amount into net (to player) + fee (to house)."""
    gross = max(0.0, float(gross_usd))
    rate = max(0.0, min(0.99, float(rate)))
    fee = round(gross * rate, 2)
    net = round(gross - fee, 2)
    return {"gross_usd": gross, "fee_usd": fee, "net_usd": net, "rate": rate}


async def record_revenue(
    db,
    *,
    kind: Literal["cashtag", "giftcard", "btc"],
    user_id: Optional[str],
    gross_usd: float,
    fee_usd: float,
    net_usd: float,
    rate: float,
    ref_id: Optional[str] = None,
    ref_kind: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Insert a ledger row. Returns the entry id."""
    entry = {
        "id": str(uuid.uuid4()),
        "kind": kind,                            # cashtag | giftcard | btc
        "user_id": user_id,
        "gross_usd": round(float(gross_usd), 2),
        "fee_usd": round(float(fee_usd), 2),
        "net_usd": round(float(net_usd), 2),
        "rate": round(float(rate), 4),
        "ref_id": ref_id,                        # gift_card_redemption id, redemption_request id, payment_transaction id
        "ref_kind": ref_kind,                    # "gift_card" | "btc_redemption" | "cashtag_deposit"
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.revenue_ledger.insert_one(entry)
    except Exception as e:
        logger.error(f"revenue_ledger insert failed: {e}")
    return entry["id"]


async def revenue_summary(db, days: int = 30) -> Dict[str, Any]:
    """Aggregate revenue ledger for the dashboard."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = await db.revenue_ledger.find({"created_at": {"$gte": cutoff}}).to_list(10_000)

    by_kind: Dict[str, Dict[str, float]] = {}
    total_fee = 0.0
    total_gross = 0.0
    for r in rows:
        k = r.get("kind", "unknown")
        slot = by_kind.setdefault(k, {"gross_usd": 0.0, "fee_usd": 0.0, "count": 0})
        slot["gross_usd"] += float(r.get("gross_usd", 0))
        slot["fee_usd"] += float(r.get("fee_usd", 0))
        slot["count"] += 1
        total_fee += float(r.get("fee_usd", 0))
        total_gross += float(r.get("gross_usd", 0))

    # All-time totals (no date filter)
    all_time_fee = 0.0
    try:
        async for r in db.revenue_ledger.find({}, {"fee_usd": 1}):
            all_time_fee += float(r.get("fee_usd", 0))
    except Exception:
        pass

    rates = await get_rates(db)
    return {
        "window_days": days,
        "total_gross_usd": round(total_gross, 2),
        "total_fee_usd": round(total_fee, 2),
        "all_time_fee_usd": round(all_time_fee, 2),
        "by_kind": {k: {**v, "gross_usd": round(v["gross_usd"], 2),
                         "fee_usd": round(v["fee_usd"], 2)} for k, v in by_kind.items()},
        "current_rates": rates,
    }
