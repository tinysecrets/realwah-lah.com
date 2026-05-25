"""
Admin Revenue Dashboard Endpoints.

GET  /api/admin/revenue/summary    -> aggregated P&L (window=days, default 30)
GET  /api/admin/revenue/ledger     -> last N raw ledger rows
GET  /api/admin/revenue/settings   -> current fee rates
POST /api/admin/revenue/settings   -> update fee rates live (no redeploy)
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from typing import Optional
from services.revenue import get_rates, set_rates, revenue_summary


def register_revenue_admin_routes(api_router: APIRouter, db, get_admin_user):
    @api_router.get("/admin/revenue/summary")
    async def admin_revenue_summary(request: Request, days: int = Query(30, ge=1, le=365)):
        await get_admin_user(request)
        return await revenue_summary(db, days=days)

    @api_router.get("/admin/revenue/ledger")
    async def admin_revenue_ledger(request: Request, limit: int = Query(100, ge=1, le=1000)):
        await get_admin_user(request)
        rows = await db.revenue_ledger.find().sort("created_at", -1).to_list(limit)
        for r in rows:
            r.pop("_id", None)
        return rows

    @api_router.get("/admin/revenue/settings")
    async def admin_revenue_settings(request: Request):
        await get_admin_user(request)
        return await get_rates(db)

    @api_router.post("/admin/revenue/settings")
    async def admin_update_revenue_settings(request: Request):
        admin = await get_admin_user(request)
        body = await request.json()
        return await set_rates(
            db,
            cashtag=body.get("cashtag"),
            giftcard=body.get("giftcard"),
            btc=body.get("btc"),
            updated_by=admin.get("email", "admin"),
        )
