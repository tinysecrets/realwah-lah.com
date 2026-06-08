"""State-level IP geoblock for sweepstakes compliance.

Uses ipapi.co (free tier, no key) to resolve client IP → US state. Blocks
users whose state is in the BLOCKED_STATES env var. If the lookup fails,
we default to ALLOW (soft-fail) and log — consult your attorney about
whether to switch this to fail-closed.

Common sweepstakes-prohibited states (fill per attorney advice):
  WA, ID, MT, NV, UT, AZ, LA, MD, NJ, NY, MI, TN, FL, RI
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


def _blocked_states() -> set[str]:
    raw = os.environ.get("BLOCKED_STATES", "").strip()
    if not raw:
        return set()
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


def list_blocked_states() -> list[str]:
    return sorted(_blocked_states())


async def _resolve_state(ip: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (state_code, country_code). None on lookup failure."""
    # Strip any port / proxy annotations.
    ip = (ip or "").split(",")[0].strip()
    if not ip or ip in ("127.0.0.1", "::1", "localhost"):
        return None, None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"https://ipapi.co/{ip}/json/")
            if r.status_code != 200:
                return None, None
            data = r.json()
            return (data.get("region_code") or "").upper() or None, (data.get("country_code") or "").upper() or None
    except Exception as e:
        logger.warning(f"Geoblock lookup failed for {ip}: {e}")
        return None, None


async def check_geoblock(ip: str) -> Tuple[bool, str, Optional[str]]:
    """Returns (is_blocked, reason, detected_state).

    Fails open (not blocked) on lookup error — a compliance officer should
    review the geoblock_events collection and escalate ambiguous cases.
    """
    blocked = _blocked_states()
    if not blocked:
        return False, "", None
    state, country = await _resolve_state(ip)
    if country and country != "US":
        # Non-US — sweepstakes is a US legal construct. Block outright.
        return True, f"non-US ({country})", state
    if state and state in blocked:
        return True, f"state {state} is in BLOCKED_STATES", state
    return False, "", state


async def record_geoblock_event(db, *, user_id: Optional[str], ip: str, state: Optional[str], blocked: bool, context: str) -> None:
    await db["geoblock_events"].insert_one({
        "user_id": user_id,
        "ip": ip,
        "state": state,
        "blocked": blocked,
        "context": context,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def client_ip_from_request(request) -> str:
    """Best-effort client IP extraction honoring common proxy headers."""
    fwd = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip") or request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    return (request.client.host if request.client else "") or ""
