"""Compliance routes — KYC, OFAC, Geoblock, AML, BTC Payout Hold Queue."""
from __future__ import annotations

import logging
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from services.compliance import (
    KYC_BASIC_THRESHOLD_USD,
    KYC_ENHANCED_THRESHOLD_USD,
    CTR_THRESHOLD_USD,
    PERSONA_ENABLED,
    check_btc_address,
    check_geoblock,
    get_user_kyc_status,
    list_blocked_states,
    load_sdn_list,
    persona_client,
    record_aml_event,
    required_kyc_tier,
)
from services.compliance.geoblock import client_ip_from_request, record_geoblock_event
from services.compliance.kyc import TIER_BASIC, TIER_ENHANCED, upsert_kyc_profile
from services.compliance.ofac import record_ofac_hit

logger = logging.getLogger(__name__)

# ---- upload dir for manual KYC docs ----
KYC_UPLOAD_DIR = Path(os.environ.get("KYC_UPLOAD_DIR", "/tmp/sugar_kyc_uploads"))
KYC_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB


# Pydantic payloads — hoisted out of build_compliance_router so FastAPI can resolve them.
class KycInitiatePayload(BaseModel):
    tier: str  # "basic" | "enhanced"


class KycDecisionPayload(BaseModel):
    user_id: str
    tier: str
    decision: str  # approve | reject
    notes: Optional[str] = None


class PayoutActionPayload(BaseModel):
    redemption_id: str
    action: str  # approve | reject
    notes: Optional[str] = None


class FlagPayload(BaseModel):
    key: str
    value: Any


