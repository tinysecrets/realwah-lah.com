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
GET    /api/ext/distributor/summary                              counts + overdue + today's P&L
POST   /api/ext/distributor/queue/{task_id}/confirm-sent         mark sent (deposit completes)
POST   /api/ext/distributor/queue/{task_id}/mark-failed          couldn't send
POST   /api/ext/distributor/queue/{task_id}/retry                failed -> awaiting_send
POST   /api/ext/distributor/queue/{task_id}/cancel               terminal cancel (no credits move)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from services.self_distributor import (
    cancel_task,
    confirm_sent,
    get_settings,
    list_tasks,
    mark_failed,
    MODE_AUTO,
    MODE_MANUAL,
    retry_task,
    set_mode,
    summary,
    STATUS_AWAITING,
)


class SettingsBody(BaseModel):
    mode: str


class TaskNoteBody(BaseModel):
    note: Optional[str] = None

    @classmethod
    def _cap(cls, v: Optional[str]) -> Optional[str]:
        return v[:1000] if isinstance(v, str) else v


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
        return await list_tasks(db, status=status, limit=max(1, min(limit, 500)))

    @router.get("/summary")
    async def read_summary(request: Request):
        await get_admin_user(request)
        return await summary(db)

    @router.post("/queue/{task_id}/confirm-sent")
    async def confirm(task_id: str, body: TaskNoteBody, request: Request):
        admin = await get_admin_user(request)
        ok, msg = await confirm_sent(
            db, task_id, admin["email"], note=TaskNoteBody._cap(body.note) or ""
        )
        if not ok:
            raise HTTPException(status_code=409, detail=msg)
        return {"ok": True, "message": msg}

    @router.post("/queue/{task_id}/mark-failed")
    async def fail(task_id: str, body: TaskNoteBody, request: Request):
        admin = await get_admin_user(request)
        ok, msg = await mark_failed(
            db, task_id, admin["email"], reason=TaskNoteBody._cap(body.note) or ""
        )
        if not ok:
            raise HTTPException(status_code=409, detail=msg)
        return {"ok": True, "message": msg}

    @router.post("/queue/{task_id}/retry")
    async def retry(task_id: str, request: Request):
        admin = await get_admin_user(request)
        ok, msg = await retry_task(db, task_id, admin["email"])
        if not ok:
            raise HTTPException(status_code=409, detail=msg)
        return {"ok": True, "message": msg}

    @router.post("/queue/{task_id}/cancel")
    async def cancel(task_id: str, body: TaskNoteBody, request: Request):
        admin = await get_admin_user(request)
        ok, msg = await cancel_task(
            db, task_id, admin["email"], reason=TaskNoteBody._cap(body.note) or ""
        )
        if not ok:
            raise HTTPException(status_code=409, detail=msg)
        return {"ok": True, "message": msg}

    return router