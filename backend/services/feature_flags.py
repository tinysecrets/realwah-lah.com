"""Feature flags — admin-toggleable without backend restart.

Stored in `app_settings` collection as {key, value, updated_at, updated_by}.
Cached in-memory for 10s to keep hot paths fast.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Optional

# Defaults: shipped OFF so a fresh deploy is conservative.
DEFAULT_FLAGS: Dict[str, Any] = {
    "btc_payouts_enabled": False,          # master kill switch for BTC redemption
    "giftcard_redemption_enabled": True,   # fallback path while BTC is off
    "redeem_tab_visible": True,            # show the Redeem tab to users
    "withdraw_tab_visible": False,         # hide the Withdraw tab until BTC is on
}

_cache: Dict[str, Any] = {}
_cache_at: float = 0.0
_lock = asyncio.Lock()
TTL = int(os.environ.get("FLAG_CACHE_TTL_SECONDS", "10"))


async def _refresh(db) -> None:
    """Populate _cache from DB, layered over DEFAULT_FLAGS."""
    global _cache, _cache_at
    flags = dict(DEFAULT_FLAGS)
    cursor = db["app_settings"].find({}, {"_id": 0, "key": 1, "value": 1})
    async for row in cursor:
        key = row.get("key")
        if key in DEFAULT_FLAGS:
            flags[key] = row.get("value")
    _cache = flags
    _cache_at = time.time()


async def get_flags(db) -> Dict[str, Any]:
    async with _lock:
        if not _cache or (time.time() - _cache_at) > TTL:
            await _refresh(db)
        return dict(_cache)


async def get_flag(db, key: str) -> Any:
    flags = await get_flags(db)
    return flags.get(key, DEFAULT_FLAGS.get(key))


async def set_flag(db, key: str, value: Any, actor: Optional[str] = None) -> Dict[str, Any]:
    if key not in DEFAULT_FLAGS:
        raise ValueError(f"unknown flag: {key}")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await db["app_settings"].update_one(
        {"key": key},
        {"$set": {"key": key, "value": value, "updated_at": now, "updated_by": actor}},
        upsert=True,
    )
    # Invalidate cache so next read hits DB.
    global _cache_at
    _cache_at = 0.0
    return await get_flags(db)
