"""Million Dollar Competition endpoints.

Player-facing:
  GET /api/competition              -> public payload (live/upcoming comp, totals,
                                      leaderboard, recent winners, my entries)
  GET /api/competition/leaderboard  -> top 20 leaderboard

Admin (role == "admin"):
  GET    /api/admin/competition                -> list competitions
  POST   /api/admin/competition                -> create (starts upcoming)
  POST   /api/admin/competition/{cid}/update   -> update name/prize/status/times/rules
  POST   /api/admin/competition/{cid}/draw     -> run weighted draw (idempotent after conclusion)
  POST   /api/admin/competition/{cid}/prize-paid
  POST   /api/admin/competition/{cid}/cancel
  GET    /api/admin/competition/{cid}/summary  -> totals + leaderboard (emails visible)
  GET    /api/admin/competition/{cid}/entries  -> entry ledger audit (emails visible)
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Request

from services import competition_service as cs

logger = logging.getLogger(__name__)


def _clean(doc: dict) -> dict:
    if doc is None:
        return None
    out = dict(doc)
    out.pop("_id", None)
    return out


def register_competition_routes(api_router: APIRouter, db, get_current_user):
    @api_router.get("/competition")
    async def get_competition(request: Request):
        user = None
        try:
            user = await get_current_user(request)
        except HTTPException:
            user = None
        user_id = None
        if user:
            user_id = str(user.get("id") or "")
            if not user_id or user_id == "None":
                user_id = user.get("user_id")
        return await cs.public_payload(db, user_id=user_id)

    @api_router.get("/competition/leaderboard")
    async def competition_leaderboard(request: Request, limit: int = 20):
        comp = await cs.get_live_or_upcoming(db)
        if not comp:
            return {"competition": None, "leaderboard": [], "totals": {"total_entries": 0, "total_players": 0}}
        cid = comp["id"]
        return {
            "competition_id": cid,
            "leaderboard": await cs.get_leaderboard(db, cid, limit=max(1, min(limit, 100))),
            "totals": await cs.get_competition_totals(db, cid),
        }


def register_competition_admin_routes(api_router: APIRouter, db, get_admin_user):
    @api_router.get("/admin/competition")
    async def admin_list_competitions(request: Request):
        await get_admin_user(request)
        rows = await db["competitions"].find().sort("created_at", -1).to_list(100)
        return [_clean(r) for r in rows]

    @api_router.post("/admin/competition")
    async def admin_create_competition(request: Request):
        admin = await get_admin_user(request)
        body = await request.json()
        doc = await cs.create_competition(
            db, body, created_by=admin.get("email") or admin.get("name") or "admin"
        )
        return _clean(doc)

    @api_router.post("/admin/competition/{cid}/update")
    async def admin_update_competition(cid: str, request: Request):
        admin = await get_admin_user(request)
        body = await request.json()
        try:
            doc = await cs.update_competition(
                db, cid, body,
                updated_by=admin.get("email") or admin.get("name") or "admin",
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return _clean(doc)

    @api_router.post("/admin/competition/{cid}/cancel")
    async def admin_cancel_competition(cid: str, request: Request):
        admin = await get_admin_user(request)
        try:
            doc = await cs.cancel_competition(
                db, cid, updated_by=admin.get("email") or admin.get("name") or "admin"
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return _clean(doc)

    @api_router.post("/admin/competition/{cid}/draw")
    async def admin_run_draw(cid: str, request: Request):
        admin = await get_admin_user(request)
        try:
            result = await cs.run_draw(
                db, cid, run_by=admin.get("email") or admin.get("name") or "admin"
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {
            "already_drawn": result["already_drawn"],
            "winner": result["winner"],
            "competition": _clean(result["competition"]),
        }

    @api_router.post("/admin/competition/{cid}/prize-paid")
    async def admin_mark_prize_paid(cid: str, request: Request):
        admin = await get_admin_user(request)
        try:
            doc = await cs.mark_prize_paid(
                db, cid, updated_by=admin.get("email") or admin.get("name") or "admin"
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return _clean(doc)

    @api_router.get("/admin/competition/{cid}/summary")
    async def admin_competition_summary(cid: str, request: Request):
        await get_admin_user(request)
        comp = await cs.get_by_id(db, cid)
        if not comp:
            raise HTTPException(status_code=404, detail="Competition not found")
        return {
            "competition": _clean(comp),
            "totals": await cs.get_competition_totals(db, cid),
            "leaderboard": await cs.get_leaderboard(db, cid, limit=100, include_email=True),
        }

    @api_router.get("/admin/competition/{cid}/entries")
    async def admin_competition_entries(cid: str, request: Request, limit: int = 500):
        await get_admin_user(request)
        rows = await db["competition_entries"].find({"competition_id": cid}) \
            .sort("created_at", -1).to_list(max(1, min(limit, 5000)))
        return [_clean(r) for r in rows]


def build_competition_router(db, get_current_user):
    """Player-facing competition endpoints (mounted under /api)."""
    router = APIRouter(tags=["competition"])
    register_competition_routes(router, db, get_current_user)
    return router


def build_competition_admin_router(db, get_admin_user):
    """Admin competition endpoints (mounted under /api)."""
    router = APIRouter(tags=["competition-admin"])
    register_competition_admin_routes(router, db, get_admin_user)
    return router