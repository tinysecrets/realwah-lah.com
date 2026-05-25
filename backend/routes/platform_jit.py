"""
Just-In-Time (JIT) platform registration framework.

Purpose
-------
When a player clicks "Deposit" on a specific game, the system ensures the player
is registered on that platform using their MASTER credentials. If registration
fails, the deposit is paused and an admin alert is emitted.

Design
------
- Master credentials (game_username / game_password) are stored on the user doc.
- Per-platform state lives in `users.platform_accounts[game_id]`:
    {status: "registered" | "failed" | "pending", platform_uid: str, registered_at, error}
- Each game platform has an adapter. The default adapter is a stub that records the
  master credentials as the platform UID (dry-run). Real adapters are plug-ins that
  must implement `async def register(username, password, context) -> (bool, platform_uid|err)`.
- Alerts live in `admin_alerts` collection.

No external network calls are attempted in the default adapter.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from bson import ObjectId

logger = logging.getLogger(__name__)


# =========================================================
# Adapters
# =========================================================
class PlatformAdapter:
    """Base adapter. Subclass per game platform to integrate real APIs / automation."""

    platform_id: str = "default"
    label: str = "Default"

    async def register(
        self, username: str, password: str, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Return (success, platform_uid_or_error).

        The default implementation is a DRY-RUN stub that treats the master username as
        the platform UID. Replace in production with real API or Playwright automation.
        """
        if not username or not password:
            return False, "Missing master credentials"
        # Dry-run: use the master username as the platform UID.
        return True, username


class DryRunAdapter(PlatformAdapter):
    platform_id = "dry_run"
    label = "Dry-run stub"


# Registry of adapters per game_id. Fallback to DryRunAdapter.
_ADAPTERS: Dict[str, PlatformAdapter] = {}


def register_adapter(platform_id: str, adapter: PlatformAdapter) -> None:
    _ADAPTERS[platform_id] = adapter


def get_adapter(platform_id: str) -> PlatformAdapter:
    return _ADAPTERS.get(platform_id, DryRunAdapter())


# =========================================================
# Core service
# =========================================================
async def ensure_platform_registered(
    db, user: Dict[str, Any], game: Dict[str, Any]
) -> Tuple[bool, str, Optional[str]]:
    """Ensure user is registered on the given game platform.

    Returns (success, message, platform_uid)
    """
    game_id = str(game.get("_id") or game.get("id") or "")
    platform_id = game.get("platform_id") or game_id
    username = user.get("game_username") or ""
    password = user.get("game_password") or ""

    # Already registered?
    accounts = user.get("platform_accounts") or {}
    existing = accounts.get(game_id)
    if existing and existing.get("status") == "registered" and existing.get("platform_uid"):
        return True, "Already registered", existing["platform_uid"]

    if not username or not password:
        await _emit_alert(db, user, game, "Missing master credentials for user")
        return False, "Missing master credentials for this user. Contact support.", None

    adapter = get_adapter(platform_id)
    try:
        ok, result = await adapter.register(
            username=username,
            password=password,
            context={
                "user_id": user.get("id") or str(user.get("_id")),
                "user_email": user.get("email"),
                "game_id": game_id,
                "platform_id": platform_id,
                "game_name": game.get("name"),
            },
        )
    except Exception as e:
        logger.exception("Adapter error for %s: %s", platform_id, e)
        ok, result = False, f"Adapter exception: {e}"

    now = datetime.now(timezone.utc).isoformat()
    if ok:
        await db.users.update_one(
            {"_id": ObjectId(user["id"])},
            {"$set": {
                f"platform_accounts.{game_id}": {
                    "status": "registered",
                    "platform_uid": result,
                    "registered_at": now,
                    "adapter": adapter.platform_id,
                }
            }},
        )
        logger.info("JIT register OK: user=%s game=%s uid=%s", user.get("email"), game_id, result)
        return True, "Registered", result

    # Failure: mark and alert
    await db.users.update_one(
        {"_id": ObjectId(user["id"])},
        {"$set": {
            f"platform_accounts.{game_id}": {
                "status": "failed",
                "error": str(result),
                "failed_at": now,
                "adapter": adapter.platform_id,
            }
        }},
    )
    await _emit_alert(db, user, game, f"JIT registration failed: {result}")
    return False, f"Registration failed: {result}", None


async def _emit_alert(db, user: Dict[str, Any], game: Dict[str, Any], message: str) -> None:
    doc = {
        "user_id": user.get("id") or str(user.get("_id")),
        "user_email": user.get("email"),
        "game_id": str(game.get("_id") or game.get("id") or ""),
        "game_name": game.get("name"),
        "platform_id": game.get("platform_id"),
        "type": "jit_registration_failure",
        "message": message,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.admin_alerts.insert_one(doc)
    logger.warning("Admin alert created: %s", message)


# =========================================================
# Router
# =========================================================
class RegisterBody(BaseModel):
    game_id: str


class AlertResolveBody(BaseModel):
    resolution: Optional[str] = ""


def build_platform_router(db, get_current_user, get_admin_user) -> APIRouter:
    router = APIRouter(prefix="/api/ext/platform", tags=["platform-jit"])

    @router.post("/register")
    async def platform_register(data: RegisterBody, request: Request):
        """Ensure the current user is registered on a game platform (JIT)."""
        user = await get_current_user(request)
        game = await db.games.find_one({"_id": ObjectId(data.game_id)})
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        ok, msg, uid = await ensure_platform_registered(db, user, game)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "ok", "platform_uid": uid, "message": msg}

    @router.get("/accounts")
    async def my_platform_accounts(request: Request):
        user = await get_current_user(request)
        db_user = await db.users.find_one({"_id": ObjectId(user["id"])})
        return db_user.get("platform_accounts", {}) if db_user else {}

    @router.get("/alerts")
    async def list_alerts(request: Request, status: Optional[str] = "open"):
        await get_admin_user(request)
        q: Dict[str, Any] = {}
        if status:
            q["status"] = status
        alerts = await db.admin_alerts.find(q).sort("created_at", -1).to_list(500)
        return [{"id": str(a["_id"]), **{k: v for k, v in a.items() if k != "_id"}} for a in alerts]

    @router.post("/alerts/{alert_id}/resolve")
    async def resolve_alert(alert_id: str, data: AlertResolveBody, request: Request):
        admin = await get_admin_user(request)
        r = await db.admin_alerts.update_one(
            {"_id": ObjectId(alert_id)},
            {"$set": {
                "status": "resolved",
                "resolution": data.resolution or "",
                "resolved_by": admin["email"],
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"message": "Resolved"}

    @router.post("/admin/retry/{user_id}/{game_id}")
    async def admin_retry(user_id: str, game_id: str, request: Request):
        """Admin can retry JIT registration for a user/game."""
        await get_admin_user(request)
        u = await db.users.find_one({"_id": ObjectId(user_id)})
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        u["id"] = str(u["_id"])
        game = await db.games.find_one({"_id": ObjectId(game_id)})
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        ok, msg, uid = await ensure_platform_registered(db, u, game)
        return {"status": "ok" if ok else "failed", "message": msg, "platform_uid": uid}

    return router
