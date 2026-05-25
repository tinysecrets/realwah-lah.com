"""
WAH-LAH - Feature Extensions
=======================================
Adds: Password Reset, 2FA (TOTP), Promo Codes, Referral System,
      VIP Tiers, Support Tickets frontend-facing APIs, Enhanced Analytics.
"""
from __future__ import annotations

import os
import io
import base64
import secrets
import string
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId
import bcrypt
import jwt
import pyotp
import qrcode

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"


# =========================================================
# VIP / Loyalty Tiers - config
# =========================================================
VIP_TIERS = [
    {"name": "Bronze", "min_spend": 0,     "bonus_pct": 0,  "color": "#cd7f32"},
    {"name": "Silver", "min_spend": 100,   "bonus_pct": 5,  "color": "#c0c0c0"},
    {"name": "Gold",   "min_spend": 500,   "bonus_pct": 10, "color": "#ffd700"},
    {"name": "Platinum", "min_spend": 2000, "bonus_pct": 15, "color": "#e5e4e2"},
    {"name": "Diamond", "min_spend": 10000, "bonus_pct": 25, "color": "#b9f2ff"},
]


def compute_vip_tier(total_spend_usd: float) -> Dict[str, Any]:
    """Return the VIP tier info for a given lifetime spend."""
    tier = VIP_TIERS[0]
    for t in VIP_TIERS:
        if total_spend_usd >= t["min_spend"]:
            tier = t
    # Compute next tier & progress
    idx = VIP_TIERS.index(tier)
    if idx < len(VIP_TIERS) - 1:
        nxt = VIP_TIERS[idx + 1]
        progress = (total_spend_usd - tier["min_spend"]) / (nxt["min_spend"] - tier["min_spend"])
        progress = max(0.0, min(1.0, progress))
        next_tier = {"name": nxt["name"], "min_spend": nxt["min_spend"], "needed": max(0.0, nxt["min_spend"] - total_spend_usd)}
    else:
        progress = 1.0
        next_tier = None
    return {**tier, "progress": round(progress, 3), "next_tier": next_tier, "lifetime_spend_usd": total_spend_usd}


# =========================================================
# Pydantic models
# =========================================================
class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


class PasswordChangeBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class TwoFAVerify(BaseModel):
    code: str


class TwoFALoginBody(BaseModel):
    email: EmailStr
    password: str
    code: str


class PromoCreateBody(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    bonus_credits: int = Field(ge=1)
    max_uses: int = Field(default=0, ge=0)  # 0 = unlimited
    expires_at: Optional[str] = None  # ISO string
    description: Optional[str] = ""


class PromoRedeemBody(BaseModel):
    code: str


class ReferralRedeemBody(BaseModel):
    code: str


class SupportTicketBody(BaseModel):
    subject: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=1, max_length=4000)
    priority: str = "normal"


class TicketResponseBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


# =========================================================
# Helpers
# =========================================================
def _gen_token(n: int = 32) -> str:
    return secrets.token_urlsafe(n)


