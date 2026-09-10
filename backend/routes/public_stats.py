"""Public proof endpoints — real numbers for the landing page.

These power the "Standing Ovations" payout feed and the stats band. Every
figure is computed live from the database; there are no hardcoded claims.

Privacy rules (non-negotiable for a PUBLIC, unauthenticated router):
- Player identities are masked to one initial + bullets (``j***``).
- No emails, no BTC addresses, no tx ids, no gift-card codes, no user ids.
- Only COMPLETED money-out counts: redemption_requests with status
  ``approved`` (BTC sent) and gift_card_redemptions with status
  ``fulfilled``. Pending/held/rejected rows never appear here.

Responses are cached in-memory for 60 seconds so landing-page traffic
never hammers Mongo.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Query

CACHE_TTL_SECONDS = 60

_cache: Dict[str, Any] = {}


def _cached(key: str, builder):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]
    value = builder()
    _cache[key] = (now, value)
    return value


def clear_public_stats_cache() -> None:
    """Test hook — drop cached proof payloads."""
    _cache.clear()


def mask_name(email: Any) -> str:
    """Turn ``jane@gmail.com`` into ``j***``. Never leaks the address."""
    if not email or not isinstance(email, str) or "@" not in email:
        return "a player"
    local = email.split("@", 1)[0].strip()
    if not local:
        return "a player"
    return f"{local[0].lower()}***"


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _paid_at(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key):
            return row[key]
    return row.get("created_at")


def build_public_stats_router(db) -> APIRouter:
    router = APIRouter(prefix="/public", tags=["public-proof"])

    async def _paid_redemptions() -> List[Dict[str, Any]]:
        cursor = db["redemption_requests"].find({"status": "approved"})
        return await cursor.to_list(length=5000)

    async def _fulfilled_giftcards() -> List[Dict[str, Any]]:
        cursor = db["gift_card_redemptions"].find({"status": "fulfilled"})
        return await cursor.to_list(length=5000)

    @router.get("/stats")
    async def public_stats():
        """Live headline numbers for the landing page stats band."""
        key = "public:stats"
        now = time.time()
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]

        redemptions = await _paid_redemptions()
        giftcards = await _fulfilled_giftcards()
        players = await db["users"].count_documents({"role": {"$ne": "admin"}})
        platforms = await db["games"].count_documents({"is_active": True})

        paid_out_usd = round(
            sum(_as_float(r.get("amount_usd")) for r in redemptions)
            + sum(_as_float(g.get("amount_usd")) for g in giftcards),
            2,
        )

        value = {
            "players": players,
            "paid_out_usd": paid_out_usd,
            "payouts_count": len(redemptions) + len(giftcards),
            "platforms": platforms,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _cache[key] = (now, value)
        return value

    @router.get("/payouts/recent")
    async def recent_payouts(
        limit: int = Query(default=12, ge=1, le=50),
    ):
        """Most recent completed payouts, player-masked. Newest first."""
        key = f"public:payouts:{limit}"
        now = time.time()
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]

        redemptions = await _paid_redemptions()
        giftcards = await _fulfilled_giftcards()

        feed: List[Dict[str, Any]] = []
        for r in redemptions:
            feed.append({
                "name": mask_name(r.get("user_email")),
                "amount_usd": round(_as_float(r.get("amount_usd")), 2),
                "method": "BTC",
                "paid_at": _paid_at(r, "completed_at", "approved_at"),
            })
        for g in giftcards:
            feed.append({
                "name": mask_name(g.get("user_email")),
                "amount_usd": round(_as_float(g.get("amount_usd")), 2),
                "method": str(g.get("brand_label") or g.get("brand") or "Gift card"),
                "paid_at": _paid_at(g, "fulfilled_at"),
            })

        feed.sort(key=lambda e: str(e.get("paid_at") or ""), reverse=True)
        value = {"payouts": feed[:limit], "count": len(feed)}
        _cache[key] = (now, value)
        return value

    return router
