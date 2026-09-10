"""Pool balance resync worker — keeps distributor seat balances truthful.

The credit loop's ground truth is ``distributor_proxies.balance_cached``, which
starts at ``0.0`` and the pool treats ``0.0`` as "unknown" until a real balance
was observed. Balances only drift via transfers and sweeps, so without a
periodic read the rebalancer's rules have nothing to work on:

* rule (b) ``enforce_balance_floor``  — auto-disable seats below the floor
* rule (a) ``sweep_credits_to_lowest`` — move surplus into the neediest seat
* rule (c) ``maybe_emit_capacity_alert`` — raise one alert/day near exhaustion

This loop closes that gap: on a configured interval it logs each active/cooldown
seat in via its hub bridge, reads the live balance, and stamps ``balance_cached``
plus ``resynced_at``. After the pass it hands the *fresh* picture to the credit
rebalancer.

Design rules
------------
* Best-effort, never raises: a seat whose hub has no balance endpoint yet (all
  hubs today — see ``hub_registry`` / ``api_paths.balance`` / the ``balance``
  selector) is recorded as ``unsupported`` and its cached balance is left
  untouched, so ``0.0`` stays "unknown" and the floor rule cannot mis-disable
  it. Nothing is clobbered on a failed or unsupported read.
* Failures are attributed: a seat that cannot be *read* (network, login, bad
  selectors) advances through the same ``mark_failed`` cooldown/lock path a
  transfer failure would follow. A successful read clears failures, cooldown,
  and re-activates the seat.
* Auditable: one row per seat per pass plus one summary row are written to the
  ``pool_resyncs`` collection (admin endpoint + history exposed on the router).
* The post-pass rebalancer always runs ``dry_run=True`` — it enforces the floor,
  may emit the capacity alert, and only *plans* sweeps. Real sweeps require an
  explicit ``dry_run=false`` call AND ``POOL_REBALANCE_ENABLED=true``.

Knobs (env):
  POOL_RESYNC_ENABLED          default "true"   — run the loop at all
  POOL_RESYNC_INTERVAL_MIN     default "1440"   — minutes between passes (24h)
  POOL_RESYNC_RUN_REBALANCE    default "true"   — safe dry-run rebalance after pass
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.hub_bridge import make_bridge
from services.proxy_pool import (
    COLLECTION,
    get_decrypted_credentials,
    mark_failed,
    run_rebalance,
)

logger = logging.getLogger(__name__)

RESYNC_COLLECTION = "pool_resyncs"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cfg_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _cfg_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _balance_supported(diag: Dict[str, Any]) -> bool:
    """Whether the hub actually declared a way to read a balance."""
    return bool(diag.get("balance_supported"))


def _fail_msg(value: Any, diag: Dict[str, Any]) -> str:
    """Human-readable reason for a failed balance read, from the bridge diag."""
    if value is not None:
        return str(value)
    steps = diag.get("steps", [])
    if steps:
        last = steps[-1]
        name = last.get("step", "")
        detail = (
            last.get("error")
            or last.get("detail")
            or last.get("body_preview")
            or ""
        )
        if detail:
            return f"{name}: {str(detail)[:160]}"
        if name:
            return name
    return "balance read failed"


async def _read_one(db, proxy: Dict[str, Any]) -> Dict[str, Any]:
    """Read one seat's live balance through its hub bridge. Never raises.

    Returns a result dict with ``status`` of ``done`` | ``failed`` |
    ``unsupported`` and (on success) the numeric ``balance``.
    """
    pid = proxy["_id"]
    label = proxy.get("label")
    hub_type = proxy.get("hub_type") or "sugar_sweeps"
    base = {
        "proxy_id": str(pid),
        "label": label,
        "hub_type": hub_type,
        "status": "failed",
        "message": "",
        "balance": None,
    }

    try:
        creds = await get_decrypted_credentials(db, str(pid))
        if not creds:
            return {**base, "message": "credentials unavailable"}
        bridge = make_bridge(
            hub_type=hub_type,
            username=creds["username"],
            password=creds["password"],
            base_url=creds["base_url"],
        )
        try:
            ok, value, diag = await bridge.get_balance()
        finally:
            try:
                await bridge.close()
            except Exception:  # pragma: no cover — defensive only
                pass
    except Exception as e:  # noqa: BLE001 — a read must never kill the pass
        return {**base, "message": f"read crash: {e}"}

    if not ok:
        if not _balance_supported(diag):
            # Hub has no balance read configured — informational, not a failure.
            return {
                **base,
                "status": "unsupported",
                "message": "hub has no balance endpoint/selector configured",
            }
        reason = _fail_msg(value, diag)
        try:
            await mark_failed(db, pid, f"balance read failed: {reason}")
        except Exception:  # noqa: BLE001
            logger.exception("mark_failed crashed for %s", pid)
        return {**base, "message": reason}

    try:
        balance = round(float(value), 2)
    except (TypeError, ValueError):
        try:
            await mark_failed(db, pid, f"non-numeric balance {value!r}")
        except Exception:  # noqa: BLE001
            logger.exception("mark_failed crashed for %s", pid)
        return {**base, "message": f"non-numeric balance {value!r}"}

    await db[COLLECTION].update_one(
        {"_id": pid},
        {"$set": {
            "balance_cached": balance,
            "resynced_at": _now().isoformat(),
            "consecutive_failures": 0,
            "status": "active",
            "cooldown_until": None,
        }},
    )
    return {**base, "status": "done", "balance": balance, "message": "balance refreshed"}


async def resync_seat_balances(db) -> Dict[str, Any]:
    """Refresh every active/cooldown seat's cached balance from its hub.

    One best-effort read per seat, a dry-run rebalance on the fresh picture,
    and a summary row in ``pool_resyncs``. Returns the pass summary; callers
    (scheduler, admin endpoint, watchdog) use it for reports.
    """
    proxies = await db[COLLECTION].find(
        {"status": {"$in": ["active", "cooldown"]}}
    ).to_list(1000)

    results: list[Dict[str, Any]] = []
    done = failed = unsupported = 0
    total_balance = 0.0
    for proxy in proxies:
        r = await _read_one(db, proxy)
        results.append(r)
        if r["status"] == "done":
            done += 1
            total_balance += float(r["balance"] or 0)
        elif r["status"] == "failed":
            failed += 1
        else:
            unsupported += 1

    rebalance: Optional[Dict[str, Any]] = None
    if _cfg_bool("POOL_RESYNC_RUN_REBALANCE", True):
        try:
            rebalance = await run_rebalance(db, dry_run=True)
        except Exception as e:  # noqa: BLE001
            logger.exception("Post-resync dry-run rebalance crashed")
            rebalance = {"ok": False, "dry_run": True, "error": str(e)}

    summary = {
        "started_at": _now().isoformat(),
        "seats": len(proxies),
        "read": done,
        "failed": failed,
        "unsupported": unsupported,
        "cached_balance_total": round(total_balance, 2),
        "results": results,
        "rebalance_dry_run": rebalance,
    }
    try:
        await db[RESYNC_COLLECTION].insert_one(dict(summary))
    except Exception:  # noqa: BLE001 — audit write must never break the pass
        logger.exception("Failed to audit pool resync pass")
    return summary


class PoolResyncWorker:
    """Long-lived background task that refreshes seat balances, restart-safe."""

    def __init__(self, db):
        self.db = db
        self.last_report: Optional[dict] = None
        self._task: Optional[asyncio.Task] = None
        self.enabled = _cfg_bool("POOL_RESYNC_ENABLED", True)
        # Never faster than once an hour no matter what the env says.
        self._interval = max(3600, _cfg_int("POOL_RESYNC_INTERVAL_MIN", 1440) * 60)

    def start(self) -> None:
        if not self.enabled:
            logger.info("Pool resync disabled (POOL_RESYNC_ENABLED=false).")
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        logger.info(
            "Pool resync worker started (every %ss, refreshing seat balances).",
            self._interval,
        )
        while True:
            try:
                report = await resync_seat_balances(self.db)
                self.last_report = report
                if report["seats"]:
                    logger.info(
                        "Pool resync pass: %d seats (%d read, %d failed, %d unsupported), "
                        "cached balance $%.2f",
                        report["seats"], report["read"], report["failed"],
                        report["unsupported"], report["cached_balance_total"],
                    )
                else:
                    logger.info("Pool resync pass: no distributor seats configured.")
            except Exception:  # noqa: BLE001 — worker must never die
                logger.exception("Pool resync pass crashed")
            await asyncio.sleep(self._interval)