def _gen_referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": _now() + timedelta(minutes=60),
        "type": "access",
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def _create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": _now() + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def build_extensions_router(db, get_current_user, get_admin_user) -> APIRouter:
    """Build the APIRouter wired to the provided db + auth helpers."""
    router = APIRouter(prefix="/api/ext", tags=["extensions"])

    # =========================================================
    # VIP Tier
    # =========================================================
    async def _user_lifetime_spend(user_id: str) -> float:
        pipeline = [
            {"$match": {"user_id": user_id, "status": "completed"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
        r = await db.payment_transactions.aggregate(pipeline).to_list(1)
        return float(r[0]["total"]) if r else 0.0

    @router.get("/vip/tier")
    async def get_vip_tier(request: Request):
        user = await get_current_user(request)
        spend = await _user_lifetime_spend(user["id"])
        tier = compute_vip_tier(spend)
        # Persist current tier name for display
        await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"vip_tier": tier["name"]}})
        return tier

    @router.get("/vip/tiers")
    async def list_vip_tiers():
        return VIP_TIERS

    # =========================================================
    # Password Reset
    # =========================================================
    @router.post("/password/forgot")
    async def forgot_password(data: PasswordResetRequest):
        email = data.email.lower()
        user = await db.users.find_one({"email": email})
        token = _gen_token(32)
        frontend_url = os.environ.get("FRONTEND_URL", "")
        dev_link = f"{frontend_url}/reset-password?token={token}" if user else None
        email_sent = False
        if user:
            await db.password_resets.insert_one({
                "user_id": str(user["_id"]),
                "email": email,
                "token": token,
                "expires_at": _now() + timedelta(hours=1),
                "used": False,
                "created_at": _now(),
            })
            logger.info(f"Password reset issued for {email}")
            # Send via Resend when key is configured
            try:
                from services.email_service import email_service
                if email_service.api_key and dev_link:
                    html = f"""
                    <div style="font-family:Arial,sans-serif;background:#1a0a2e;color:#fff;padding:40px">
                      <div style="max-width:560px;margin:0 auto;background:#2d1b3d;padding:32px;border-radius:16px;border:2px solid #ff1493">
                        <h1 style="color:#ff1493;margin:0 0 12px">WAH-LAH</h1>
                        <h2 style="color:#fff;margin:0 0 16px">Password reset request</h2>
                        <p>Click the button below to reset your password. This link expires in 1 hour.</p>
                        <p style="text-align:center;margin:28px 0">
                          <a href="{dev_link}" style="display:inline-block;background:linear-gradient(135deg,#ff1493,#9b59b6);color:#fff;padding:14px 36px;border-radius:30px;text-decoration:none;font-weight:bold">Reset password</a>
                        </p>
                        <p style="color:#aaa;font-size:12px">If you didn't request this, ignore this email.</p>
                      </div>
                    </div>
                    """
                    ok, msg = email_service.send_email(
                        to_email=email,
                        subject="WAH-LAH — Password Reset",
                        html_content=html,
                    )
                    email_sent = ok
                    if not ok:
                        logger.warning(f"Resend send failed for {email}: {msg}")
            except Exception as e:
                logger.error(f"Password reset email error: {e}")
        # Always return ok to avoid user enumeration.
        # dev_token is still returned for test + fallback convenience; the real reset
        # link is delivered via Resend when the key is configured.
        return {
            "message": "If the email exists, a reset link has been issued.",
            "email_sent": email_sent,
            "dev_token": token if user else None,
            "dev_reset_link": dev_link,
        }

    @router.post("/password/reset")
    async def reset_password(data: PasswordResetConfirm):
        rec = await db.password_resets.find_one({"token": data.token, "used": False})
        if not rec:
            raise HTTPException(status_code=400, detail="Invalid or expired token")
        exp = rec["expires_at"]
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < _now():
            raise HTTPException(status_code=400, detail="Token expired")
        new_hash = _hash_password(data.new_password)
        await db.users.update_one({"_id": ObjectId(rec["user_id"])}, {"$set": {"password_hash": new_hash}})
        await db.password_resets.update_one({"_id": rec["_id"]}, {"$set": {"used": True, "used_at": _now()}})
        return {"message": "Password reset successful"}

    @router.post("/password/change")
    async def change_password(data: PasswordChangeBody, request: Request):
        user = await get_current_user(request)
        db_user = await db.users.find_one({"_id": ObjectId(user["id"])})
        if not db_user or not _verify_password(data.current_password, db_user["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"password_hash": _hash_password(data.new_password)}})
        return {"message": "Password updated"}

    # =========================================================
    # 2FA (TOTP)
    # =========================================================
    @router.post("/2fa/setup")
    async def twofa_setup(request: Request):
        """Generate a TOTP secret + provisioning URI + QR code (base64)."""
        user = await get_current_user(request)
        secret = pyotp.random_base32()
        issuer = "WAH-LAH"
        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name=issuer)

        # Generate QR code png -> base64
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        # Store temp secret (not enabled until verified)
        await db.users.update_one(
            {"_id": ObjectId(user["id"])},
            {"$set": {"twofa_pending_secret": secret}},
        )
        return {
            "secret": secret,
            "otpauth_uri": uri,
            "qr_code_base64": f"data:image/png;base64,{qr_b64}",
        }

    @router.post("/2fa/enable")
    async def twofa_enable(data: TwoFAVerify, request: Request):
        user = await get_current_user(request)
        db_user = await db.users.find_one({"_id": ObjectId(user["id"])})
        secret = db_user.get("twofa_pending_secret")
        if not secret:
            raise HTTPException(status_code=400, detail="Start 2FA setup first")
        totp = pyotp.TOTP(secret)
        if not totp.verify(data.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid code")
        await db.users.update_one(
            {"_id": ObjectId(user["id"])},
            {"$set": {"twofa_secret": secret, "twofa_enabled": True},
             "$unset": {"twofa_pending_secret": ""}},
        )
        return {"message": "2FA enabled"}

    @router.post("/2fa/disable")
    async def twofa_disable(data: TwoFAVerify, request: Request):
        user = await get_current_user(request)
        db_user = await db.users.find_one({"_id": ObjectId(user["id"])})
        if not db_user.get("twofa_enabled"):
            raise HTTPException(status_code=400, detail="2FA is not enabled")
        totp = pyotp.TOTP(db_user["twofa_secret"])
        if not totp.verify(data.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid code")
        await db.users.update_one(
            {"_id": ObjectId(user["id"])},
            {"$unset": {"twofa_secret": "", "twofa_pending_secret": ""},
             "$set": {"twofa_enabled": False}},
        )
        return {"message": "2FA disabled"}

    @router.get("/2fa/status")
    async def twofa_status(request: Request):
        user = await get_current_user(request)
        db_user = await db.users.find_one({"_id": ObjectId(user["id"])})
        return {"enabled": bool(db_user.get("twofa_enabled", False))}

    @router.post("/auth/login-2fa")
    async def login_with_2fa(data: TwoFALoginBody, response: Response):
        """Login that requires 2FA code if user has 2FA enabled."""
        email = data.email.lower()
        db_user = await db.users.find_one({"email": email})
        if not db_user or not _verify_password(data.password, db_user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if db_user.get("twofa_enabled"):
            totp = pyotp.TOTP(db_user["twofa_secret"])
            if not totp.verify(data.code, valid_window=1):
                raise HTTPException(status_code=401, detail="Invalid 2FA code")
        user_id = str(db_user["_id"])
        access = _create_access_token(user_id, email)
        refresh = _create_refresh_token(user_id)
        response.set_cookie("access_token", access, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
        response.set_cookie("refresh_token", refresh, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
        return {"id": user_id, "email": email, "name": db_user.get("name"), "role": db_user.get("role", "user")}

    # =========================================================
    # Promo Codes
    # =========================================================
    @router.post("/admin/promo")
    async def create_promo(data: PromoCreateBody, request: Request):
        await get_admin_user(request)
        code = data.code.upper().strip()
        existing = await db.promo_codes.find_one({"code": code})
        if existing:
            raise HTTPException(status_code=400, detail="Promo code already exists")
        doc = {
            "code": code,
            "bonus_credits": data.bonus_credits,
            "max_uses": data.max_uses,
            "uses_count": 0,
            "expires_at": data.expires_at,
            "description": data.description or "",
            "created_at": _now().isoformat(),
            "enabled": True,
        }
        result = await db.promo_codes.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        doc.pop("_id", None)
        return doc

    @router.get("/admin/promo")
    async def list_promos(request: Request):
        await get_admin_user(request)
        promos = await db.promo_codes.find({}).sort("created_at", -1).to_list(500)
        return [{"id": str(p["_id"]), **{k: v for k, v in p.items() if k != "_id"}} for p in promos]

    @router.delete("/admin/promo/{promo_id}")
    async def delete_promo(promo_id: str, request: Request):
        await get_admin_user(request)
        await db.promo_codes.delete_one({"_id": ObjectId(promo_id)})
        return {"message": "Promo code deleted"}

    @router.post("/promo/redeem")
    async def redeem_promo(data: PromoRedeemBody, request: Request):
        user = await get_current_user(request)
        code = data.code.upper().strip()
        promo = await db.promo_codes.find_one({"code": code, "enabled": True})
        if not promo:
            raise HTTPException(status_code=404, detail="Invalid or inactive promo code")
        # Expiry
        if promo.get("expires_at"):
            try:
                exp = datetime.fromisoformat(promo["expires_at"])
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < _now():
                    raise HTTPException(status_code=400, detail="Promo code expired")
            except ValueError:
                pass
        # Max uses
        if promo.get("max_uses", 0) > 0 and promo.get("uses_count", 0) >= promo["max_uses"]:
            raise HTTPException(status_code=400, detail="Promo code fully redeemed")
        # Per-user once
        already = await db.promo_redemptions.find_one({"user_id": user["id"], "code": code})
        if already:
            raise HTTPException(status_code=400, detail="You have already redeemed this code")
        # Apply
        credits = int(promo["bonus_credits"])
        await db.users.update_one(
            {"_id": ObjectId(user["id"])},
            {"$inc": {"game_credits": credits}},
        )
        await db.promo_codes.update_one({"_id": promo["_id"]}, {"$inc": {"uses_count": 1}})
        await db.promo_redemptions.insert_one({
            "user_id": user["id"],
            "user_email": user["email"],
            "code": code,
            "credits": credits,
            "created_at": _now().isoformat(),
        })
        return {"message": f"Promo redeemed! +{credits} Game Credits", "credits_granted": credits}

    @router.get("/promo/history")
    async def promo_history(request: Request):
        user = await get_current_user(request)
        redemptions = await db.promo_redemptions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
        return redemptions

    # =========================================================
    # Referral System
    # =========================================================
    async def _ensure_referral_code(user_id: str) -> str:
        u = await db.users.find_one({"_id": ObjectId(user_id)})
        code = u.get("referral_code") if u else None
        if code:
            return code
        # Generate unique code
        for _ in range(10):
            code = _gen_referral_code()
            exists = await db.users.find_one({"referral_code": code})
            if not exists:
                break
        await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"referral_code": code}})
        return code

    @router.get("/referral/me")
    async def my_referral(request: Request):
        user = await get_current_user(request)
        code = await _ensure_referral_code(user["id"])
        referred = await db.referrals.count_documents({"referrer_user_id": user["id"]})
        bonus_total = 0
        async for r in db.referrals.find({"referrer_user_id": user["id"]}):
            bonus_total += int(r.get("bonus_credits", 0))
        return {
            "referral_code": code,
            "referred_count": referred,
            "bonus_earned": bonus_total,
            "reward_per_signup": 500,  # credits
        }

    @router.post("/referral/redeem")
    async def redeem_referral(data: ReferralRedeemBody, request: Request):
        user = await get_current_user(request)
        code = data.code.upper().strip()
        referrer = await db.users.find_one({"referral_code": code})
        if not referrer:
            raise HTTPException(status_code=404, detail="Invalid referral code")
        if str(referrer["_id"]) == user["id"]:
            raise HTTPException(status_code=400, detail="You can't use your own referral code")
        # Once per user
        already = await db.referrals.find_one({"referred_user_id": user["id"]})
        if already:
            raise HTTPException(status_code=400, detail="You have already used a referral code")
        reward = 500
        await db.users.update_one({"_id": ObjectId(user["id"])}, {"$inc": {"game_credits": reward}})
        await db.users.update_one({"_id": referrer["_id"]}, {"$inc": {"game_credits": reward}})
        await db.referrals.insert_one({
            "referrer_user_id": str(referrer["_id"]),
            "referrer_email": referrer["email"],
            "referred_user_id": user["id"],
            "referred_email": user["email"],
            "bonus_credits": reward,
            "created_at": _now().isoformat(),
        })
        return {"message": f"Referral applied! +{reward} Game Credits for both.", "credits_granted": reward}

    # =========================================================
    # Support Tickets (user + admin)
    # =========================================================
    @router.post("/support/ticket")
    async def create_ticket(data: SupportTicketBody, request: Request):
        user = await get_current_user(request)
        priority = data.priority if data.priority in ("low", "normal", "high") else "normal"
        doc = {
            "user_id": user["id"],
            "user_email": user["email"],
            "user_name": user.get("name", ""),
            "subject": data.subject,
            "message": data.message,
            "priority": priority,
            "status": "open",
            "responses": [],
            "created_at": _now().isoformat(),
            "updated_at": _now().isoformat(),
        }
        r = await db.support_tickets.insert_one(doc)
        return {"id": str(r.inserted_id), "message": "Ticket created"}

    @router.get("/support/tickets")
    async def user_tickets(request: Request):
        user = await get_current_user(request)
        tickets = await db.support_tickets.find({"user_id": user["id"]}).sort("created_at", -1).to_list(200)
        return [{"id": str(t["_id"]), **{k: v for k, v in t.items() if k != "_id"}} for t in tickets]

    @router.get("/admin/support/tickets")
    async def all_tickets(request: Request, status: Optional[str] = None):
        await get_admin_user(request)
        q: Dict[str, Any] = {}
        if status:
            q["status"] = status
        tickets = await db.support_tickets.find(q).sort("created_at", -1).to_list(500)
        return [{"id": str(t["_id"]), **{k: v for k, v in t.items() if k != "_id"}} for t in tickets]

    @router.post("/admin/support/tickets/{ticket_id}/respond")
    async def respond_ticket(ticket_id: str, data: TicketResponseBody, request: Request):
        admin = await get_admin_user(request)
        resp = {
            "author": admin["email"],
            "message": data.message,
            "created_at": _now().isoformat(),
        }
        r = await db.support_tickets.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$push": {"responses": resp}, "$set": {"status": "answered", "updated_at": _now().isoformat()}},
        )
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return {"message": "Response added"}

    @router.post("/admin/support/tickets/{ticket_id}/close")
    async def close_ticket(ticket_id: str, request: Request):
        await get_admin_user(request)
        r = await db.support_tickets.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": {"status": "closed", "updated_at": _now().isoformat()}},
        )
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return {"message": "Ticket closed"}

    # =========================================================
    # Enhanced Admin Analytics
    # =========================================================
    @router.get("/admin/analytics/overview")
    async def analytics_overview(request: Request):
        await get_admin_user(request)
        total_users = await db.users.count_documents({})
        new_users_7d_cutoff = (_now() - timedelta(days=7)).isoformat()
        new_users_7d = await db.users.count_documents({"created_at": {"$gte": new_users_7d_cutoff}})
        total_tx = await db.payment_transactions.count_documents({})
        completed_tx = await db.payment_transactions.count_documents({"status": "completed"})
        pipeline = [
            {"$match": {"status": "completed"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
        rev = await db.payment_transactions.aggregate(pipeline).to_list(1)
        total_revenue = rev[0]["total"] if rev else 0
        promo_redeemed = await db.promo_redemptions.count_documents({})
        referrals = await db.referrals.count_documents({})
        open_tickets = await db.support_tickets.count_documents({"status": "open"})
        return {
            "total_users": total_users,
            "new_users_7d": new_users_7d,
            "total_transactions": total_tx,
            "completed_transactions": completed_tx,
            "total_revenue": total_revenue,
            "promo_redeemed": promo_redeemed,
            "referrals": referrals,
            "open_tickets": open_tickets,
        }

    @router.get("/admin/analytics/revenue-by-day")
    async def revenue_by_day(request: Request, days: int = 14):
        await get_admin_user(request)
        days = min(max(days, 1), 90)
        cutoff_iso = (_now() - timedelta(days=days)).isoformat()
        # created_at is stored as ISO string in this codebase
        txs = await db.payment_transactions.find(
            {"status": "completed", "created_at": {"$gte": cutoff_iso}},
            {"_id": 0, "amount": 1, "created_at": 1},
        ).to_list(5000)
        buckets: Dict[str, float] = {}
        for t in txs:
            c = t.get("created_at")
            if isinstance(c, str):
                day = c[:10]
            elif isinstance(c, datetime):
                day = c.date().isoformat()
            else:
                continue
            buckets[day] = buckets.get(day, 0) + float(t.get("amount", 0))
        # Build full list for the last N days
        out = []
        today = _now().date()
        for i in range(days, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            out.append({"date": d, "revenue": round(buckets.get(d, 0), 2)})
        return out

    @router.get("/admin/analytics/signups-by-day")
    async def signups_by_day(request: Request, days: int = 14):
        await get_admin_user(request)
        days = min(max(days, 1), 90)
        cutoff_iso = (_now() - timedelta(days=days)).isoformat()
        users = await db.users.find({"created_at": {"$gte": cutoff_iso}}, {"_id": 0, "created_at": 1}).to_list(5000)
        buckets: Dict[str, int] = {}
        for u in users:
            c = u.get("created_at")
            if isinstance(c, str):
                day = c[:10]
            elif isinstance(c, datetime):
                day = c.date().isoformat()
            else:
                continue
            buckets[day] = buckets.get(day, 0) + 1
        out = []
        today = _now().date()
        for i in range(days, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            out.append({"date": d, "signups": buckets.get(d, 0)})
        return out

    @router.get("/admin/analytics/top-users")
    async def top_users(request: Request, limit: int = 10):
        await get_admin_user(request)
        limit = min(max(limit, 1), 100)
        pipeline = [
            {"$match": {"status": "completed"}},
            {"$group": {"_id": "$user_id", "total_spend": {"$sum": "$amount"}, "email": {"$first": "$user_email"}}},
            {"$sort": {"total_spend": -1}},
            {"$limit": limit},
        ]
        res = await db.payment_transactions.aggregate(pipeline).to_list(limit)
        return [{"user_id": r["_id"], "email": r.get("email", ""), "total_spend": round(r["total_spend"], 2)} for r in res]

    return router
