"""Distributor-operator admin API — the daily money surface.

The operator IS the distributor: players send Cash App / Chime, the operator
verifies in the provider app, reconciles here, and the system credits NET
(after the house fee), records the keep, and routes the credits to the game —
either as a manual queue task (self-distributor mode) or via the proxy pool.

Endpoints
---------
POST   /api/admin/cashtag/reconcile   verify + credit a Cash App/Chime deposit
GET    /api/admin/users               paginated user list (safe projection)
PATCH  /api/admin/users/{id}          role + audited credit adjustments
GET    /api/admin/transactions        unified money feed across all rails
GET    /api/admin/stats               morning-glance distributor stats

All routes are admin-only. Money-moving routes are idempotent.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from config.currency_config import MAX_PURCHASE_USD_PER_DAY, MIN_PURCHASE_USD
from services.currency_service import CurrencyService
from services.money_feed import VALID_KINDS as FEED_KINDS
from services.money_feed import get_feed

logger = logging.getLogger(__name__)

SAFE_USER_PROJECTION = {
    "password_hash": 0,
    "twofa_secret": 0,
    "twofa_pending_secret": 0,
}


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------
class ReconcileBody(BaseModel):
    user_id: Optional[str] = Field(default=None, description="Mongo user _id (preferred)")
    user_email: Optional[str] = Field(default=None, description="Lookup key if user_id omitted")
    amount_usd: float = Field(gt=0, le=MAX_PURCHASE_USD_PER_DAY)
    source: str = Field(default="cashapp", description="cashapp | chime | cashtag")
    receipt: Optional[str] = Field(default=None, max_length=128,
                                   description="Provider receipt/confirmation # (idempotency key)")
    note: Optional[str] = Field(default="", max_length=500)
    platform: Optional[str] = Field(default=None, max_length=64,
                                    description="Game name or id to fund (omit = local balance only)")
    apply_fee: bool = Field(default=True, description="False = whale comp (0% fee, audited)")


class UserPatchBody(BaseModel):
    role: Optional[str] = Field(default=None, description="user | admin")
    adjust_sugar_tokens: Optional[int] = Field(default=0)
    adjust_game_credits: Optional[int] = Field(default=0)
    note: Optional[str] = Field(default="", max_length=500)
    game_username: Optional[str] = Field(default=None, max_length=128)
    game_password: Optional[str] = Field(default=None, max_length=128)
    game_accounts: Optional[Dict[str, Any]] = Field(default=None)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _safe_user(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc = dict(doc)
    doc.pop("password_hash", None)
    doc.pop("twofa_secret", None)
    doc.pop("twofa_pending_secret", None)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


async def _resolve_user(db, user_id: Optional[str], user_email: Optional[str]) -> Dict[str, Any]:
    if user_id:
        try:
            user = await db.users.find_one({"_id": ObjectId(user_id)})
        except (InvalidId, TypeError):
            raise HTTPException(status_code=422, detail="user_id is not a valid id")
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    if user_email:
        user = await db.users.find_one({"email": user_email.strip().lower()})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    raise HTTPException(status_code=422, detail="Provide user_id or user_email")


async def _resolve_platform(db, platform: Optional[str]) -> Optional[str]:
    """Canonicalize a game name/id against active games (typo guard)."""
    if not platform or not platform.strip():
        return None
    want = platform.strip()
    games = await db.games.find({"is_active": True}).to_list(100)
    for g in games:
        if want == str(g.get("_id")) or want.lower() == str(g.get("name", "")).lower():
            return str(g.get("name") or want)
    valid = sorted(str(g.get("name")) for g in games if g.get("name"))
    raise HTTPException(
        status_code=400,
        detail=f"Unknown platform '{want}'. Active games: {', '.join(valid) or 'none'}. "
               f"Omit platform to keep credits on the local balance.",
    )


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------
def build_distributor_admin_router(db, get_admin_user) -> APIRouter:
    router = APIRouter(tags=["distributor-admin"])
    currency = CurrencyService(db)

    # -- CashApp / Chime reconcile --------------------------------------
    @router.post("/admin/cashtag/reconcile")
    async def cashtag_reconcile(body: ReconcileBody, request: Request):
        admin = await get_admin_user(request)
        if body.amount_usd < MIN_PURCHASE_USD:
            raise HTTPException(
                status_code=400, detail=f"Minimum reconcile is ${MIN_PURCHASE_USD:,.2f}."
            )
        source = body.source.strip().lower()
        if source not in ("cashapp", "chime", "cashtag"):
            raise HTTPException(status_code=400, detail="source must be cashapp, chime, or cashtag")

        user = await _resolve_user(db, body.user_id, body.user_email)
        platform = await _resolve_platform(db, body.platform)

        # Best-effort unique guard on (source, receipt) so even a race between
        # two admin tabs cannot double-insert the same provider receipt.
        try:
            await db.manual_deposits.create_index([("source", 1), ("receipt", 1)], unique=True)
        except Exception:
            pass  # fake DBs in tests, or index already exists

        ok, msg, deposit_id = await currency.create_manual_deposit(
            user_id=str(user["_id"]),
            user_email=user.get("email", ""),
            amount_usd=body.amount_usd,
            source=source,
            receipt=(body.receipt or "").strip() or f"noreceipt-{body.amount_usd}-{user.get('email', '')}",
            admin_email=admin.get("email", "admin"),
            platform=platform,
            apply_fee=body.apply_fee,
            note=body.note or "",
        )
        if not ok or not deposit_id:
            raise HTTPException(status_code=400, detail=msg)
        duplicate = msg.startswith("Deposit already reconciled")

        if not duplicate:
            ok, msg = await currency.complete_manual_deposit(deposit_id)
            if not ok:
                logger.error("manual deposit %s settle failed: %s", deposit_id, msg)
                raise HTTPException(status_code=500, detail=msg)

        deposit = await db.manual_deposits.find_one({"id": deposit_id}) or {}
        mode = "manual"
        try:
            from services.self_distributor import get_mode
            mode = await get_mode(db)
        except Exception:
            pass
        return {
            "ok": True,
            "duplicate": duplicate,
            "deposit_id": deposit_id,
            "user_email": user.get("email"),
            "gross_usd": deposit.get("amount_usd"),
            "fee_usd": deposit.get("fee_usd"),
            "fee_rate": deposit.get("fee_rate"),
            "net_usd": deposit.get("net_usd"),
            "sugar_tokens": deposit.get("sugar_tokens"),
            "status": deposit.get("status"),
            "distribution_mode": mode,
            "pool_transfer_status": deposit.get("pool_transfer_status"),
            "distribution_task_id": deposit.get("distribution_task_id"),
            "message": msg,
        }

    # -- Users ----------------------------------------------------------
    @router.get("/admin/users")
    async def admin_list_users(
        request: Request,
        q: Optional[str] = Query(default=None, max_length=100),
        role: Optional[str] = Query(default=None),
        skip: int = Query(default=0, ge=0, le=100_000),
        limit: int = Query(default=50, ge=1, le=200),
    ):
        await get_admin_user(request)
        query: Dict[str, Any] = {}
        if role:
            if role not in ("user", "admin"):
                raise HTTPException(status_code=400, detail="role must be user or admin")
            query["role"] = role
        if q:
            rx = {"$regex": q.strip(), "$options": "i"}
            query["$or"] = [{"email": rx}, {"name": rx}, {"game_username": rx}]
        total = await db.users.count_documents(query)
        docs = await db.users.find(query, SAFE_USER_PROJECTION).sort(
            "created_at", -1).skip(skip).limit(limit).to_list(limit)
        return {"total": total, "skip": skip, "limit": limit,
                "users": [_safe_user(d) for d in docs]}

    @router.patch("/admin/users/{user_id}")
    async def admin_patch_user(user_id: str, body: UserPatchBody, request: Request):
        admin = await get_admin_user(request)
        try:
            oid = ObjectId(user_id)
        except (InvalidId, TypeError):
            raise HTTPException(status_code=422, detail="user_id is not a valid id")
        user = await db.users.find_one({"_id": oid})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        updates: Dict[str, Any] = {}
        if body.role is not None:
            if body.role not in ("user", "admin"):
                raise HTTPException(status_code=400, detail="role must be user or admin")
            updates["role"] = body.role
        if body.game_username is not None:
            updates["game_username"] = body.game_username
        if body.game_password is not None:
            updates["game_password"] = body.game_password
        if body.game_accounts is not None:
            updates["game_accounts"] = body.game_accounts
        inc: Dict[str, Any] = {}
        if body.adjust_sugar_tokens:
            inc["sugar_tokens"] = int(body.adjust_sugar_tokens)
        if body.adjust_game_credits:
            inc["game_credits"] = int(body.adjust_game_credits)
        if not updates and not inc:
            raise HTTPException(status_code=400, detail="Nothing to change")

        op: Dict[str, Any] = {}
        if updates:
            op["$set"] = updates
        if inc:
            op["$inc"] = inc
        await db.users.update_one({"_id": oid}, op)

        # Every manual money movement is audited — no silent balance edits.
        try:
            await db.credit_adjustments.insert_one({
                "user_id": str(oid),
                "user_email": user.get("email"),
                "set": updates,
                "inc": inc,
                "note": (body.note or "")[:500],
                "actor": admin.get("email", "admin"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            logger.exception("credit_adjustments audit write failed.")

        fresh = await db.users.find_one({"_id": oid}, SAFE_USER_PROJECTION)
        return {"ok": True, "user": _safe_user(fresh or {})}

    # -- Unified money feed ----------------------------------------------
    @router.get("/admin/transactions")
    async def admin_transactions(
        request: Request,
        kind: str = Query(default="all"),
        skip: int = Query(default=0, ge=0, le=100_000),
        limit: int = Query(default=50, ge=1, le=200),
    ):
        await get_admin_user(request)
        if kind not in FEED_KINDS:
            raise HTTPException(status_code=400, detail="Unknown kind filter")
        # One source of truth: the same feed the player Ledger reads.
        return await get_feed(db, kind=kind, skip=skip, limit=limit)

    # -- Morning-glance stats ---------------------------------------------
    @router.get("/admin/stats")
    async def admin_stats(request: Request):
        await get_admin_user(request)
        today = datetime.now(timezone.utc).date().isoformat()
        week_ago = (datetime.now(timezone.utc).date().isoformat())  # day-granular; see below

        async def _count(coll: str, query: Dict[str, Any]) -> int:
            try:
                return await db[coll].count_documents(query)
            except Exception:
                return 0

        async def _since_today(coll: str) -> List[Dict[str, Any]]:
            try:
                return await db[coll].find({}).to_list(10_000)
            except Exception:
                return []

        users_total = await _count("users", {})
        new_users = sum(1 for u in await _since_today("users")
                        if (u.get("created_at") or "") >= week_ago and _within_days(u.get("created_at"), 7))

        btc_today = [d for d in await _since_today("btc_deposits")
                     if (d.get("created_at") or "") >= today]
        manual_today = [d for d in await _since_today("manual_deposits")
                        if (d.get("created_at") or "") >= today]
        fees_today = sum(float(r.get("fee_usd") or 0)
                         for r in await _since_today("revenue_ledger")
                         if (r.get("created_at") or "") >= today)

        mode = "auto"
        try:
            from services.self_distributor import get_mode
            mode = await get_mode(db)
        except Exception:
            pass

        return {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "distribution_mode": mode,
            "users": {"total": users_total, "new_7d": new_users},
            "deposits_today": {
                "btc_count": len(btc_today),
                "btc_gross_usd": round(sum(float(d.get("amount_usd") or 0) for d in btc_today), 2),
                "manual_count": len(manual_today),
                "manual_gross_usd": round(sum(float(d.get("amount_usd") or 0) for d in manual_today), 2),
                "fees_usd": round(fees_today, 2),
            },
            "distribution": {
                "awaiting_send": await _count("distribution_tasks", {"status": "awaiting_send"}),
                "failed": await _count("distribution_tasks", {"status": "failed"}),
                "done_total": await _count("distribution_tasks", {"status": "done"}),
            },
            "queues": {
                "payouts_hold": await _count("redemption_requests", {"status": "hold_admin_review"}),
                "kyc_pending": await _count("kyc_profiles", {"status": {"$in": ["pending", "review"]}}),
                "open_alerts": await _count("admin_alerts", {"status": "open"}),
            },
        }

    return router


def _within_days(created_at: Optional[str], days: int) -> bool:
    try:
        dt = datetime.fromisoformat(created_at or "")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days < days
    except (ValueError, TypeError):
        return False


# NOTE: transaction normalization lives in services/money_feed.py — the single
# source of truth shared by the admin feed and the player Ledger.
