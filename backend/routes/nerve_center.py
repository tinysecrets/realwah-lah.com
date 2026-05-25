"""NERVE CENTER — aggregated ops console for admins.

One endpoint returns everything the admin dashboard needs so the frontend
can do a single request per refresh cycle (cheap + atomic). A second
endpoint streams a reverse-chronological activity feed.
"""
from __future__ import annotations

import asyncio
import json as _json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Set

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect


# =================================================================
# Live broadcast hub — any code-path can call broadcast() to push
# events to every connected Nerve Center client.
# =================================================================
class _Broadcaster:
    def __init__(self):
        self._clients: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)

    async def broadcast(self, event: Dict[str, Any]):
        if not self._clients:
            return
        payload = _json.dumps(event)
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)


broadcaster = _Broadcaster()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _count(coll, query: dict) -> int:
    return await coll.count_documents(query)


def build_nerve_center_router(db, get_admin_user) -> APIRouter:
    router = APIRouter(prefix="/api/ext/nerve", tags=["nerve-center"])

    # ======================================================
    # Aggregated overview — the main dashboard payload
    # ======================================================
    @router.get("/overview")
    async def overview(request: Request):
        await get_admin_user(request)
        now = _now()
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)

        # Run many queries in parallel
        (
            users_total,
            users_24h,
            users_week,
            payments_24h_count,
            payments_week_count,
            payments_paid_count,
            tickets_open,
            redemptions_pending,
            admin_alerts_open,
            jit_failed_recent,
        ) = await asyncio.gather(
            _count(db.users, {}),
            _count(db.users, {"created_at": {"$gte": _iso(day_ago)}}),
            _count(db.users, {"created_at": {"$gte": _iso(week_ago)}}),
            _count(db.payment_transactions, {"created_at": {"$gte": _iso(day_ago)}}),
            _count(db.payment_transactions, {"created_at": {"$gte": _iso(week_ago)}}),
            _count(db.payment_transactions, {"payment_status": "paid"}),
            _count(db.support_tickets, {"status": {"$in": ["open", "in_progress"]}}),
            _count(db.redemption_requests, {"status": "pending"}),
            _count(db.admin_alerts, {"status": "open"}),
            _count(db.admin_alerts, {"type": {"$regex": "jit|pool_payout"}, "status": "open"}),
        )

        # Revenue — sum paid transactions in last 24h and 7d
        async def _sum_paid(since_iso: str) -> float:
            pipeline = [
                {"$match": {"payment_status": "paid", "created_at": {"$gte": since_iso}}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
            rows = await db.payment_transactions.aggregate(pipeline).to_list(1)
            return float(rows[0]["total"]) if rows else 0.0

        revenue_24h, revenue_week = await asyncio.gather(
            _sum_paid(_iso(day_ago)), _sum_paid(_iso(week_ago))
        )

        # 7-day revenue sparkline — one bucket per day
        sparkline = []
        for i in range(6, -1, -1):
            day_start = now - timedelta(days=i + 1)
            day_end = now - timedelta(days=i)
            pipeline = [
                {"$match": {
                    "payment_status": "paid",
                    "created_at": {"$gte": _iso(day_start), "$lt": _iso(day_end)},
                }},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
            rows = await db.payment_transactions.aggregate(pipeline).to_list(1)
            sparkline.append({
                "day": day_start.strftime("%a"),
                "value": float(rows[0]["total"]) if rows else 0.0,
            })

        # Pool health (delegate to existing service)
        try:
            from services.proxy_pool import pool_health
            pool = await pool_health(db)
        except Exception:
            pool = {"total": 0, "active": 0, "cooldown": 0, "locked": 0, "daily_capacity_remaining": 0.0}

        # Latest 5 open admin alerts (for the siren panel)
        siren_alerts = []
        cursor = db.admin_alerts.find(
            {"status": "open"}, {"_id": 1, "type": 1, "message": 1, "created_at": 1, "user_email": 1}
        ).sort("created_at", -1).limit(5)
        async for a in cursor:
            siren_alerts.append({
                "id": str(a["_id"]),
                "type": a.get("type", "unknown"),
                "message": a.get("message", ""),
                "user_email": a.get("user_email"),
                "created_at": a.get("created_at"),
            })

        return {
            "timestamp": _iso(now),
            "users": {"total": users_total, "last_24h": users_24h, "last_7d": users_week},
            "payments": {
                "transactions_24h": payments_24h_count,
                "transactions_7d": payments_week_count,
                "total_paid_ever": payments_paid_count,
                "revenue_24h": round(revenue_24h, 2),
                "revenue_7d": round(revenue_week, 2),
                "sparkline_7d": sparkline,
            },
            "queues": {
                "tickets_open": tickets_open,
                "redemptions_pending": redemptions_pending,
                "admin_alerts_open": admin_alerts_open,
                "jit_failures_open": jit_failed_recent,
            },
            "pool": pool,
            "siren": siren_alerts,
        }

    # ======================================================
    # Live activity feed — reverse-chronological event stream
    # ======================================================
    @router.get("/activity-feed")
    async def activity_feed(request: Request, limit: int = 50):
        await get_admin_user(request)
        limit = max(1, min(limit, 200))

        events: List[Dict[str, Any]] = []

        # Users registered (last N)
        async for u in db.users.find(
            {}, {"email": 1, "created_at": 1, "role": 1}
        ).sort("created_at", -1).limit(limit):
            events.append({
                "ts": u.get("created_at"),
                "kind": "user.registered",
                "icon": "U",
                "title": f"{u.get('email')} registered",
                "detail": f"role={u.get('role', 'user')}",
            })

        # Payments (paid + failed)
        async for t in db.payment_transactions.find(
            {}, {"user_email": 1, "amount": 1, "payment_status": 1, "created_at": 1, "game_name": 1}
        ).sort("created_at", -1).limit(limit):
            status = t.get("payment_status", "pending")
            events.append({
                "ts": t.get("created_at"),
                "kind": f"payment.{status}",
                "icon": "$",
                "title": f"${t.get('amount', 0):.2f} {status.upper()} — {t.get('user_email', '?')}",
                "detail": f"game={t.get('game_name', '?')}",
            })

        # Redemptions
        async for r in db.redemption_requests.find(
            {}, {"user_email": 1, "game_credits": 1, "status": 1, "created_at": 1}
        ).sort("created_at", -1).limit(limit):
            events.append({
                "ts": r.get("created_at"),
                "kind": f"redemption.{r.get('status', 'pending')}",
                "icon": "R",
                "title": f"{r.get('game_credits', 0)} credits → BTC ({r.get('user_email', '?')})",
                "detail": f"status={r.get('status', 'pending')}",
            })

        # Support tickets opened
        async for s in db.support_tickets.find(
            {}, {"user_email": 1, "subject": 1, "status": 1, "created_at": 1}
        ).sort("created_at", -1).limit(limit):
            events.append({
                "ts": s.get("created_at"),
                "kind": "ticket.opened",
                "icon": "T",
                "title": f"{s.get('subject', 'Ticket')} ({s.get('user_email', '?')})",
                "detail": f"status={s.get('status', 'open')}",
            })

        # Admin alerts
        async for a in db.admin_alerts.find(
            {}, {"type": 1, "message": 1, "status": 1, "created_at": 1}
        ).sort("created_at", -1).limit(limit):
            events.append({
                "ts": a.get("created_at"),
                "kind": f"alert.{a.get('type', 'generic')}",
                "icon": "!",
                "title": a.get("message", "(admin alert)"),
                "detail": f"status={a.get('status', 'open')}",
            })

        # Sort all by ts desc, slice to limit
        def _key(e):
            return e.get("ts") or ""
        events.sort(key=_key, reverse=True)
        return events[:limit]

    # ======================================================
    # Alert acknowledgment
    # ======================================================
    @router.post("/alerts/{alert_id}/acknowledge")
    async def acknowledge_alert(alert_id: str, request: Request):
        admin = await get_admin_user(request)
        try:
            oid = ObjectId(alert_id)
        except Exception:
            raise HTTPException(400, "Invalid alert id")
        r = await db.admin_alerts.update_one(
            {"_id": oid},
            {"$set": {
                "status": "acknowledged",
                "acknowledged_at": _iso(_now()),
                "acknowledged_by": admin.get("email"),
            }},
        )
        if r.matched_count == 0:
            raise HTTPException(404, "Alert not found")
        await broadcaster.broadcast({
            "kind": "alert.acknowledged",
            "alert_id": alert_id,
            "ts": _iso(_now()),
        })
        return {"acknowledged": True}

    # ======================================================
    # WebSocket — live push of overview + events
    # ======================================================
    @router.websocket("/ws")
    async def nerve_ws(websocket: WebSocket):
        # NOTE: WebSocket auth — we accept the connection, then require an
        # auth message. The frontend sends its bearer/cookie within a tick.
        # For this MVP we rely on the cookie already being on the request.
        cookies = websocket.cookies or {}
        token = cookies.get("auth_token") or cookies.get("access_token")
        if not token:
            await websocket.close(code=4401)
            return

        # Minimal admin check — decode the JWT and confirm role=admin.
        try:
            import os as _os
            import jwt as _jwt

            claims = _jwt.decode(
                token,
                _os.environ["JWT_SECRET"],
                algorithms=["HS256"],
            )
            if claims.get("role") != "admin":
                await websocket.close(code=4403)
                return
        except Exception:
            await websocket.close(code=4401)
            return

        await broadcaster.connect(websocket)
        # Send a hello payload so the client knows it's live
        try:
            await websocket.send_json({"kind": "hello", "ts": _iso(_now())})
            # Periodic server-side ping so proxies don't cull idle connections
            while True:
                await asyncio.sleep(25)
                await websocket.send_json({"kind": "ping", "ts": _iso(_now())})
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            broadcaster.disconnect(websocket)

    return router
