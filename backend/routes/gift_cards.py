"""
Gift Card Redemption + Pilot Launch Checklist router.

Gift card flow (P0 launch path, safer than BTC):
  1. User picks brand + amount + recipient email in the Redeem tab.
  2. POST /api/giftcard/request creates a `gift_card_redemptions` doc (status=pending),
     debits `game_credits` atomically, and queues for admin review.
  3. Admin reviews in the admin panel, pastes the gift-card code, clicks Fulfill.
  4. (Future) Tremendous/Tango API auto-fulfills instead of manual paste.

Launch checklist (P0 pre-flight):
  GET /api/ext/launch-checklist returns a JSON array of gates with status+hint.
"""
from __future__ import annotations

import os
import uuid
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field, conint

logger = logging.getLogger(__name__)

SUPPORTED_BRANDS = {
    "amazon":   {"label": "Amazon",     "min": 5,  "max": 500},
    "visa":     {"label": "Visa",       "min": 10, "max": 500},
    "xbox":     {"label": "Xbox",       "min": 5,  "max": 500},
    "roblox":   {"label": "Roblox",     "min": 5,  "max": 200},
    "doordash": {"label": "DoorDash",   "min": 10, "max": 500},
    "spotify":  {"label": "Spotify",    "min": 10, "max": 100},
    "walmart":  {"label": "Walmart",    "min": 5,  "max": 500},
    "google_play": {"label": "Google Play", "min": 5,  "max": 500},
}


class GiftCardRequestIn(BaseModel):
    brand: str
    amount_credits: conint(gt=0)                    # credits 1:1 USD
    recipient_email: EmailStr
    game_id: Optional[str] = None                   # which game platform credits are pulled from


class FulfillIn(BaseModel):
    code: str = Field(min_length=3, max_length=200)
    notes: Optional[str] = None


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


