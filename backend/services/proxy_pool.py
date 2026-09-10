"""Distributor Proxy Pool Service — Hybrid Buffer Strategy.

Rotation pool of Sugar Sweeps distributor accounts. Provides round-robin
selection with health filtering, safety caps, auto-cooldown, and failover.

One collection: `distributor_proxies`.
Document shape:
    {
        _id, label, username, password_enc, base_url,
        status: "active" | "cooldown" | "locked" | "disabled",
        pull_supported: bool,           # pull (player->seat) capable; defaults to hub config
        balance_cached: float,
        daily_volume_sent: float,
        daily_cap: float,
        per_transfer_cap: float,
        daily_reset_at: iso,
        last_used_at: iso | None,
        consecutive_failures: int,
        cooldown_until: iso | None,
        lock_reason: str | None,
        created_at: iso,
    }
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId

from services.crypto_vault import decrypt, encrypt
from services.hub_registry import get_hub

logger = logging.getLogger(__name__)

COLLECTION = "distributor_proxies"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _cfg_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _cfg_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def hub_pull_supported(proxy: Dict[str, Any]) -> bool:
    """Whether a proxy can pull credits back to its seat.

    Per-proxy ``pull_supported`` overrides the hub registry default so an
    operator can opt a single seat in (or out) without touching all proxies on
    the same hub. Falls back to the hub capability when the proxy has no flag.
    """
    if "pull_supported" in proxy and proxy.get("pull_supported") is not None:
        return bool(proxy.get("pull_supported"))
    hub = get_hub(proxy.get("hub_type") or "sugar_sweeps")
    return bool(hub.get("pull_supported", False))


def public_view(proxy: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a proxy doc for JSON response, redacting the password."""
    return {
        "id": str(proxy["_id"]),
        "label": proxy.get("label"),
        "username": proxy.get("username"),
        "base_url": proxy.get("base_url"),
        "hub_type": proxy.get("hub_type", "sugar_sweeps"),
        "supported_platforms": proxy.get("supported_platforms", []),
        "pull_supported": hub_pull_supported(proxy),
        "status": proxy.get("status", "active"),
        "balance_cached": proxy.get("balance_cached", 0.0),
        "daily_volume_sent": proxy.get("daily_volume_sent", 0.0),
        "daily_cap": proxy.get("daily_cap", 0.0),
        "per_transfer_cap": proxy.get("per_transfer_cap", 0.0),
        "daily_reset_at": proxy.get("daily_reset_at"),
        "last_used_at": proxy.get("last_used_at"),
        "consecutive_failures": proxy.get("consecutive_failures", 0),
        "cooldown_until": proxy.get("cooldown_until"),
        "lock_reason": proxy.get("lock_reason"),
        "created_at": proxy.get("created_at"),
    }


async def create_proxy(
    db,
    *,
    label: str,
    username: str,
    password: str,
    base_url: str,
    hub_type: str = "sugar_sweeps",
    supported_platforms: Optional[List[str]] = None,
    pull_supported: Optional[bool] = None,
    daily_cap: Optional[float] = None,
    per_transfer_cap: Optional[float] = None,
) -> Dict[str, Any]:
    per_tx = (
        per_transfer_cap
        if per_transfer_cap is not None
        else _cfg_float("PROXY_DEFAULT_PER_TRANSFER_CAP", 500.0)
    )
    daily = (
        daily_cap
        if daily_cap is not None
        else _cfg_float("PROXY_DEFAULT_DAILY_CAP", 5000.0)
    )
    hub = get_hub(hub_type)
    # Default supported platforms come from the hub registry unless caller overrides.
    platforms = (
        supported_platforms
        if supported_platforms is not None
        else list(hub.get("supported_platforms", []))
    )
    pull_ok = (
        pull_supported
        if pull_supported is not None
        else bool(hub.get("pull_supported", False))
    )
    doc = {
        "label": label,
        "username": username,
        "password_enc": encrypt(password),
        "base_url": base_url or hub["base_url"],
        "hub_type": hub_type,
        "supported_platforms": platforms,
        "pull_supported": pull_ok,
        "status": "active",
        "balance_cached": 0.0,
        "daily_volume_sent": 0.0,
        "daily_cap": daily,
        "per_transfer_cap": per_tx,
        "daily_reset_at": _iso(_now()),
        "last_used_at": None,
        "consecutive_failures": 0,
        "cooldown_until": None,
        "lock_reason": None,
        "created_at": _iso(_now()),
    }
    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return public_view(doc)


