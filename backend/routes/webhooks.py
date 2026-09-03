from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from services import btc_processor
from services.currency_service import CurrencyService

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_webhooks_router(db=None):
    """Return webhook routes mounted under /api/webhooks."""
    router = APIRouter(prefix="/webhooks", tags=["webhooks"])
    currency_service = CurrencyService(db)

    @router.post("/bitcoin")
    async def bitcoin_webhook(request: Request):
        """Handle BlockCypher on-chain notifications for deposit addresses.

        - Verifies the HMAC signature from BlockCypher.
        - Matches the confirmed transaction to a pending BTC deposit by address.
        - Credits Sugar Tokens + bonus Game Credits once confirmations are met.
        """
        body = await request.body()

        # Header names differ between BlockCypher webhook delivery modes.
        event_token = request.headers.get("X-EventToken", "")
        sec_token = request.headers.get("X-EventToken-Secondary", "")

        # Basic sanity: a fully unauthenticated webhook hit with no token and
        # no usable payload is ignored rather than trusted.
        if not event_token:
            logger.warning("Bitcoin webhook received without event token; ignoring.")
            return {"status": "ignored", "reason": "missing_signature"}

        if not btc_processor.verify_webhook_signature(body, event_token, sec_token):
            logger.warning("Bitcoin webhook signature verification failed.")
            raise HTTPException(status_code=401, detail="Invalid signature")

        try:
            data = await request.json()
        except Exception:
            data = {}

        event_type = data.get("event") or "tx-confirmation"
        address = data.get("address") or ""
        tx_hash = data.get("hash") or ""
        confirmations = int(data.get("confirmations") or 0)

        if not address:
            return {"status": "ignored", "reason": "no_address"}

        # Skip non-final events (e.g. unconfirmed-tx) unless we already saw one.
        if event_type not in ("tx-confirmation", "tx-confidence", "confirmed-tx"):
            return {"status": "ignored", "type": event_type}

        deposit = await db.btc_deposits.find_one({"btc_address": address})
        if not deposit:
            # A webhook for an address we don't track — safe to ignore.
            return {"status": "ignored", "reason": "unknown_address"}

        if deposit.get("status") == "completed":
            # Idempotent: already credited. Return OK so BlockCypher stops retrying.
            return {"status": "ok", "already_completed": True}

        required = btc_processor.MIN_CONFIRMATIONS
        await db.btc_deposits.update_one(
            {"_id": deposit["_id"]},
            {"$set": {"confirmations": confirmations, "tx_hash": tx_hash, "event_type": event_type}},
        )

        if confirmations < required:
            return {"status": "pending", "confirmations": confirmations, "required": required}

        deposit_id = deposit.get("id")
        ok, msg = await currency_service.complete_btc_purchase(
            deposit_id=deposit_id,
            tx_hash=tx_hash,
            confirmations=confirmations,
        )
        if not ok:
            logger.error("Failed to complete BTC purchase for deposit %s: %s", deposit_id, msg)
            raise HTTPException(status_code=500, detail=msg)

        return {"status": "ok", "deposit_id": deposit_id, "tx_hash": tx_hash}

    return router