def build_giftcard_router(db, get_current_user, get_admin_user):
    router = APIRouter(prefix="/api", tags=["gift-cards"])

    # ---- USER ENDPOINTS ----
    @router.get("/giftcard/catalog")
    async def giftcard_catalog():
        """Public catalog of supported brands + min/max per-card caps + house fee disclosure."""
        from services.revenue import get_rates
        rates = await get_rates(db)
        return {
            "brands": [{"id": k, **v} for k, v in SUPPORTED_BRANDS.items()],
            "fee_rate": rates["giftcard"],
            "fee_disclosure": (
                f"A {int(rates['giftcard']*100)}% processing fee is applied to gift card "
                f"redemptions. Example: redeeming 25 credits delivers a "
                f"${round(25 * (1 - rates['giftcard']), 2)} gift card."
            ),
        }

    @router.post("/giftcard/request")
    async def giftcard_request(payload: GiftCardRequestIn, user=Depends(get_current_user)):
        # Feature-flag gate
        from services.feature_flags import get_flag
        if not await get_flag(db, "giftcard_redemption_enabled"):
            raise HTTPException(status_code=503, detail="Gift card redemptions are currently disabled.")

        brand_cfg = SUPPORTED_BRANDS.get(payload.brand)
        if not brand_cfg:
            raise HTTPException(status_code=400, detail=f"Unsupported brand. Pick: {', '.join(SUPPORTED_BRANDS)}")

        amount = int(payload.amount_credits)
        if amount < brand_cfg["min"]:
            raise HTTPException(status_code=400, detail=f"Minimum for {brand_cfg['label']} is ${brand_cfg['min']}")
        if amount > brand_cfg["max"]:
            raise HTTPException(status_code=400, detail=f"Maximum for {brand_cfg['label']} is ${brand_cfg['max']}")

        # Compliance check — same thresholds as BTC path.
        # KYC-basic required at >= $500 cumulative (per-card max is already $500).
        KYC_THRESHOLD = int(os.environ.get("KYC_BASIC_THRESHOLD_USD", "500"))
        if amount >= KYC_THRESHOLD:
            kyc_tier = (user.get("kyc", {}) or {}).get("tier")
            if kyc_tier != "basic" and kyc_tier != "enhanced":
                raise HTTPException(
                    status_code=402,
                    detail={
                        "required_tier": "basic",
                        "threshold_usd": KYC_THRESHOLD,
                        "message": f"Gift cards of ${KYC_THRESHOLD}+ require Basic KYC. Upload ID to continue.",
                    },
                )

        # Atomic credit debit — conditional update so concurrent requests can't double-spend.
        from bson import ObjectId
        uid = user.get("_id") or user.get("id")
        try:
            uid_q = ObjectId(uid) if not isinstance(uid, ObjectId) else uid
        except Exception:
            uid_q = uid
            
        # Playthrough check: Cannot redeem credits that are locked by a playthrough requirement
        playthrough_bal = user.get("playthrough_balance", 0.0)
        if (user.get("game_credits", 0.0) - playthrough_bal) < amount:
            raise HTTPException(status_code=400, detail=f"Insufficient redeemable credits. Remaining playthrough: ${playthrough_bal:.2f}")

        res = await db.users.update_one(
            {"_id": uid_q, "game_credits": {"$gte": amount + playthrough_bal}},
            {"$inc": {"game_credits": -amount}},
        )
        if res.modified_count == 0:
            raise HTTPException(status_code=400, detail="Insufficient game credits.")

        # ---------- HOUSE FEE ----------
        # Player redeems `amount` credits; we deliver a gift card worth
        # `net_usd` and keep `fee_usd` as house revenue.
        from services.revenue import get_rates, apply_fee, record_revenue
        rates = await get_rates(db)
        split = apply_fee(amount, rates["giftcard"])
        net_usd = split["net_usd"]
        fee_usd = split["fee_usd"]

        rid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": rid,
            "user_id": str(uid),
            "user_email": user.get("email"),
            "brand": payload.brand,
            "brand_label": brand_cfg["label"],
            "amount_usd": net_usd,                       # ← amount the player actually receives
            "amount_credits": amount,                    # ← credits debited
            "gross_usd": amount,                         # for ledger reconciliation
            "fee_usd": fee_usd,
            "fee_rate": rates["giftcard"],
            "recipient_email": payload.recipient_email,
            "game_id": payload.game_id,
            "status": "pending",             # pending → fulfilled | rejected
            "created_at": now,
            "fulfilled_at": None,
            "fulfilled_by": None,
            "code": None,
            "notes": None,
        }
        await db.gift_card_redemptions.insert_one(doc)

        # Revenue ledger entry
        await record_revenue(
            db,
            kind="giftcard",
            user_id=str(uid),
            gross_usd=amount,
            fee_usd=fee_usd,
            net_usd=net_usd,
            rate=rates["giftcard"],
            ref_id=rid,
            ref_kind="gift_card",
            metadata={"brand": payload.brand, "recipient_email": payload.recipient_email},
        )

        # AML tracking — log just like BTC path
        try:
            await db.aml_events.insert_one({
                "event": "giftcard_request",
                "user_id": str(uid),
                "amount_usd": amount,
                "brand": payload.brand,
                "created_at": now,
            })
        except Exception:
            pass

        # Admin alert
        await db.admin_alerts.insert_one({
            "id": str(uuid.uuid4()),
            "type": "gift_card_pending",
            "severity": "info",
            "title": f"{brand_cfg['label']} ${amount} gift card requested",
            "message": f"{user.get('email')} → {payload.recipient_email}",
            "resolved": False,
            "ref_id": rid,
            "created_at": now,
        })

        doc.pop("_id", None)
        return doc

    @router.get("/giftcard/my-requests")
    async def my_giftcard_requests(user=Depends(get_current_user)):
        items = await db.gift_card_redemptions.find(
            {"user_id": str(user.get("_id") or user.get("id"))},
            {"_id": 0, "code": 0},                # never leak the code in list view
        ).sort("created_at", -1).limit(50).to_list(length=50)
        return items

    @router.get("/giftcard/my-requests/{rid}")
    async def my_giftcard_detail(rid: str, user=Depends(get_current_user)):
        doc = await db.gift_card_redemptions.find_one(
            {"id": rid, "user_id": str(user.get("_id") or user.get("id"))},
            {"_id": 0},
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        # Only reveal the code once fulfilled
        if doc.get("status") != "fulfilled":
            doc["code"] = None
        return doc

    # ---- ADMIN ENDPOINTS ----
    @router.get("/ext/giftcard/admin/pending")
    async def admin_pending(_=Depends(get_admin_user)):
        items = await db.gift_card_redemptions.find(
            {"status": "pending"},
            {"_id": 0},
        ).sort("created_at", -1).limit(200).to_list(length=200)
        return items

    @router.get("/ext/giftcard/admin/all")
    async def admin_all(status: Optional[str] = None, _=Depends(get_admin_user)):
        query = {}
        if status:
            query["status"] = status
        items = await db.gift_card_redemptions.find(query, {"_id": 0}).sort("created_at", -1).limit(300).to_list(length=300)
        return items

    @router.post("/ext/giftcard/admin/fulfill/{rid}")
    async def admin_fulfill(rid: str, payload: FulfillIn, admin=Depends(get_admin_user)):
        doc = await db.gift_card_redemptions.find_one({"id": rid})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        if doc.get("status") != "pending":
            raise HTTPException(status_code=400, detail=f"Already {doc.get('status')}")
        now = datetime.now(timezone.utc).isoformat()
        await db.gift_card_redemptions.update_one(
            {"id": rid},
            {"$set": {
                "status": "fulfilled",
                "code": payload.code,
                "notes": payload.notes,
                "fulfilled_at": now,
                "fulfilled_by": admin.get("email"),
            }},
        )
        # Resolve the alert
        await db.admin_alerts.update_one(
            {"ref_id": rid},
            {"$set": {"resolved": True, "resolved_at": now, "resolved_by": admin.get("email")}},
        )
        # Email the user via Resend (best-effort — no-op if not configured)
        try:
            from services.email_service import EmailService
            EmailService().send_email(
                to_email=doc["user_email"],
                subject=f"Your {doc['brand_label']} gift card is ready",
                html_content=(
                    f"<h2>WAH-LAH</h2>"
                    f"<p>Your ${doc['amount_usd']} {doc['brand_label']} gift card is ready.</p>"
                    f"<p><strong>Code:</strong> <code>{payload.code}</code></p>"
                    f"<p>Enjoy, Boss.</p>"
                ),
            )
        except Exception as e:
            logger.info("giftcard email skipped: %s", e)
        return {"ok": True, "id": rid, "status": "fulfilled"}

    @router.post("/ext/giftcard/admin/reject/{rid}")
    async def admin_reject(rid: str, payload: RejectIn, admin=Depends(get_admin_user)):
        doc = await db.gift_card_redemptions.find_one({"id": rid})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        if doc.get("status") != "pending":
            raise HTTPException(status_code=400, detail=f"Already {doc.get('status')}")
        now = datetime.now(timezone.utc).isoformat()
        # Refund credits back to the user
        from bson import ObjectId
        try:
            uid_q = ObjectId(doc["user_id"])
        except Exception:
            uid_q = doc["user_id"]
        await db.users.update_one(
            {"_id": uid_q},
            {"$inc": {"game_credits": int(doc["amount_credits"])}},
        )
        await db.gift_card_redemptions.update_one(
            {"id": rid},
            {"$set": {
                "status": "rejected",
                "notes": payload.reason,
                "fulfilled_at": now,
                "fulfilled_by": admin.get("email"),
            }},
        )
        await db.admin_alerts.update_one(
            {"ref_id": rid},
            {"$set": {"resolved": True, "resolved_at": now, "resolved_by": admin.get("email")}},
        )
        return {"ok": True, "id": rid, "status": "rejected", "refunded_credits": int(doc["amount_credits"])}

    # ---- LAUNCH CHECKLIST ----
    @router.get("/ext/launch-checklist")
    async def launch_checklist(_=Depends(get_admin_user)):
        """
        Six pre-flight gates for going live. Each returns:
          { key, label, status: 'pass'|'warn'|'fail', detail }
        """
        checks: List[dict] = []

        # 1) Stripe
        sk = os.environ.get("STRIPE_API_KEY", "")
        pk = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
        stripe_live = sk.startswith(("sk_live_", "rk_live_"))
        stripe_placeholder = "placeholder" in sk.lower() or not sk or not pk
        checks.append({
            "key": "stripe",
            "label": "Stripe API key",
            "status": "fail" if stripe_placeholder else ("pass" if stripe_live else "warn"),
            "detail": "LIVE key configured" if stripe_live else (
                "placeholder or missing PK/SK in .env — replace before launch" if stripe_placeholder else
                "test-mode key detected (OK for staging)"
            ),
        })

        # 2) Games healthy — all have logo_url and accent_color
        games = await db.games.find({"is_active": True}, {"_id": 0}).to_list(length=50)
        missing = [g.get("name") for g in games if not g.get("logo_url") or not g.get("accent_color")]
        checks.append({
            "key": "games",
            "label": "Games healthy (logo + color)",
            "status": "pass" if not missing else "warn",
            "detail": f"{len(games)} games active"
                      + (f" · {len(missing)} need assets: {', '.join(missing)}" if missing else ""),
        })

        # 3) Distributor pool — at least 2 active proxies
        try:
            active = await db.distributor_proxies.count_documents({"status": "active"})
            total = await db.distributor_proxies.count_documents({})
            checks.append({
                "key": "pool",
                "label": "Distributor pool (≥2 active)",
                "status": "pass" if active >= 2 else ("warn" if active == 1 else "fail"),
                "detail": f"{active} active / {total} total",
            })
        except Exception as e:
            checks.append({"key": "pool", "label": "Distributor pool", "status": "warn", "detail": str(e)})

        # 4) Admin alerts clean (no unresolved critical in last 24h)
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            unresolved = await db.admin_alerts.count_documents({
                "resolved": False,
                "severity": {"$in": ["critical", "error"]},
                "created_at": {"$gte": cutoff},
            })
            checks.append({
                "key": "alerts",
                "label": "No critical alerts (24h)",
                "status": "pass" if unresolved == 0 else "warn",
                "detail": f"{unresolved} unresolved critical alerts" if unresolved else "all clear",
            })
        except Exception as e:
            checks.append({"key": "alerts", "label": "Alerts", "status": "warn", "detail": str(e)})

        # 5) Compliance — OFAC list refreshed in last 7d
        try:
            colls = await db.list_collection_names()
            ofac_meta = await db.ofac_refreshes.find_one(sort=[("refreshed_at", -1)]) if \
                "ofac_refreshes" in colls else None
            if ofac_meta:
                age_ok = ofac_meta["refreshed_at"] > (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                checks.append({
                    "key": "compliance",
                    "label": "OFAC SDN list fresh (<7d)",
                    "status": "pass" if age_ok else "warn",
                    "detail": f"last refresh {ofac_meta['refreshed_at']}",
                })
            else:
                checks.append({
                    "key": "compliance",
                    "label": "OFAC SDN list fresh (<7d)",
                    "status": "warn",
                    "detail": "no refresh recorded — hit the Refresh button in Compliance tab",
                })
        except Exception as e:
            checks.append({"key": "compliance", "label": "Compliance", "status": "warn", "detail": str(e)})

        # 6) At least one redemption path enabled
        try:
            from services.feature_flags import get_flags
            flags = await get_flags(db)
            btc_on = bool(flags.get("btc_payouts_enabled"))
            gc_on = bool(flags.get("giftcard_redemption_enabled"))
            paths = []
            if btc_on:
                paths.append("BTC")
            if gc_on:
                paths.append("Gift Cards")
            checks.append({
                "key": "redemption_path",
                "label": "Redemption path available",
                "status": "pass" if paths else "fail",
                "detail": f"active: {' + '.join(paths)}" if paths else "both BTC and Gift Cards are OFF — users can't cash out",
            })
        except Exception as e:
            checks.append({"key": "redemption_path", "label": "Redemption path", "status": "warn", "detail": str(e)})

        # 7) Playwright Environment Check
        try:
            pw_check = subprocess.run(["playwright", "--version"], capture_output=True)
            checks.append({
                "key": "playwright",
                "label": "Playwright Environment",
                "status": "pass" if pw_check.returncode == 0 else "fail",
                "detail": "CLI ready" if pw_check.returncode == 0 else "CLI missing - run install script",
            })
        except Exception:
            checks.append({
                "key": "playwright",
                "label": "Playwright Environment",
                "status": "fail",
                "detail": "Package missing"
            })

        # 8) Stripe Webhook Secret Check
        whsec = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        whsec_present = whsec.startswith("whsec_")
        checks.append({
            "key": "stripe_webhook",
            "label": "Stripe Webhook Secret",
            "status": "pass" if whsec_present else "fail",
            "detail": "whsec_ configured" if whsec_present else "Missing whsec_ key. Webhook signature verification will fail."
        })

        fails = [c for c in checks if c["status"] == "fail"]
        warns = [c for c in checks if c["status"] == "warn"]
        summary = {
            # Site is only ready if all critical gates (fails) are clear.
            "ready": len(fails) == 0,
            "total": len(checks),
            "passing": sum(1 for c in checks if c["status"] == "pass"),
            "warning": len(warns),
            "failing": len(fails),
            "banner": (
                "READY FOR LIVE TRAFFIC" if not fails and not warns
                else "LAUNCH WITH CAUTION" if not fails
                else "DO NOT LAUNCH"
            ),
        }
        return {"summary": summary, "checks": checks, "at": datetime.now(timezone.utc).isoformat()}

    return router
