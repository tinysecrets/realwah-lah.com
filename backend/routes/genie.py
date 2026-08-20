"""Player-facing Genie chat route."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.genie import GENIE_SYSTEM_PROMPT, complete, create_escalation_ticket, relay_escalation


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=2000)


def build_genie_router(db, get_current_user) -> APIRouter:
    router = APIRouter(prefix="/genie", tags=["genie"])

    @router.post("/chat")
    async def chat(request: ChatRequest, user=Depends(get_current_user)):
        session_id = request.session_id or str(uuid.uuid4())
        user_id = str(user["_id"])
        now = datetime.now(timezone.utc).isoformat()
        await db.genie_messages.insert_one({
            "session_id": session_id,
            "user_id": user_id,
            "role": "user",
            "content": request.message,
            "created_at": now,
        })
        history = await db.genie_messages.find(
            {"session_id": session_id, "user_id": user_id}, {"_id": 0, "role": 1, "content": 1}
        ).sort("created_at", 1).limit(20).to_list(length=20)
        try:
            reply, provider, model = await complete([
                {"role": "system", "content": GENIE_SYSTEM_PROMPT},
                *[{"role": item["role"], "content": item["content"]} for item in history],
            ])
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

        escalated = reply.startswith("[ESCALATE]")
        ticket_id = None
        if escalated:
            ticket_id = await create_escalation_ticket(db, user, session_id, request.message, reply)
            await relay_escalation(ticket_id, user, request.message)
            reply = reply.replace("[ESCALATE]", "", 1).strip()
        await db.genie_messages.insert_one({
            "session_id": session_id,
            "user_id": user_id,
            "role": "assistant",
            "content": reply,
            "provider": provider,
            "model": model,
            "escalated": escalated,
            "ticket_id": ticket_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "session_id": session_id,
            "reply": reply,
            "provider": provider,
            "model": model,
            "escalated": escalated,
            "ticket_id": ticket_id,
        }

    @router.get("/history/{session_id}")
    async def history(session_id: str, user=Depends(get_current_user)):
        rows = await db.genie_messages.find(
            {"session_id": session_id, "user_id": str(user["_id"])}, {"_id": 0}
        ).sort("created_at", 1).to_list(length=100)
        return {"session_id": session_id, "messages": rows}

    return router