async def update_proxy(db, proxy_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = {"label", "base_url", "daily_cap", "per_transfer_cap", "status", "hub_type", "supported_platforms", "pull_supported"}
    updates = {k: v for k, v in patch.items() if k in allowed}
    if "password" in patch and patch["password"]:
        updates["password_enc"] = encrypt(patch["password"])
    if "username" in patch and patch["username"]:
        updates["username"] = patch["username"]
    if not updates:
        return None
    await db[COLLECTION].update_one({"_id": ObjectId(proxy_id)}, {"$set": updates})
    doc = await db[COLLECTION].find_one({"_id": ObjectId(proxy_id)})
    return public_view(doc) if doc else None


async def delete_proxy(db, proxy_id: str) -> bool:
    r = await db[COLLECTION].delete_one({"_id": ObjectId(proxy_id)})
    return r.deleted_count > 0


async def list_proxies(db) -> List[Dict[str, Any]]:
    await _reset_daily_if_needed(db)
    await _clear_expired_cooldowns(db)
    items = await db[COLLECTION].find({}).sort("created_at", 1).to_list(500)
    return [public_view(p) for p in items]


async def get_decrypted_credentials(db, proxy_id: str) -> Optional[Dict[str, str]]:
    """Return {username, password, base_url} for bridge use. Internal only."""
    doc = await db[COLLECTION].find_one({"_id": ObjectId(proxy_id)})
    if not doc:
        return None
    return {
        "username": doc.get("username", ""),
        "password": decrypt(doc.get("password_enc", "")),
        "base_url": doc.get("base_url") or "https://sugarsweeps.com",
    }


# =========================================================
# Health filter + selection
# =========================================================
async def _reset_daily_if_needed(db) -> None:
    """Reset daily_volume_sent for any proxy whose daily_reset_at is > 24h old."""
    threshold = _now() - timedelta(hours=24)
    cursor = db[COLLECTION].find({})
    async for p in cursor:
        reset_at = _parse_iso(p.get("daily_reset_at"))
        if reset_at is None or reset_at < threshold:
            await db[COLLECTION].update_one(
                {"_id": p["_id"]},
                {"$set": {"daily_volume_sent": 0.0, "daily_reset_at": _iso(_now())}},
            )


async def _clear_expired_cooldowns(db) -> None:
    now = _now()
    cursor = db[COLLECTION].find({"status": "cooldown"})
    async for p in cursor:
        until = _parse_iso(p.get("cooldown_until"))
        if until and until <= now:
            await db[COLLECTION].update_one(
                {"_id": p["_id"]},
                {"$set": {"status": "active", "cooldown_until": None, "consecutive_failures": 0}},
            )


async def select_proxy(
    db, amount: float, platform: Optional[str] = None, require_pull: bool = False
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Round-robin selection with health filter.

    When ``platform`` is provided, only proxies whose ``supported_platforms``
    list contains it are considered (empty list = supports all).

    When ``require_pull`` is set, only proxies capable of pulling credits back
    to their seat (per-proxy ``pull_supported`` or hub default) are eligible —
    used by the credit-loop / pool_pull path.

    Returns (proxy_doc, reason). When no eligible proxy: (None, reason).
    """
    if amount <= 0:
        return None, "Invalid amount"

    await _reset_daily_if_needed(db)
    await _clear_expired_cooldowns(db)

    candidates: List[Dict[str, Any]] = []
    async for p in db[COLLECTION].find({"status": "active"}):
        per_tx = float(p.get("per_transfer_cap", 0) or 0)
        daily_cap = float(p.get("daily_cap", 0) or 0)
        sent = float(p.get("daily_volume_sent", 0) or 0)
        if per_tx and amount > per_tx:
            continue
        if daily_cap and sent + amount > daily_cap:
            continue
        supported = p.get("supported_platforms") or []
        if platform and supported and platform not in supported:
            continue
        if require_pull and not hub_pull_supported(p):
            continue
        candidates.append(p)

    if not candidates:
        # Diagnostic: figure out why
        total = await db[COLLECTION].count_documents({})
        if total == 0:
            return None, "No proxies configured. Add one in admin → Distributor Pool."
        active = await db[COLLECTION].count_documents({"status": "active"})
        if active == 0:
            return None, "All proxies are in cooldown, locked, or disabled."
        if require_pull:
            pull_ok = await db[COLLECTION].count_documents({"status": "active", "pull_supported": True})
            if pull_ok == 0:
                return None, (
                    "No active proxy supports pull for this platform yet — "
                    "set pull_supported on a hub/proxy or accept wholesale fallback."
                )
        if platform:
            supporting = await db[COLLECTION].count_documents({
                "status": "active",
                "$or": [
                    {"supported_platforms": platform},
                    {"supported_platforms": {"$size": 0}},
                    {"supported_platforms": {"$exists": False}},
                ],
            })
            if supporting == 0:
                return None, f"No active proxy supports platform '{platform}'. Add a hub that covers it."
        return None, (
            f"All {active} active proxies are over their per-transfer or daily cap "
            f"for amount ${amount:.2f}."
        )

    # Round-robin: earliest last_used_at wins; None < any timestamp.
    def _sort_key(p):
        return _parse_iso(p.get("last_used_at")) or datetime.min.replace(tzinfo=timezone.utc)

    candidates.sort(key=_sort_key)
    return candidates[0], "selected"


async def mark_used(db, proxy_id: ObjectId, amount: float) -> None:
    await db[COLLECTION].update_one(
        {"_id": proxy_id},
        {
            "$set": {"last_used_at": _iso(_now()), "consecutive_failures": 0},
            "$inc": {"daily_volume_sent": amount},
        },
    )


async def mark_failed(db, proxy_id: ObjectId, reason: str) -> Dict[str, Any]:
    """Increment failure counter; cooldown or lock when thresholds are hit."""
    cooldown_at = _cfg_int("PROXY_COOLDOWN_FAILURES", 3)
    lock_at = _cfg_int("PROXY_LOCK_FAILURES", 5)
    cooldown_mins = _cfg_int("PROXY_COOLDOWN_MINUTES", 30)

    doc = await db[COLLECTION].find_one_and_update(
        {"_id": proxy_id},
        {"$inc": {"consecutive_failures": 1}},
        return_document=True,
    )
    if not doc:
        return {"updated": False}
    # Motor returns the *pre*-update doc unless we tell it otherwise; fetch fresh.
    doc = await db[COLLECTION].find_one({"_id": proxy_id})
    failures = int(doc.get("consecutive_failures", 0))

    outcome = {"updated": True, "failures": failures, "status": doc.get("status")}
    if failures >= lock_at:
        await db[COLLECTION].update_one(
            {"_id": proxy_id},
            {"$set": {"status": "locked", "lock_reason": reason, "cooldown_until": None}},
        )
        outcome["status"] = "locked"
    elif failures >= cooldown_at:
        until = _now() + timedelta(minutes=cooldown_mins)
        await db[COLLECTION].update_one(
            {"_id": proxy_id},
            {"$set": {"status": "cooldown", "cooldown_until": _iso(until)}},
        )
        outcome["status"] = "cooldown"
        outcome["cooldown_until"] = _iso(until)
    return outcome


async def clear_lock(db, proxy_id: str) -> bool:
    r = await db[COLLECTION].update_one(
        {"_id": ObjectId(proxy_id)},
        {
            "$set": {
                "status": "active",
                "consecutive_failures": 0,
                "lock_reason": None,
                "cooldown_until": None,
            }
        },
    )
    return r.matched_count > 0


async def enforce_balance_floor(db) -> List[str]:
    """Auto-disable active seats whose *known* balance is below the floor.

    ``balance_cached == 0`` (or missing) means "unknown" — the nightly resync
    hasn't observed it yet — and is left alone. The rule only fires once a real
    balance was measured below the floor (playbook: credit rebalancer rule b).
    Returns the proxy ids disabled.
    """
    floor = _cfg_float("PROXY_BALANCE_FLOOR", 50.0)
    disabled: List[str] = []
    cursor = db[COLLECTION].find({"status": "active"})
    async for p in cursor:
        bal = float(p.get("balance_cached") or 0)
        if bal > 0 and bal < floor:
            await db[COLLECTION].update_one(
                {"_id": p["_id"]},
                {"$set": {
                    "status": "disabled",
                    "lock_reason": f"balance ${bal:.2f} below floor ${floor:.2f}",
                }},
            )
            disabled.append(str(p["_id"]))
    return disabled


async def maybe_emit_capacity_alert(db, health: Dict[str, Any]) -> Dict[str, Any]:
    """Raise one admin alert per day when aggregate capacity is nearly done.

    Fires when active seats exist, aggregate daily capacity is configured, and
    ``daily_capacity_remaining_pct`` has dropped below 20% (playbook rule c).
    """
    pct = float(health.get("daily_capacity_remaining_pct") or 0)
    if (
        health.get("active", 0) <= 0
        or float(health.get("daily_capacity_total") or 0) <= 0
        or pct >= 20.0
    ):
        return {"alerted": False, "reason": "above_threshold"}
    today = datetime.now(timezone.utc).date().isoformat()
    existing = await db["admin_alerts"].find_one({"type": "pool_capacity", "created_date": today})
    if existing:
        return {"alerted": False, "reason": "already_open_today"}
    doc = {
        "type": "pool_capacity",
        "severity": "high",
        "message": (
            f"Aggregate daily pool capacity {pct:.1f}% remaining — add seats "
            "or raise daily_cap before seats lock."
        ),
        "daily_capacity_remaining_pct": round(pct, 2),
        "status": "open",
        "created_at": _iso(_now()),
        "created_date": today,
    }
    await db["admin_alerts"].insert_one(doc)
    logger.warning("Admin alert created: %s", doc["message"])
    return {"alerted": True, "reason": "threshold_crossed"}


def _rebalance_enabled() -> bool:
    val = os.environ.get("POOL_REBALANCE_ENABLED", "false").strip().lower()
    return val in ("1", "true", "yes", "on")


async def sweep_credits_to_lowest(db, dry_run: bool = True) -> Dict[str, Any]:
    """Rule (a): sweep surplus seat balance into the seat with the lowest balance.

    Within each hub family, active seats with a *known* balance
    (``balance_cached > 0``) are compared. When a seat holds more than the
    lowest-balance seat plus ``PROXY_SWEEP_MARGIN``, the excess (capped at
    ``per_transfer_cap``) is moved to the neediest seat via the same bridge
    transfer the funding path uses — i.e. recycled credits are re-allocated so
    no seat dries up while another is over-provisioned.

    ``dry_run=True`` (default) only returns the plan; no credits move. Real
    sweeps additionally require ``POOL_REBALANCE_ENABLED=true``. Every attempt
    is appended to the ``pool_sweeps`` audit collection.
    """
    enabled = _rebalance_enabled()
    margin = _cfg_float("PROXY_SWEEP_MARGIN", 25.0)
    plan: List[Dict[str, Any]] = []
    executed: List[Dict[str, Any]] = []
    skipped: List[str] = []

    proxies = await list_proxies(db)
    active = [p for p in proxies if p["status"] == "active" and float(p.get("balance_cached") or 0) > 0]
    by_hub: Dict[str, List[Dict[str, Any]]] = {}
    for p in active:
        by_hub.setdefault(p.get("hub_type") or "sugar_sweeps", []).append(p)

    for hub_type, seats in by_hub.items():
        seats = sorted(seats, key=lambda p: float(p.get("balance_cached") or 0))
        target = seats[0]
        t_bal = float(target.get("balance_cached") or 0)
        if len(seats) < 2:
            skipped.append(f"{hub_type}: only one known seat")
            continue
        for source in seats[1:]:
            s_bal = float(source.get("balance_cached") or 0)
            excess = s_bal - t_bal - margin
            if excess < 1.0:
                skipped.append(f"{source.get('label')}: no surplus")
                continue
            per_tx = float(source.get("per_transfer_cap") or 0)
            amount = round(min(excess, per_tx if per_tx else excess), 2)
            platform = (source.get("supported_platforms") or target.get("supported_platforms") or [""])[0]
            rec = {
                "hub_type": hub_type,
                "source_id": source["id"],
                "source_label": source.get("label"),
                "source_balance": round(s_bal, 2),
                "target_id": target["id"],
                "target_label": target.get("label"),
                "target_balance": round(t_bal, 2),
                "amount": amount,
                "platform": platform if platform else None,
            }
            plan.append(rec)
            if dry_run or not enabled:
                continue
            try:
                creds = await get_decrypted_credentials(db, str(source["id"]))
                if not creds:
                    raise RuntimeError("source credentials unavailable")
                from services.hub_bridge import make_bridge

                bridge = make_bridge(
                    hub_type=hub_type,
                    username=creds["username"],
                    password=creds["password"],
                    base_url=creds["base_url"],
                )
                try:
                    ok, msg, diag = await bridge.transfer(
                        recipient=target.get("username") or target.get("label"),
                        amount=amount,
                        platform=platform if platform else None,
                    )
                finally:
                    try:
                        await bridge.close()
                    except Exception:  # pragma: no cover — defensive only
                        pass
            except Exception as e:
                logger.exception("Rebalance sweep crashed")
                ok, msg, diag = False, f"sweep crash: {e}", {}
            out = {**rec, "ok": ok, "message": msg, "diagnostic": diag, "ran_at": _iso(_now())}
            executed.append(out)
            if ok:
                await db[COLLECTION].update_one(
                    {"_id": ObjectId(rec["source_id"])},
                    {"$inc": {"balance_cached": -amount}},
                )
                await db[COLLECTION].update_one(
                    {"_id": ObjectId(rec["target_id"])},
                    {"$inc": {"balance_cached": amount}},
                )
            # Always leave an audit trail, successes and failures alike.
            await db["pool_sweeps"].insert_one({"type": "rebalance", **out})

    return {
        "enabled": enabled,
        "dry_run": dry_run,
        "sweep_margin": margin,
        "planned": plan,
        "executed": [e for e in executed if e["ok"]],
        "failed": [e for e in executed if not e["ok"]],
        "skipped": skipped,
    }


async def run_rebalance(db, dry_run: bool = True) -> Dict[str, Any]:
    """Credit rebalancer cron entrypoint — all three playbook rules.

    1. (b) ``enforce_balance_floor``   — auto-disable beds below floor.
    2. (c) ``maybe_emit_capacity_alert`` — one alert/day under 20% capacity.
    3. (a) ``sweep_credits_to_lowest``  — move surplus seats into the neediest.

    ``dry_run`` defaults to true so a scheduler misconfiguration can never move
    credits; real sweeps require ``dry_run=false`` AND ``POOL_REBALANCE_ENABLED``.
    """
    floor = await enforce_balance_floor(db)
    health = await pool_health(db)
    alert = await maybe_emit_capacity_alert(db, health)
    sweep = await sweep_credits_to_lowest(db, dry_run=dry_run)
    return {
        "ok": True,
        "dry_run": dry_run,
        "balance_floor": health["balance_floor"],
        "disabled_below_floor_ids": floor,
        "capacity_alert": alert,
        "sweep": sweep,
        "health": health,
    }


async def pool_health(db) -> Dict[str, Any]:
    disabled_ids = await enforce_balance_floor(db)
    proxies = await list_proxies(db)
    active = [p for p in proxies if p["status"] == "active"]
    cap_total = sum(float(p["daily_cap"] or 0) for p in active)
    remaining = sum(
        max(0.0, float(p["daily_cap"] or 0) - float(p["daily_volume_sent"] or 0))
        for p in active
    )
    floor = _cfg_float("PROXY_BALANCE_FLOOR", 50.0)
    below = [
        p for p in active
        if float(p.get("balance_cached") or 0) > 0
        and float(p.get("balance_cached") or 0) < floor
    ]
    return {
        "total": len(proxies),
        "active": len(active),
        "cooldown": sum(1 for p in proxies if p["status"] == "cooldown"),
        "locked": sum(1 for p in proxies if p["status"] == "locked"),
        "disabled": sum(1 for p in proxies if p["status"] == "disabled"),
        "daily_capacity_total": round(cap_total, 2),
        "daily_capacity_remaining": round(remaining, 2),
        "daily_capacity_remaining_pct": round(remaining / cap_total * 100.0, 2) if cap_total else 0.0,
        "active_below_floor": len(below),
        "balance_floor": floor,
        "disabled_below_floor_ids": disabled_ids,
    }
