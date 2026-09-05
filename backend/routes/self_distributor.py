"""Admin router for Self-Distributor mode.

Lets the operator swap the automated third-party proxy pool for a manual
fulfillment queue: deposits land as "send these credits" tasks, the operator
sends them by hand on the game backend, then confirms. Full margin, no
wholesale buy-in.

Endpoints
---------
GET    /api/ext/distributor/settings                             mode + toggle info
POST   /api/ext/distributor/settings                             {mode: "auto"|"manual"}
GET    /api/ext/distributor/queue?status=awaiting_send           pending send instructions
GET    /api/ext/distributor/summary                              counts + pending credits
POST   /api/ext/distributor/queue/{task_id}/confirm-sent         mark sent (deposit completes)
POST   /api/ext/distributor/queue/{task_id}/mark-failed          couldn't send
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from services.self_distributor import (
    confirm_sent,
    get_settings,
    list_tasks,
    mark_failed,
    MODE_AUTO,
    MODE_MANUAL,
    set_mode,
    summary,
    STATUS_AWAITING,
)


class SettingsBody(BaseModel):
    mode: str


class TaskNoteBody(BaseModel):
    note: Optional[str] = None


def build_self_distributor_router(db, get_admin_user) -> APIRouter:
    router = APIRouter(prefix="/ext/distributor", tags=["self-distributor"])

    @router.get("/settings")
    async def read_settings(request: Request):
        await get_admin_user(request)
        return await get_settings(db)

    @router.post("/settings")
    async def update_settings(body: SettingsBody, request: Request):
        admin = await get_admin_user(request)
        if body.mode not in (MODE_AUTO, MODE_MANUAL):
            raise HTTPException(
                status_code=400,
                detail=f"mode must be '{MODE_AUTO}' (proxy pool) or '{MODE_MANUAL}' (self)",
            )
        return await set_mode(db, body.mode, updated_by=admin["email"])

    @router.get("/queue")
    async def queue(request: Request, status: Optional[str] = STATUS_AWAITING, limit: int = 100):
        await get_admin_user(request)
        if status not in (None, "awaiting_send", "done", "failed", "cancelled"):
            raise HTTPException(
                status_code=400,
                detail="status must be one of awaiting_send, done, failed, cancelled",
            )
        return await list_tasks(db, status=status, limit=min(limit, 500))

    @router.get("/summary")
    async def read_summary(request: Request):
        await get_admin_user(request)
        return await summary(db)

    @router.post("/queue/{task_id}/confirm-sent")
    async def confirm(task_id: str, body: TaskNoteBody, request: Request):
        admin = await get_admin_user(request)
        ok, msg = await confirm_sent(db, task_id, admin["email"], note=body.note or "")
        if not ok:
            raise HTTPException(status_code=409, detail=msg)
        return {"ok": True, "message": msg}

    @router.post("/queue/{task_id}/mark-failed")
    async def fail(task_id: str, body: TaskNoteBody, request: Request):
        admin = await get_admin_user(request)
        ok, msg = await mark_failed(db, task_id, admin["email"], reason=body.note or "")
        if not ok:
            raise HTTPException(status_code=409, detail=msg)
        return {"ok": True, "message": msg}

    return router