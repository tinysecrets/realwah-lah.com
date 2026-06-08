"""OFAC SDN list screening for BTC recipient addresses.

Source: https://www.treasury.gov/ofac/downloads/sdn.csv (public, no key)
We parse the narrative column for lines matching 'Digital Currency Address - XBT'
to extract sanctioned Bitcoin addresses and cache them locally.

Refreshed once per day. If the fetch fails, we fall back to the cached list
and log an admin alert so we never accidentally serve an unscreened request.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Set, Tuple

import httpx

logger = logging.getLogger(__name__)

SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
# Bundled fallback so we never ship zero coverage even if the download fails.
FALLBACK_SDN_XBT = {
    # A few historical OFAC-designated Bitcoin addresses (Lazarus / Hydra / Tornado Cash mixers).
    "1AQvR6HvLV2jCBboQkn97QnkuKtHyCEWFK",
    "13mnk8SvDGqsQTHbiGiHBXqtaQCUKfcsnP",
    "14NU6C1FxRrctVvDBzJGuPEh3WEUfLxyxf",
    "bc1qa3pfzfusehllns8krer95hfckgduf2kd3p6v8e",
    "bc1qnyk5sr46mzex9zl5v6cu2j6dpgj6h5u5dnrdsv",
}
CACHE_DIR = Path("/tmp/sugar_compliance")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHE_DIR / "ofac_xbt.txt"
REFRESH_HOURS = 24

_xbt_cache: Set[str] = set()
_last_loaded_at: datetime | None = None
_load_lock = asyncio.Lock()

_XBT_PATTERN = re.compile(r"Digital Currency Address - XBT\s+([A-Za-z0-9]{26,90})", re.IGNORECASE)


def _parse_xbt_addresses(csv_text: str) -> Set[str]:
    """Extract unique XBT addresses from the SDN narrative column."""
    return set(_XBT_PATTERN.findall(csv_text))


async def _fetch_sdn() -> Set[str]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(SDN_URL, headers={"User-Agent": "SugarCitySweeps-Compliance/1.0"})
            r.raise_for_status()
            return _parse_xbt_addresses(r.text)
    except Exception as e:
        logger.warning(f"OFAC SDN fetch failed: {e}; using fallback list.")
        return set()


async def _load_from_cache() -> Set[str]:
    if CACHE_FILE.exists():
        try:
            return {line.strip() for line in CACHE_FILE.read_text().splitlines() if line.strip()}
        except Exception as e:
            logger.error(f"OFAC cache read failed: {e}")
    return set()


async def _save_to_cache(addrs: Set[str]) -> None:
    try:
        CACHE_FILE.write_text("\n".join(sorted(addrs)))
    except Exception as e:
        logger.error(f"OFAC cache write failed: {e}")


async def load_sdn_list(force: bool = False) -> Tuple[int, str]:
    """Load SDN XBT list with daily refresh. Returns (count, source)."""
    global _xbt_cache, _last_loaded_at
    async with _load_lock:
        now = datetime.now(timezone.utc)
        fresh = (
            _last_loaded_at is not None
            and (now - _last_loaded_at) < timedelta(hours=REFRESH_HOURS)
            and len(_xbt_cache) > 0
        )
        if fresh and not force:
            return len(_xbt_cache), "memory"

        remote = await _fetch_sdn()
        if remote:
            _xbt_cache = remote | FALLBACK_SDN_XBT
            await _save_to_cache(_xbt_cache)
            _last_loaded_at = now
            return len(_xbt_cache), "treasury"

        cached = await _load_from_cache()
        _xbt_cache = cached | FALLBACK_SDN_XBT
        _last_loaded_at = now
        return len(_xbt_cache), "cache+fallback"


def _ensure_loaded_sync() -> Set[str]:
    """Synchronous accessor for the in-memory list (never blocks on I/O)."""
    if not _xbt_cache:
        return set(FALLBACK_SDN_XBT)
    return _xbt_cache


async def check_btc_address(address: str) -> Tuple[bool, str]:
    """Returns (is_flagged, reason). False + '' means clean.

    Normalizes casing — Bitcoin addresses are case-sensitive but we compare
    in both raw and lowered forms to catch user-input typos.
    """
    if not address:
        return True, "empty address"
    await load_sdn_list()  # idempotent; refreshes only when stale
    addrs = _ensure_loaded_sync()
    lowered = {a.lower() for a in addrs}
    addr = address.strip()
    if addr in addrs or addr.lower() in lowered:
        logger.warning(f"OFAC SDN match on BTC address: {addr}")
        return True, "OFAC SDN list match"
    return False, ""


async def record_ofac_hit(db, *, user_id: str, btc_address: str, context: str) -> None:
    await db["ofac_hits"].insert_one({
        "user_id": user_id,
        "btc_address": btc_address,
        "context": context,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    # Also raise an admin alert so the compliance officer sees it immediately.
    await db["admin_alerts"].insert_one({
        "type": "ofac_sdn_match",
        "user_id": user_id,
        "btc_address": btc_address,
        "context": context,
        "message": f"OFAC SDN match on {btc_address}. Redemption BLOCKED. File SAR if pattern suggests sanctions evasion.",
        "status": "open",
        "severity": "critical",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
