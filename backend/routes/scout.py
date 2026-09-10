from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_scout_router(db=None, get_admin_user=None):
    """Routes that let the free-tier AI Scout Force land leads in the platform.

    The scout Worker (scout-force/) POSTs structured, intel-only leads here.
    They are stored in ``scout_leads`` and summarized into one admin alert per
    scout per day so the siren panel stays readable.
    """
    router = APIRouter(prefix="/admin/scout", tags=["scout"])

    def _authorize(request: Request):
        token = os.environ.get("SCOUT_LEADS_TOKEN", "")
        if not token:
            raise HTTPException(status_code=503, detail="scout ingestion not configured")
        provided = (request.headers.get("Authorization") or "").replace("Bearer ", "")
        try:
            match = bool(provided) and hmac.compare_digest(
                provided.encode("utf-8"), token.encode("utf-8")
            )
        except Exception:
            match = False
        if not match:
            raise HTTPException(status_code=401, detail="unauthorized")

    @router.post("/leads")
    async def receive_leads(request: Request):
        """Accept a batch of scout leads for one scout from the Worker.

        Body: { scout, region, collected_at, leads: [...] }
        """
        _authorize(request)
        payload = await request.json()
        scout_id = (payload.get("scout") or "unknown")[:64]
        region = (payload.get("region") or "")[:80]
        leads = payload.get("leads") or []
        if not isinstance(leads, list):
            raise HTTPException(status_code=400, detail="leads must be a list")
        if len(leads) > 200:
            raise HTTPException(status_code=413, detail="batch too large (max 200 leads)")

        today = datetime.now(timezone.utc).date().isoformat()
        inserted = 0
        for lead in leads:
            if not isinstance(lead, dict):
                continue
            name = str(lead.get("name") or lead.get("url") or "")[:200]
            url = str(lead.get("url") or "")[:500]
            doc = {
                "scout": scout_id,
                "region": region,
                "name": name,
                "url": url,
                "note": str(lead.get("note") or "")[:500],
                "kind": str(lead.get("kind") or "unknown")[:40],
                "score": float(lead.get("score") or 0.0),
                "collected_at": payload.get("collected_at") or _now_iso(),
                "created_at": _now_iso(),
                "status": "new",
            }
            await db["scout_leads"].insert_one(doc)
            inserted += 1

        # One alert per scout per day (deduped by created_date), so a busy
        # force doesn't flood the siren panel.
        if inserted:
            existing = await db["admin_alerts"].find_one(
                {"type": "scout_leads", "scout": scout_id, "created_date": today}
            )
            if existing:
                await db["admin_alerts"].update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"lead_count": int(existing.get("lead_count", 0)) + inserted}},
                )
            else:
                await db["admin_alerts"].insert_one(
                    {
                        "type": "scout_leads",
                        "scout": scout_id,
                        "severity": "info",
                        "status": "open",
                        "created_date": today,
                        "lead_count": inserted,
                        "message": f"Scout {scout_id} surfaced {inserted} new player-source lead{'s' if inserted != 1 else ''}",
                        "created_at": _now_iso(),
                    }
                )
        return {"ok": True, "inserted": inserted, "scout": scout_id}

    @router.get("/leads")
    async def list_leads(request: Request, limit: int = 100):
        """Admin: browse the scout lead backlog (intel-only)."""
        if get_admin_user:
            await get_admin_user(request)
        limit = max(1, min(limit, 500))
        items = await db["scout_leads"].find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
        return {"total": len(items), "items": items}

    return router