"""Admin + service router for the distributor proxy pool (Hybrid Buffer Strategy).

Endpoints
---------
POST   /api/ext/pool/admin/proxies          add a proxy (admin)
GET    /api/ext/pool/admin/proxies          list all proxies (admin)
PATCH  /api/ext/pool/admin/proxies/{id}     edit caps / status / creds (admin)
DELETE /api/ext/pool/admin/proxies/{id}     remove a proxy (admin)
POST   /api/ext/pool/admin/proxies/{id}/ping   live login check via bridge (admin)
POST   /api/ext/pool/admin/proxies/{id}/unlock reset lock + failures (admin)
GET    /api/ext/pool/admin/health           aggregate pool health (admin)
POST   /api/ext/pool/admin/transfer         manually trigger a P2P transfer (admin)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import proxy_pool
from services.hub_registry import HUB_CONFIGS, list_hubs
from services.proxy_pool import (
    clear_lock,
    create_proxy,
    delete_proxy,
    get_decrypted_credentials,
    list_proxies,
    mark_failed,
    mark_used,
    pool_health,
    select_proxy,
    update_proxy,
)

logger = logging.getLogger(__name__)


class ProxyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)
    base_url: Optional[str] = None
    hub_type: str = "sugar_sweeps"
    supported_platforms: Optional[list[str]] = None
    daily_cap: Optional[float] = None
    per_transfer_cap: Optional[float] = None


class ProxyUpdate(BaseModel):
    label: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    base_url: Optional[str] = None
    hub_type: Optional[str] = None
    supported_platforms: Optional[list[str]] = None
    daily_cap: Optional[float] = None
    per_transfer_cap: Optional[float] = None
    status: Optional[str] = None  # active | disabled (admin-reset; use /unlock for lock)


class TransferBody(BaseModel):
    recipient_username: str
    amount: float = Field(gt=0)
    platform: str = "fire_kirin"
    user_id: Optional[str] = None


async def execute_pool_transfer(
    db, recipient_username: str, amount: float, platform: str, proxy_id: Optional[str] = None, user_id: Optional[str] = None
):
    """Select a proxy, attempt a P2P transfer, record success/failure.

    If ``proxy_id`` is provided, that specific proxy is used (admin test flow);
    otherwise the pool is queried for the healthiest eligible proxy.

    Returns (ok, message, detail_dict).
    """
    if proxy_id:
        from bson import ObjectId as _OID
        doc = await db[proxy_pool.COLLECTION].find_one({"_id": _OID(proxy_id)})
        if not doc:
            return False, "Proxy not found", {"proxy_id": None}
        proxy = doc
    else:
        proxy, reason = await select_proxy(db, amount, platform=platform)
        if not proxy:
            return False, reason, {"proxy_id": None}

    proxy_oid = proxy["_id"]
    creds = await get_decrypted_credentials(db, str(proxy_oid))
    if not creds:
        return False, "Proxy credentials unavailable", {"proxy_id": str(proxy_oid)}

    bridge = None
    diagnostic: Dict[str, object] = {}
    try:
        from services.hub_bridge import make_bridge

        bridge = make_bridge(
            hub_type=proxy.get("hub_type") or "sugar_sweeps",
            username=creds["username"],
            password=creds["password"],
            base_url=creds["base_url"],
        )
        ok, msg, diagnostic = await bridge.transfer(
            recipient=recipient_username, amount=amount, platform=platform,
        )
    except ImportError as e:
        logger.warning("Playwright unavailable: %s", e)
        return False, "Bridge unavailable (Playwright not installed).", {
            "proxy_id": str(proxy_oid),
            "proxy_label": proxy.get("label"),
            "pending": True,
        }
    except Exception as e:
        logger.exception("Bridge transfer crashed")
        await mark_failed(db, proxy_oid, f"crash: {e}")
        return False, f"Bridge exception: {e}", {
            "proxy_id": str(proxy_oid),
            "proxy_label": proxy.get("label"),
        }
    finally:
        if bridge is not None:
            try:
                await bridge.close()
            except Exception:  # pragma: no cover — defensive only
                pass

    # Sanitize message if error contains internal paths to prevent info leak
    clean_msg = msg
    if not ok and ("/app/" in msg or "/root/" in msg or "executable not found" in msg.lower()):
        clean_msg = "Bridge transfer failed due to internal environment error. Check logs."

    if ok:
        await mark_used(db, proxy_oid, amount)
        
        # PLAYTHROUGH LOGIC: If we have a user_id, decrement their playthrough balance
        # as these credits are now "in play" on the platform.
        if user_id:
            try:
                from bson import ObjectId
                await db.users.update_one(
                    {"_id": ObjectId(user_id)},
                    [{"$set": {
                        "playthrough_balance": {
                            "$max": [0, {"$subtract": ["$playthrough_balance", amount]}]
                        }
                    }}]
                )
            except Exception as e:
                logger.warning(f"Failed to decrement playthrough balance for user {user_id}: {e}")

        return True, clean_msg, {
            "proxy_id": str(proxy_oid),
            "proxy_label": proxy.get("label"),
            "diagnostic": diagnostic,
        }

    await mark_failed(db, proxy_oid, msg) # Keep original message in DB for admin audit
    return False, clean_msg, {
        "proxy_id": str(proxy_oid),
        "proxy_label": proxy.get("label"),
        "diagnostic": diagnostic,
    }


def build_distributor_pool_router(db, get_admin_user) -> APIRouter:
    router = APIRouter(prefix="/api/ext/pool", tags=["distributor-pool"])

    @router.get("/admin/health")
    async def get_pool_health(request: Request):
        await get_admin_user(request)
        return await pool_health(db)

    @router.get("/admin/proxies")
    async def get_proxies(request: Request):
        await get_admin_user(request)
        return await list_proxies(db)

    @router.post("/admin/proxies")
    async def add_proxy(body: ProxyCreate, request: Request):
        await get_admin_user(request)
        if body.hub_type not in HUB_CONFIGS:
            raise HTTPException(400, f"Unknown hub_type '{body.hub_type}'. Valid: {list(HUB_CONFIGS.keys())}")
        hub = HUB_CONFIGS[body.hub_type]
        return await create_proxy(
            db,
            label=body.label,
            username=body.username,
            password=body.password,
            base_url=body.base_url or hub["base_url"],
            hub_type=body.hub_type,
            supported_platforms=body.supported_platforms,
            daily_cap=body.daily_cap,
            per_transfer_cap=body.per_transfer_cap,
        )

    @router.get("/admin/hubs")
    async def get_hubs(request: Request):
        """List all registered distributor hub types (for admin UI dropdown)."""
        await get_admin_user(request)
        return list_hubs()

    @router.patch("/admin/proxies/{proxy_id}")
    async def edit_proxy(proxy_id: str, body: ProxyUpdate, request: Request):
        await get_admin_user(request)
        patch = {k: v for k, v in body.dict().items() if v is not None}
        if "status" in patch and patch["status"] not in {"active", "disabled"}:
            raise HTTPException(400, "status must be 'active' or 'disabled' (use /unlock to clear locks)")
        result = await update_proxy(db, proxy_id, patch)
        if result is None:
            raise HTTPException(404, "Proxy not found or no valid fields to update")
        return result

    @router.delete("/admin/proxies/{proxy_id}")
    async def remove_proxy(proxy_id: str, request: Request):
        await get_admin_user(request)
        ok = await delete_proxy(db, proxy_id)
        if not ok:
            raise HTTPException(404, "Proxy not found")
        return {"deleted": True}

    @router.post("/admin/proxies/{proxy_id}/unlock")
    async def unlock_proxy(proxy_id: str, request: Request):
        await get_admin_user(request)
        ok = await clear_lock(db, proxy_id)
        if not ok:
            raise HTTPException(404, "Proxy not found")
        return {"unlocked": True}

    @router.post("/admin/proxies/{proxy_id}/ping")
    async def ping_proxy(proxy_id: str, request: Request):
        """Live login probe via GenericHubBridge. Returns rich diagnostic info."""
        await get_admin_user(request)
        from bson import ObjectId as _OID
        doc = await db[proxy_pool.COLLECTION].find_one({"_id": _OID(proxy_id)})
        if not doc:
            raise HTTPException(404, "Proxy not found")
        creds = await get_decrypted_credentials(db, proxy_id)
        try:
            from services.hub_bridge import make_bridge

            bridge = make_bridge(
                hub_type=doc.get("hub_type") or "sugar_sweeps",
                username=creds["username"],
                password=creds["password"],
                base_url=creds["base_url"],
            )
            try:
                ok, msg, diag = await bridge.ping()
            finally:
                try:
                    await bridge.close()
                except Exception:
                    pass
            
            # Sanitize for admin-facing diagnostic as well to avoid stack-hint leak
            clean_msg = msg
            if not ok:
                if "executable not found" in msg.lower() or "/app/" in msg or "/root/" in msg:
                    clean_msg = "Bridge driver missing (Playwright). Run install script."
            
            return {"ok": bool(ok), "message": clean_msg, "diagnostic": diag}
        except ImportError as e:
            return {"ok": False, "message": "Playwright dependency missing. Run pip install playwright.", "diagnostic": {}}
        except Exception as e:
            logger.exception("ping crashed")
            return {"ok": False, "message": "Internal error during ping. Check server logs.", "diagnostic": {}}

    @router.post("/admin/proxies/{proxy_id}/test-transfer")
    async def test_transfer(proxy_id: str, body: TransferBody, request: Request):
        """Trigger a P2P transfer *pinned* to a specific proxy (admin debug flow)."""
        await get_admin_user(request)
        ok, msg, detail = await execute_pool_transfer(
            db, body.recipient_username, body.amount, body.platform, proxy_id=proxy_id, user_id=body.user_id
        )
        return {"ok": ok, "message": msg, **detail}

    @router.get("/admin/routing-matrix")
    async def routing_matrix(request: Request):
        """For each game platform, list proxies that can serve it.

        Useful pre-launch check to spot coverage gaps.
        """
        await get_admin_user(request)
        proxies = await list_proxies(db)
        # Union of all platforms seen across hub registry + proxy overrides
        platform_set = set()
        for p in proxies:
            for pl in p.get("supported_platforms") or []:
                platform_set.add(pl)
        for hub in HUB_CONFIGS.values():
            for pl in hub.get("supported_platforms", []):
                platform_set.add(pl)

        matrix = []
        for pl in sorted(platform_set):
            serving = [
                {
                    "id": p["id"], "label": p["label"], "hub_type": p.get("hub_type"),
                    "status": p["status"],
                    "capacity_remaining": max(0.0, p["daily_cap"] - p["daily_volume_sent"]),
                }
                for p in proxies
                if (not p.get("supported_platforms")) or pl in (p.get("supported_platforms") or [])
            ]
            active = [s for s in serving if s["status"] == "active"]
            matrix.append({
                "platform": pl,
                "total_coverage": len(serving),
                "active_coverage": len(active),
                "proxies": serving,
            })
        return matrix

    @router.get("/admin/launch-readiness")
    async def launch_readiness(request: Request):
        """Pre-launch operational readiness dashboard.

        Runs 4 checks. Each returns ok|warn|fail + human-readable detail.
        The UI reads this to show a green "READY FOR LIVE TRAFFIC" banner
        or a red fix-list.
        """
        import os as _os
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td

        await get_admin_user(request)
        proxies = await list_proxies(db)

        # 1) Every game has >= 2 active proxies (inline routing-matrix compute)
        platform_set = set()
        for p in proxies:
            for pl in p.get("supported_platforms") or []:
                platform_set.add(pl)
        for hub in HUB_CONFIGS.values():
            for pl in hub.get("supported_platforms", []):
                platform_set.add(pl)
        gaps = []
        for pl in sorted(platform_set):
            active_cov = sum(
                1 for p in proxies
                if p.get("status") == "active"
                and ((not p.get("supported_platforms")) or pl in (p.get("supported_platforms") or []))
            )
            if active_cov < 2:
                gaps.append(pl)
        check_coverage = {
            "name": "Game coverage redundancy",
            "ok": len(gaps) == 0,
            "detail": "All games have ≥2 active proxies." if not gaps
                      else f"Games with <2 active proxies: {', '.join(gaps)} — add another hub or deposits will stall if one proxy fails.",
        }

        # 2) All proxies pinged green in last 24h  (we use last_used_at as proxy;
        #    if never used, it's a fail). Admins should run "Ping all" to refresh.
        now = _dt.now(_tz.utc)
        stale = []
        for p in proxies:
            last = p.get("last_used_at")
            if not last:
                stale.append(p["label"])
                continue
            try:
                t = _dt.fromisoformat(last)
                if (now - t) > _td(hours=24):
                    stale.append(p["label"])
            except Exception:
                stale.append(p["label"])
        check_freshness = {
            "name": "Proxy health freshness",
            "ok": len(stale) == 0 and len(proxies) > 0,
            "detail": "All proxies used within the last 24h." if len(stale) == 0 and len(proxies) > 0
                      else ("No proxies configured." if len(proxies) == 0
                            else f"Stale / never-used proxies: {', '.join(stale)} — click 'Ping all' to verify they still log in."),
        }

        # 3) No proxy > 80% of daily cap
        hot = [p["label"] for p in proxies
               if p["daily_cap"] > 0 and (p["daily_volume_sent"] / p["daily_cap"]) > 0.8]
        check_capacity = {
            "name": "Per-proxy daily capacity",
            "ok": len(hot) == 0,
            "detail": "No proxy is above 80% of its daily cap." if not hot
                      else f"Proxies near cap: {', '.join(hot)} — raise cap or add another proxy before peak hours.",
        }

        # 4) Stripe key is not the placeholder
        stripe_key = _os.environ.get("STRIPE_API_KEY", "")
        stripe_real = bool(stripe_key) and "placeholder" not in stripe_key.lower()
        check_stripe = {
            "name": "Stripe API key",
            "ok": stripe_real,
            "detail": "Stripe key looks real." if stripe_real
                      else "STRIPE_API_KEY is a placeholder — deposits will 500 at Stripe. Replace in backend/.env.",
        }

        checks = [check_coverage, check_freshness, check_capacity, check_stripe]
        all_ok = all(c["ok"] for c in checks)
        return {
            "ready": all_ok,
            "checks": checks,
            "summary": "READY FOR LIVE TRAFFIC" if all_ok
                       else f"{sum(1 for c in checks if not c['ok'])} issue(s) to fix before launch.",
        }

    @router.post("/admin/ping-all")
    async def ping_all(request: Request):
        """Ping every proxy in parallel. Returns a summary + per-proxy result.

        This also updates `last_used_at` on success, feeding the launch-readiness
        freshness check.
        """
        await get_admin_user(request)
        proxies = await list_proxies(db)

        async def _ping_one(p):
            creds = await get_decrypted_credentials(db, p["id"])
            try:
                from services.hub_bridge import make_bridge

                bridge = make_bridge(
                    hub_type=p.get("hub_type") or "sugar_sweeps",
                    username=creds["username"],
                    password=creds["password"],
                    base_url=creds["base_url"],
                )
                try:
                    ok, msg, _diag = await bridge.ping()
                finally:
                    try:
                        await bridge.close()
                    except Exception:
                        pass
                if ok:
                    from bson import ObjectId as _OID
                    await mark_used(db, _OID(p["id"]), 0)  # touch last_used_at without incrementing volume
                return {"id": p["id"], "label": p["label"], "hub_type": p.get("hub_type"), "ok": ok, "message": msg}
            except Exception as e:
                return {"id": p["id"], "label": p["label"], "hub_type": p.get("hub_type"), "ok": False, "message": f"{type(e).__name__}: {e}"}

        if not proxies:
            return {"total": 0, "passed": 0, "failed": 0, "results": []}

        # Sequential with delays — anti-bot pages (Vercel/Cloudflare) penalize
        # parallel hits from the same egress IP. Sequential is slower but reliable.
        results = []
        for p in proxies:
            results.append(await _ping_one(p))
            await asyncio.sleep(2)  # cool-down between proxies
        passed = sum(1 for r in results if r["ok"])
        return {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "results": results,
        }

    @router.post("/admin/transfer")
    async def manual_transfer(body: TransferBody, request: Request):
        """Admin-initiated manual P2P transfer (routes via round-robin pool)."""
        await get_admin_user(request)
        ok, msg, detail = await execute_pool_transfer(
            db, body.recipient_username, body.amount, body.platform, user_id=body.user_id
        )
        return {"ok": ok, "message": msg, **detail}

    # Expose helpers on module for other routers (e.g. server.py webhook).
    proxy_pool.execute_pool_transfer = execute_pool_transfer  # type: ignore[attr-defined]
    return router