def build_compliance_router(db, get_current_user, admin_required) -> APIRouter:
    router = APIRouter(prefix="/api/ext/compliance", tags=["compliance"])

    # ====================================================================
    # User-facing: KYC initiate / status / upload
    # ====================================================================

    @router.post("/kyc/initiate")
    async def kyc_initiate(payload: KycInitiatePayload, request: Request):
        user = await get_current_user(request)
        if payload.tier not in (TIER_BASIC, TIER_ENHANCED):
            raise HTTPException(status_code=400, detail="tier must be 'basic' or 'enhanced'")

        existing = await get_user_kyc_status(db, user["id"], payload.tier)
        if existing.get("status") == "approved":
            return {"status": "approved", "message": "Already approved at this tier."}

        # Prefer Persona if enabled.
        if PERSONA_ENABLED:
            frontend = os.environ.get("FRONTEND_URL", "")
            redirect_url = f"{frontend}/redemption/kyc-return" if frontend else None
            result = await persona_client.create_inquiry(
                user_id=user["id"], tier=payload.tier, redirect_url=redirect_url
            )
            if not result.get("fallback") and result.get("hosted_inquiry_url"):
                await upsert_kyc_profile(
                    db,
                    user_id=user["id"],
                    tier=payload.tier,
                    status="pending",
                    method="persona",
                    inquiry_id=result["inquiry_id"],
                )
                # Store reference_id → user_id map for webhook correlation
                await db["kyc_persona_refs"].update_one(
                    {"reference_id": result["reference_id"]},
                    {"$set": {
                        "reference_id": result["reference_id"],
                        "inquiry_id": result["inquiry_id"],
                        "user_id": user["id"],
                        "tier": payload.tier,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }},
                    upsert=True,
                )
                return {
                    "method": "persona",
                    "status": "pending",
                    "hosted_inquiry_url": result["hosted_inquiry_url"],
                    "inquiry_id": result["inquiry_id"],
                }

        # Fallback: manual upload.
        await upsert_kyc_profile(
            db,
            user_id=user["id"],
            tier=payload.tier,
            status="pending",
            method="manual_upload",
        )
        return {
            "method": "manual_upload",
            "status": "pending",
            "message": "Persona unavailable — upload ID + selfie via /kyc/upload.",
            "upload_endpoint": "/api/ext/compliance/kyc/upload",
        }

    @router.post("/kyc/upload")
    async def kyc_upload(
        request: Request,
        tier: str = Form(...),
        doc_type: str = Form("id_front"),  # id_front | id_back | selfie | proof_of_address
        file: UploadFile = File(...),
    ):
        user = await get_current_user(request)
        if tier not in (TIER_BASIC, TIER_ENHANCED):
            raise HTTPException(status_code=400, detail="tier must be 'basic' or 'enhanced'")
        if file.content_type not in ALLOWED_MIME:
            raise HTTPException(status_code=415, detail=f"mime {file.content_type} not allowed")
        body = await file.read()
        if len(body) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="file too large (max 10MB)")
        doc_id = uuid.uuid4().hex
        ext = (file.filename or "bin").split(".")[-1][:8]
        path = KYC_UPLOAD_DIR / f"{user['id']}_{tier}_{doc_type}_{doc_id}.{ext}"
        path.write_bytes(body)
        await db["kyc_uploads"].insert_one({
            "doc_id": doc_id,
            "user_id": user["id"],
            "tier": tier,
            "doc_type": doc_type,
            "mime": file.content_type,
            "size_bytes": len(body),
            "storage_path": str(path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        # Move profile to 'review' so admin queue picks it up.
        await upsert_kyc_profile(
            db,
            user_id=user["id"],
            tier=tier,
            status="review",
            method="manual_upload",
            uploaded_doc_id=doc_id,
        )
        return {"uploaded": True, "doc_id": doc_id, "status": "review"}

    @router.get("/kyc/status")
    async def kyc_status(request: Request, tier: str = TIER_BASIC):
        user = await get_current_user(request)
        doc = await get_user_kyc_status(db, user["id"], tier)
        # Never leak reviewer_notes to the user.
        doc.pop("reviewer_notes", None)
        return doc

    # ====================================================================
    # Persona webhook
    # ====================================================================

    @router.post("/persona/webhook")
    async def persona_webhook(request: Request):
        raw = await request.body()
        sig = request.headers.get("persona-signature") or request.headers.get("Persona-Signature") or ""
        if not persona_client.verify_webhook_signature(raw, sig):
            raise HTTPException(status_code=403, detail="invalid signature")
        payload = json.loads(raw or b"{}")
        event = payload.get("data", {}).get("attributes", {}).get("name") or payload.get("type")
        inquiry = payload.get("data", {}).get("attributes", {}).get("payload", {}).get("data", {})
        inquiry_id = inquiry.get("id") or payload.get("data", {}).get("id")
        attrs = (inquiry.get("attributes") or {})
        reference_id = attrs.get("reference-id") or payload.get("data", {}).get("attributes", {}).get("reference-id")
        status_map = {
            "inquiry.approved": "approved",
            "inquiry.declined": "declined",
            "inquiry.marked-for-review": "review",
            "inquiry.completed": "review",  # officer decides
        }
        new_status = status_map.get(event or "", "review")
        ref_doc = await db["kyc_persona_refs"].find_one({"reference_id": reference_id}) if reference_id else None
        if not ref_doc:
            logger.warning(f"Persona webhook: unknown reference_id={reference_id} event={event}")
            return {"received": True, "action": "unknown_reference"}
        # Fetch full inquiry for extracted fields.
        full = await persona_client.fetch_inquiry(inquiry_id) if inquiry_id else None
        extracted = None
        if full:
            a = full.get("attributes") or {}
            extracted = {
                "name_first": a.get("name-first"),
                "name_last": a.get("name-last"),
                "birthdate": a.get("birthdate"),
                "address_country": a.get("address-country-code"),
            }
        await upsert_kyc_profile(
            db,
            user_id=ref_doc["user_id"],
            tier=ref_doc["tier"],
            status=new_status,
            method="persona",
            inquiry_id=inquiry_id,
            extracted_data=extracted,
        )
        return {"received": True, "new_status": new_status}

    # ====================================================================
    # Admin: KYC review queue
    # ====================================================================

    @router.get("/admin/kyc/queue")
    async def admin_kyc_queue(request: Request):
        await admin_required(request)
        items = await db["kyc_profiles"].find(
            {"status": {"$in": ["pending", "review"]}},
            {"_id": 0},
        ).sort("updated_at", -1).to_list(500)
        # Attach user email for display.
        emails_by_id = {}
        for it in items:
            uid = it.get("user_id")
            if uid and uid not in emails_by_id:
                u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1})
                emails_by_id[uid] = (u or {}).get("email", "?")
            it["user_email"] = emails_by_id.get(uid, "?")
        return items

    @router.get("/admin/kyc/{user_id}/{tier}/uploads")
    async def admin_kyc_uploads(user_id: str, tier: str, request: Request):
        await admin_required(request)
        docs = await db["kyc_uploads"].find(
            {"user_id": user_id, "tier": tier}, {"_id": 0, "storage_path": 0}
        ).sort("created_at", -1).to_list(50)
        return docs

    @router.post("/admin/kyc/decide")
    async def admin_kyc_decide(payload: KycDecisionPayload, request: Request):
        admin = await admin_required(request)
        if payload.decision not in ("approve", "reject"):
            raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")
        new_status = "approved" if payload.decision == "approve" else "declined"
        await upsert_kyc_profile(
            db,
            user_id=payload.user_id,
            tier=payload.tier,
            status=new_status,
            method="admin_granted",
            actor_id=admin.get("id") or admin.get("email"),
            reviewer_notes=payload.notes,
        )
        await record_aml_event(
            db,
            user_id=payload.user_id,
            event_type="kyc_decision",
            amount_usd=0.0,
            metadata={"tier": payload.tier, "decision": new_status, "actor": admin.get("email")},
        )
        return {"ok": True, "status": new_status}

    # ====================================================================
    # Admin: BTC payout hold queue
    # ====================================================================

    @router.get("/admin/payouts/queue")
    async def admin_payout_queue(request: Request):
        await admin_required(request)
        items = await db["redemption_requests"].find(
            {"status": {"$in": ["hold_admin_review", "pending", "approved"]}},
        ).sort("created_at", -1).to_list(200)
        for it in items:
            it["id"] = str(it.pop("_id"))
        return items

    @router.post("/admin/payouts/action")
    async def admin_payout_action(payload: PayoutActionPayload, request: Request):
        admin = await admin_required(request)
        if payload.action not in ("approve", "reject"):
            raise HTTPException(status_code=400, detail="action must be approve/reject")
        rec = await db["redemption_requests"].find_one({"_id": ObjectId(payload.redemption_id)})
        if not rec:
            raise HTTPException(status_code=404, detail="redemption not found")
        now = datetime.now(timezone.utc).isoformat()
        new_status = "approved" if payload.action == "approve" else "rejected"
        update = {
            "status": new_status,
            "reviewer_id": admin.get("id") or admin.get("email"),
            "reviewer_notes": payload.notes,
            "decided_at": now,
        }
        # Actual BTC send happens via middleware PayoutEngine on approval;
        # we call it below. Keep the redemption row authoritative for state.
        if payload.action == "approve":
            # Defer import to avoid circulars.
            try:
                from server import middleware_manager  # type: ignore
                amount_usd = float(rec.get("amount_usd") or 0)
                btc_address = rec.get("btc_address")
                ok, msg, payout_id = False, "payout_engine_unavailable", None
                if middleware_manager and middleware_manager.payout_engine and btc_address and amount_usd > 0:
                    ok, msg, payout_id = await middleware_manager.process_withdrawal(
                        user_id=str(rec.get("user_id")),
                        user_email=rec.get("user_email", ""),
                        amount_usd=amount_usd,
                        btc_address=btc_address,
                    )
                update["payout_gateway_result"] = {"ok": ok, "msg": msg, "payout_id": payout_id, "at": now}
                if not ok:
                    update["status"] = "approved_payout_failed"
                else:
                    await record_aml_event(
                        db,
                        user_id=str(rec.get("user_id")),
                        event_type="redemption_paid",
                        amount_usd=amount_usd,
                        metadata={"btc_address": btc_address, "payout_id": payout_id},
                    )
            except Exception as e:
                logger.error(f"Payout execution failed: {e}")
                update["payout_gateway_result"] = {"ok": False, "msg": str(e), "at": now}
                update["status"] = "approved_payout_failed"
        await db["redemption_requests"].update_one({"_id": ObjectId(payload.redemption_id)}, {"$set": update})
        return {"ok": True, "status": update["status"]}

    # ====================================================================
    # Admin: AML / OFAC / Geoblock visibility
    # ====================================================================

    @router.get("/admin/aml/events")
    async def admin_aml_events(request: Request, limit: int = 100):
        await admin_required(request)
        items = await db["aml_events"].find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
        return items

    @router.get("/admin/ofac/hits")
    async def admin_ofac_hits(request: Request, limit: int = 100):
        await admin_required(request)
        items = await db["ofac_hits"].find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
        return items

    @router.post("/admin/ofac/refresh")
    async def admin_ofac_refresh(request: Request):
        await admin_required(request)
        count, source = await load_sdn_list(force=True)
        return {"count": count, "source": source}

    @router.get("/admin/geoblock/config")
    async def admin_geoblock_config(request: Request):
        await admin_required(request)
        return {
            "blocked_states": list_blocked_states(),
            "note": "Edit BLOCKED_STATES env var and restart backend to modify.",
        }

    @router.get("/admin/overview")
    async def admin_overview(request: Request):
        await admin_required(request)
        pending_kyc = await db["kyc_profiles"].count_documents({"status": {"$in": ["pending", "review"]}})
        approved_kyc = await db["kyc_profiles"].count_documents({"status": "approved"})
        declined_kyc = await db["kyc_profiles"].count_documents({"status": "declined"})
        payout_hold = await db["redemption_requests"].count_documents({"status": "hold_admin_review"})
        payout_approved_today = await db["redemption_requests"].count_documents({
            "status": "approved",
            "decided_at": {"$gte": datetime.now(timezone.utc).date().isoformat()},
        })
        open_alerts = await db["admin_alerts"].count_documents({"status": "open"})
        ofac_hits_all = await db["ofac_hits"].count_documents({})
        return {
            "kyc": {"pending_review": pending_kyc, "approved": approved_kyc, "declined": declined_kyc},
            "payouts": {"hold_admin_review": payout_hold, "approved_today": payout_approved_today},
            "alerts": {"open": open_alerts, "ofac_hits_all_time": ofac_hits_all},
            "thresholds": {
                "kyc_basic_usd": KYC_BASIC_THRESHOLD_USD,
                "kyc_enhanced_usd": KYC_ENHANCED_THRESHOLD_USD,
                "ctr_usd": CTR_THRESHOLD_USD,
            },
            "persona_enabled": PERSONA_ENABLED,
            "blocked_states": list_blocked_states(),
        }

    # ====================================================================
    # Feature flags — admin-toggleable master switches
    # ====================================================================
    from services.feature_flags import get_flags as _ff_get, set_flag as _ff_set  # noqa: E402

    @router.get("/admin/feature-flags")
    async def admin_get_flags(request: Request):
        await admin_required(request)
        return await _ff_get(db)

    @router.patch("/admin/feature-flags")
    async def admin_patch_flag(payload: FlagPayload, request: Request):
        admin = await admin_required(request)
        try:
            flags = await _ff_set(db, payload.key, payload.value, actor=admin.get("email"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return flags

    # Public (user-authenticated) read so the frontend can hide/show tabs
    @router.get("/feature-flags")
    async def public_get_flags(request: Request):
        await get_current_user(request)
        # Only expose user-relevant, visibility-oriented flags
        flags = await _ff_get(db)
        return {
            "btc_payouts_enabled": flags.get("btc_payouts_enabled", False),
            "giftcard_redemption_enabled": flags.get("giftcard_redemption_enabled", True),
            "redeem_tab_visible": flags.get("redeem_tab_visible", True),
            "withdraw_tab_visible": flags.get("withdraw_tab_visible", False),
            "maintenance_mode_enabled": flags.get("maintenance_mode_enabled", False),
        }

    return router


__all__ = [
    "build_compliance_router",
    "check_btc_address",
    "check_geoblock",
    "client_ip_from_request",
    "record_geoblock_event",
    "record_ofac_hit",
    "record_aml_event",
    "required_kyc_tier",
    "is_user_cleared_for_wrapper",
]


async def is_user_cleared_for_wrapper(db, user_id: str, amount_usd: float):
    """Re-export for server.py to avoid importing services.compliance.kyc directly."""
    from services.compliance import is_user_cleared_for as _impl
    return await _impl(db, user_id, amount_usd)
