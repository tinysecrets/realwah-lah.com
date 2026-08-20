"""Player-facing Genie service and escalation relay."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

GENIE_SYSTEM_PROMPT = """You are Genie, the friendly WAH-LAH player support guide.

Answer from these site rules and be clear about what is known:
- Deposits add game credits after the selected payment is confirmed. Players should use the payment instructions shown in the app and keep their payment reference or receipt.
- Cash App and crypto deposits are manually reviewed when required. Never promise instant crediting if a payment is still pending.
- Redemptions are requested from redeemable credits, not credits still locked by playthrough. Small redemptions may process without KYC; KYC is required at $500 or more (basic) and $5,000 or more (enhanced). Approved enhanced KYC also covers the basic tier.
- BTC redemptions can be held for manual review. Never promise an exact payout time; tell players to allow up to 24 hours for normal review and longer when KYC, address checks, or compliance review is pending.
- Players in a blocked state or outside the US cannot use sweepstakes features. Do not suggest bypassing geolocation or compliance checks.
- Common fixes: confirm the player is signed into the right account, check that a deposit receipt/reference was submitted, verify the BTC address, check the redemption/KYC status, and avoid duplicate submissions while a payment or payout is pending.
- You can explain status and next steps, but you cannot change balances, approve redemptions, bypass KYC, unblock states, or promise a payout.
- Escalate when a payment or payout is missing after the stated review window, an account appears compromised, a player disputes a balance, KYC is stuck or rejected unexpectedly, or the player explicitly asks for a human. When escalating, begin the response with exactly [ESCALATE] and briefly state what the player should expect.

Be concise, calm, and practical. Never request passwords, full payment credentials, or private keys."""


def _provider_configs() -> list[dict[str, str]]:
    providers = []
    cerebras_key = os.environ.get("CEREBRAS_API_KEY", "").strip()
    if cerebras_key:
        providers.append({
            "name": "cerebras",
            "key": cerebras_key,
            "base_url": "https://api.cerebras.ai/v1",
            "model": os.environ.get("CEREBRAS_MODEL", "llama-3.3-70b"),
        })
    fallback_key = os.environ.get("GENIE_FALLBACK_API_KEY", "").strip()
    if fallback_key:
        providers.append({
            "name": "fallback",
            "key": fallback_key,
            "base_url": os.environ.get("GENIE_FALLBACK_BASE_URL", "https://api.openai.com/v1"),
            "model": os.environ.get("GENIE_FALLBACK_MODEL", "gpt-4o-mini"),
        })
    return providers


async def complete(messages: list[dict[str, str]]) -> tuple[str, str, str]:
    providers = _provider_configs()
    if not providers:
        raise RuntimeError("No Genie provider configured. Set CEREBRAS_API_KEY or GENIE_FALLBACK_API_KEY.")
    last_error: Optional[Exception] = None
    for provider in providers:
        try:
            client = AsyncOpenAI(api_key=provider["key"], base_url=provider["base_url"])
            response = await client.chat.completions.create(
                model=provider["model"],
                messages=messages,
                temperature=0.2,
                max_completion_tokens=700,
            )
            return (response.choices[0].message.content or "").strip(), provider["name"], provider["model"]
        except Exception as exc:
            last_error = exc
            logger.warning("Genie provider %s failed: %s", provider["name"], exc)
    raise RuntimeError(f"All Genie providers failed: {last_error}")


async def create_escalation_ticket(db, user: Dict[str, Any], session_id: str, message: str, reply: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    ticket = {
        "id": str(uuid.uuid4()),
        "user_id": str(user["_id"]),
        "user_email": user.get("email", ""),
        "user_name": user.get("name", ""),
        "subject": "Genie escalation: player support needed",
        "message": message,
        "genie_reply": reply,
        "source": "genie",
        "priority": "high",
        "status": "open",
        "created_at": now,
        "updated_at": now,
        "responses": [],
    }
    await db.support_tickets.insert_one(ticket)
    return ticket["id"]


async def relay_escalation(ticket_id: str, user: Dict[str, Any], message: str) -> None:
    if os.environ.get("TELEGRAM_ESCALATION_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_ESCALATION_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.warning("Telegram escalation enabled but token or chat id is missing")
        return
    text = f"WAH-LAH Genie escalation\nTicket: {ticket_id}\nPlayer: {user.get('email', 'unknown')}\nIssue: {message[:900]}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            response.raise_for_status()
    except Exception:
        logger.exception("Failed to relay Genie escalation %s to Telegram", ticket_id)
