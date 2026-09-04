"""Crypto (Bitcoin) money-path routes.

Provides the user-facing endpoints the frontend expects:
- GET  /games                  -> active game list
- GET  /payment/crypto-info    -> deposit info (BTC + Lightning display)
- POST /checkout/create        -> start a pending BTC deposit
- GET  /checkout/status/{id}   -> poll a deposit's on-chain status
- POST /redemption/request     -> request Game Credit -> BTC payout

Mounted under the shared /api prefix in server.py.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from config.currency_config import (
    MIN_PURCHASE_USD,
    MAX_PURCHASE_USD_PER_DAY,
    MAX_PURCHASE_USD_PER_HOUR,
)
from models.payment_models import CheckoutCreateRequest, GamePayload, RedemptionRequestPayload
from services import btc_processor
from services.currency_service import CurrencyService

# Public base URL of the API — used for outbound webhook callback URLs.
# Defaults to the Cloudflare proxy domain; override with PUBLIC_API_URL.
PUBLIC_API_URL = (os.getenv("PUBLIC_API_URL") or "https://api.wah-lah.com").rstrip("/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_payment_router(db, get_current_user, get_admin_user) -> APIRouter:
    router = APIRouter(tags=["payment"])
    currency_service = CurrencyService(db)

    # ------------------------------------------------------------------
    # Games
    # ------------------------------------------------------------------
    @router.get("/games")
    async def list_games(request: Request):
        """Return all active games (matching frontend's GameResponse shape)."""
        games = await db.games.find({"is_active": True}).to_list(length=100)
        return [_game_doc(g) for g in games]

    # ------------------------------------------------------------------
    # Admin: game CRUD (drives the frontend's admin "Games" tab)
    # ------------------------------------------------------------------
    def _game_doc(g) -> dict:
        return {
            "id": str(g.get("_id")),
            "name": g.get("name", ""),
            "logo_url": g.get("logo_url", ""),
            "game_url": g.get("game_url", ""),
            "description": g.get("description", ""),
            "is_active": g.get("is_active", True),
            "accent_color": g.get("accent_color", "#ff00ff"),
            "created_at": g.get("created_at", ""),
        }

    @router.get("/games/all")
    async def list_all_games(request: Request):
        """Admin: return every game (active + inactive) for management."""
        await get_admin_user(request)
        games = await db.games.find().to_list(length=200)
        return [_game_doc(g) for g in games]

    @router.post("/games")
    async def create_game(payload: GamePayload, request: Request):
        """Admin: add a new game card."""
        await get_admin_user(request)
        doc = {
            **payload.model_dump(),
            "created_at": _now_iso(),
        }
        result = await db.games.insert_one(doc)
        return {"ok": True, "id": str(result.inserted_id)}

    @router.put("/games/{game_id}")
    async def update_game(game_id: str, payload: GamePayload, request: Request):
        """Admin: edit an existing game card."""
        await get_admin_user(request)
        update = {
            k: v
            for k, v in payload.model_dump().items()
            if k != "created_at"
        }
        result = await db.games.update_one(
            {"_id": ObjectId(game_id)}, {"$set": update}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Game not found")
        return {"ok": True, "id": game_id}

    @router.delete("/games/{game_id}")
    async def delete_game(game_id: str, request: Request):
        """Admin: remove a game card."""
        await get_admin_user(request)
        result = await db.games.delete_one({"_id": ObjectId(game_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Game not found")
        return {"ok": True, "id": game_id}

    # ------------------------------------------------------------------
    # Payment info
    # ------------------------------------------------------------------
    @router.get("/payment/crypto-info")
    async def crypto_info():
        """Return display info for the crypto deposit screen.

        The btc_address here is a general receive address; every actual
        checkout mints a fresh per-deposit address via /checkout/create.
        """
        btc_address = ""
        try:
            if btc_processor._has_credentials():
                btc_address = await btc_processor.derive_deposit_address()
        except Exception:
            btc_address = ""
        return {
            "btc_address": btc_address,
            "lightning_address": "",
            "payby": "bitcoin",
            "enabled": True,
        }

    @router.get("/payment/card-info")
    async def card_info():
        """Legacy card-payment stub. Card on-ramps are not offered; payout is
        Bitcoin only. Returns an empty tag so the UI does not render a card box."""
        return {"tag": "", "enabled": False}

    # ------------------------------------------------------------------
    # Checkout (deposit) flow
    # ------------------------------------------------------------------
    @router.post("/checkout/create")
    async def checkout_create(payload: CheckoutCreateRequest, request: Request):
        user = await get_current_user(request)
        user_id = user.get("id")
        user_email = user.get("email", "")

        method = (payload.payment_method or "bitcoin").lower()
        if method != "bitcoin":
            raise HTTPException(
                status_code=400,
                detail="Only Bitcoin (BTC) deposits are currently supported.",
            )

        amount = payload.amount_usd
        if amount < MIN_PURCHASE_USD:
            raise HTTPException(
                status_code=400,
                detail=f"Minimum deposit is ${MIN_PURCHASE_USD:,.2f}.",
            )

        # Daily / hourly caps (compliance guard against heavy/fast spending).
        since_day = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        since_hour = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        daily = sum(
            float(d.get("amount_usd") or 0)
            for d in await db.btc_deposits.find(
                {"user_id": user_id, "created_at": {"$gte": since_day}}
            ).to_list(length=500)
        )
        hourly = sum(
            float(d.get("amount_usd") or 0)
            for d in await db.btc_deposits.find(
                {"user_id": user_id, "created_at": {"$gte": since_hour}}
            ).to_list(length=500)
        )
        if daily + amount > MAX_PURCHASE_USD_PER_DAY:
            raise HTTPException(
                status_code=400,
                detail=f"You've reached the daily deposit limit (${MAX_PURCHASE_USD_PER_DAY:,.2f}).",
            )
        if hourly + amount > MAX_PURCHASE_USD_PER_HOUR:
            raise HTTPException(
                status_code=400,
                detail=f"You've reached the hourly deposit limit (${MAX_PURCHASE_USD_PER_HOUR:,.2f}).",
            )

        if not btc_processor._has_credentials():
            raise HTTPException(
                status_code=503,
                detail="Bitcoin deposits are temporarily unavailable. Please contact support.",
            )

        try:
            btc_usd_rate = await btc_processor.get_btc_usd_rate()
            btc_address = await btc_processor.derive_deposit_address()
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Could not reach the Bitcoin network provider.") from exc

        btc_satoshis = btc_processor.usd_to_satoshis(amount, btc_usd_rate)

        # Resolve the funded game: the transfer dispatcher reads deposit.platform.
        # Prefer explicit platform, else the frontend's chosen game id.
        target_platform = payload.platform or payload.game_id

        # Persist a pending deposit + pending purchase (no credits yet).
        success, msg, deposit_id = await currency_service.create_pending_btc_purchase(
            user_id=user_id,
            user_email=user_email,
            amount_usd=amount,
            btc_address=btc_address,
            btc_satoshis=btc_satoshis,
            btc_usd_rate=btc_usd_rate,
            platform=target_platform,
        )
        if not success or not deposit_id:
            raise HTTPException(status_code=500, detail=msg)

        # Subscribe to on-chain confirmations for this deposit address.
        try:
            callback_url = f"{PUBLIC_API_URL}/api/webhooks/bitcoin"
            webhook_id = await btc_processor.create_webhook(btc_address, callback_url)
            if webhook_id:
                await db.btc_deposits.update_one(
                    {"id": deposit_id}, {"$set": {"webhook_id": webhook_id}}
                )
        except Exception:
            # Non-fatal: deposit remains pending; admin can confirm manually.
            pass

        return {
            "deposit_id": deposit_id,
            "btc_address": btc_address,
            "amount_usd": amount,
            "btc_satoshis": btc_satoshis,
            "btc_usd_rate": btc_usd_rate,
            "confirmation_required": btc_processor.MIN_CONFIRMATIONS,
            "status": "pending",
            "url": None,
        }

    @router.get("/checkout/status/{deposit_id}")
    async def checkout_status(deposit_id: str, request: Request):
        user = await get_current_user(request)
        deposit = await db.btc_deposits.find_one({"id": deposit_id})
        if not deposit:
            raise HTTPException(status_code=404, detail="Deposit not found")
        if str(deposit.get("user_id")) != str(user.get("id")):
            raise HTTPException(status_code=403, detail="Not your deposit")
        return {
            "deposit_id": deposit_id,
            "status": deposit.get("status"),
            "confirmations": deposit.get("confirmations", 0),
            "tx_hash": deposit.get("tx_hash"),
            "amount_usd": deposit.get("amount_usd"),
            "btc_address": deposit.get("btc_address"),
            "btc_satoshis": deposit.get("btc_satoshis"),
            "platform": deposit.get("platform"),
            "pool_transfer_status": deposit.get("pool_transfer_status"),
            "pool_transfer_message": deposit.get("pool_transfer_message"),
        }

    # ------------------------------------------------------------------
    # Redemption flow (Game Credits -> Bitcoin)
    # ------------------------------------------------------------------
    @router.post("/redemption/request")
    async def redemption_request(payload: RedemptionRequestPayload, request: Request):
        user = await get_current_user(request)
        user_id = user.get("id")
        user_email = user.get("email", "")

        # Geoblock + OFAC compliance before allowing a withdrawal.
        try:
            from services.compliance.geoblock import check_geoblock, client_ip_from_request
            from services.compliance.ofac import check_btc_address, record_ofac_hit
        except Exception:
            check_geoblock = None
            client_ip_from_request = None
            check_btc_address = None
            record_ofac_hit = None

        if client_ip_from_request and check_geoblock:
            ip = client_ip_from_request(request)
            geo_ok, geo_reason = check_geoblock(ip)
            if not geo_ok:
                raise HTTPException(status_code=403, detail=geo_reason or "Region not supported.")

        if check_btc_address:
            addr_ok, addr_reason = check_btc_address(payload.btc_address)
            if not addr_ok:
                if record_ofac_hit:
                    await record_ofac_hit(
                        db, user_id=user_id, btc_address=payload.btc_address, context="redemption"
                    )
                raise HTTPException(status_code=403, detail=addr_reason or "Payout address not allowed.")

        success, msg, redemption_id = await currency_service.create_redemption_request(
            user_id=user_id,
            user_email=user_email,
            game_credits=payload.game_credits,
            btc_address=payload.btc_address,
        )
        if not success:
            raise HTTPException(status_code=400, detail=msg)

        return {
            "ok": True,
            "message": msg,
            "redemption_id": redemption_id,
            "amount_usd": round(payload.game_credits / 100.0, 2),
        }

    return router
