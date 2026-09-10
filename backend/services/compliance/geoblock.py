"""State-level IP geoblock for sweepstakes compliance.

Uses ipapi.co (free tier, no key) to resolve client IP → US state. Blocks
users whose state is in the BLOCKED_STATES env var.

FAIL-CLOSED by default: if the lookup fails (network error, rate limit,
non-200), the request is BLOCKED and logged for operator review. Set
GEOBLOCK_FAIL_CLOSED=false ONLY in dev/test environments.

Blocked-state list resolution:
  * BLOCKED_STATES set (even empty) → parsed as-is (operator override).
  * BLOCKED_STATES unset → SAFE_DEFAULT_BLOCKED_STATES below (attorney-
    reviewed production floor; matches render.yaml).

Localhost bypass applies ONLY outside production (APP_ENV != production),
so local dev keeps working while prod can never be bypassed.

Consult your gaming attorney before changing either default.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# Attorney-reviewed production floor. Keep in sync with render.yaml.
SAFE_DEFAULT_BLOCKED_STATES = frozenset(
    {"WA", "ID", "MT", "NV", "LA", "TN", "MI", "UT", "AZ"}
)


def _fail_closed() -> bool:
    return os.environ.get("GEOBLOCK_FAIL_CLOSED", "true").strip().lower() in (
        "1", "true", "yes",
    )


def _is_production() -> bool:
    return os.environ.get("APP_ENV", "development").strip().lower() in (
        "production", "prod",
    )


def _blocked_states() -> set[str]:
    raw = os.environ.get("BLOCKED_STATES")
    if raw is None:
        return set(SAFE_DEFAULT_BLOCKED_STATES)
    raw = raw.strip()
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
                logger.warning("Geoblock lookup HTTP %s for %s", r.status_code, ip)
                return None, None
            data = r.json()
            return (data.get("region_code") or "").upper() or None, (data.get("country_code") or "").upper() or None
    except Exception as e:
        logger.warning("Geoblock lookup failed for %s: %s", ip, e)
        return None, None


async def check_geoblock(ip: str) -> Tuple[bool, str, Optional[str]]:
    """Returns (is_blocked, reason, detected_state).

    FAIL-CLOSED (default): unknown state / lookup error ⇒ blocked=True.
    Every call site must treat blocked=True as "deny" and SHOULD record
    the event via record_geoblock_event for compliance review.
    """
    blocked = _blocked_states()
    clean_ip = (ip or "").split(",")[0].strip()

    # Localhost bypass is dev-only — never in production.
    if clean_ip in ("", "127.0.0.1", "::1", "localhost") and not _is_production():
        return False, "", None

    state, country = await _resolve_state(clean_ip)

    if country and country != "US":
        # Non-US — sweepstakes is a US legal construct. Block outright.
        return True, f"non-US ({country})", state
    if state and state in blocked:
        return True, f"state {state} is in BLOCKED_STATES", state
    if state is None:
        # Lookup failed or unresolvable.
        if _fail_closed():
            return True, "geolocation lookup failed (fail-closed)", None
        logger.warning("Geoblock fail-OPEN for %s (GEOBLOCK_FAIL_CLOSED=false)", clean_ip)
        return False, "", None
    return False, "", state


async def record_geoblock_event(db, *, user_id: Optional[str], ip: str, state: Optional[str], blocked: bool, context: str) -> None:
    await db["geoblock_events"].insert_one({
        "user_id": user_id,
        "ip": ip,
        "state": state,
        "blocked": blocked,
        "fail_closed": _fail_closed(),
        "context": context,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def client_ip_from_request(request) -> str:
    """Best-effort client IP extraction.

    Proxy headers are honored ONLY when TRUST_PROXY_HEADERS=true (production
    behind the Cloudflare Worker). Otherwise the peer address is used so a
    client cannot spoof its geolocation identity.
    """
    trust_proxy = os.environ.get("TRUST_PROXY_HEADERS", "false").strip().lower() in (
        "1", "true", "yes",
    )
    if trust_proxy:
        cf = request.headers.get("cf-connecting-ip") or request.headers.get("CF-Connecting-IP")
        if cf:
            return cf.split(",")[0].strip()
        fwd = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
        if fwd:
            return fwd.split(",")[0].strip()
        real = request.headers.get("x-real-ip") or request.headers.get("X-Real-IP")
        if real:
            return real.strip()
    return (request.client.host if request.client else "") or ""
