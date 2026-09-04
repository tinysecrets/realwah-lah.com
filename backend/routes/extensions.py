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
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId
import bcrypt
import jwt
try:
    import pyotp
    PYOTP_AVAILABLE = True
except Exception:
    pyotp = None
    PYOTP_AVAILABLE = False

try:
    import qrcode
    QRCODE_AVAILABLE = True
except Exception:
    qrcode = None
    QRCODE_AVAILABLE = False

logger = logging.getLogger(__name__)
JWT_ALGORITHM = "HS256"

VIP_TIERS = [
    {"name": "Bronze", "min_spend": 0, "bonus_pct": 0, "color": "#cd7f32"},
    {"name": "Silver", "min_spend": 100, "bonus_pct": 5, "color": "#c0c0c0"},
    {"name": "Gold", "min_spend": 500, "bonus_pct": 10, "color": "#ffd700"},
    {"name": "Platinum", "min_spend": 2000, "bonus_pct": 15, "color": "#e5e4e2"},
    {"name": "Diamond", "min_spend": 10000, "bonus_pct": 25, "color": "#b9f2ff"},
]


def compute_vip_tier(total_spend_usd: float) -> Dict[str, Any]:
    tier = VIP_TIERS[0]
    for candidate in VIP_TIERS:
        if total_spend_usd >= candidate["min_spend"]:
            tier = candidate
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


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class PasswordChangeBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class TwoFAVerify(BaseModel):
    code: str


class TwoFALoginBody(BaseModel):
    email: EmailStr
    password: str
    code: str


class PromoCreateBody(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    bonus_credits: int = Field(ge=1)
    playthrough_multiplier: float = Field(default=1.0, ge=0.0)
    max_uses: int = Field(default=0, ge=0)
    expires_at: Optional[str] = None
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


def _gen_token(n: int = 32) -> str:
    return secrets.token_urlsafe(n)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
    payload = {"sub": user_id, "email": email, "exp": _now() + timedelta(minutes=60), "type": "access"}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def _create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": _now() + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def build_extensions_router(db, get_current_user, get_admin_user) -> APIRouter:
    router = APIRouter(prefix="/ext", tags=["extensions"])

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

        if user:
            token = _gen_token(32)
            now = _now()
            frontend_url = os.environ.get("FRONTEND_URL", "https://wah-lah.com").rstrip("/")
            reset_path = os.environ.get("PASSWORD_RESET_PATH", "/reset-password")
            reset_link = f"{frontend_url}{reset_path}?token={token}"

            await db.password_resets.update_many(
                {"user_id": str(user["_id"]), "used": False},
                {"$set": {"used": True, "invalidated_at": now}},
            )
            await db.password_resets.insert_one({
                "user_id": str(user["_id"]),
                "email": email,
                "token_hash": _token_hash(token),
                "expires_at": now + timedelta(hours=1),
                "used": False,
                "created_at": now,
            })

            try:
                from services.email_service import email_service
                if not email_service.api_key:
                    logger.warning("Password reset requested but Resend is not configured")
                else:
                    display_name = user.get("name") or email.split("@")[0]
                    ok, msg = email_service.send_password_reset_email(email, display_name, token)
                    if not ok:
                        logger.warning("Password reset email delivery failed: %s", msg)
            except Exception:
                logger.exception("Password reset email delivery failed")

        # Deliberately identical for existing and non-existing accounts.
        # In non-production environments, expose the generated token to support
        # manual reset verification without creating a second system or altering the
        # production UX.
        response = {"message": "If the email exists, a reset link has been issued."}
        if os.environ.get("APP_ENV", "development").strip().lower() not in {"production", "prod"}:
            response["dev_token"] = token if user else None
            response["dev_reset_link"] = reset_link if user else None
        return response

    @router.post("/password/reset")
    async def reset_password(data: PasswordResetConfirm):
        token_hash = _token_hash(data.token)
        rec = await db.password_resets.find_one({"token_hash": token_hash, "used": False})
        if not rec:
            raise HTTPException(status_code=400, detail="Invalid or expired token")
        exp = rec["expires_at"]
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < _now():
            await db.password_resets.update_one({"_id": rec["_id"]}, {"$set": {"used": True, "expired_at": _now()}})
            raise HTTPException(status_code=400, detail="Token expired")

        new_hash = _hash_password(data.new_password)
        result = await db.users.update_one(
            {"_id": ObjectId(rec["user_id"])},
            {"$set": {"password_hash": new_hash}},
        )
        if result.matched_count != 1:
            raise HTTPException(status_code=400, detail="Account no longer exists")
        await db.password_resets.update_one({"_id": rec["_id"]}, {"$set": {"used": True, "used_at": _now()}})
        return {"message": "Password reset successful"}

    @router.post("/password/change")
    async def change_password(data: PasswordChangeBody, request: Request):
        user = await get_current_user(request)
        db_user = await db.users.find_one({"_id": ObjectId(user["id"])})
        if not db_user or not _verify_password(data.current_password, db_user.get("password_hash", "")):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"password_hash": _hash_password(data.new_password)}})
        return {"message": "Password updated"}

    # =========================================================
    # 2FA (TOTP)
    # =========================================================
    @router.post("/2fa/setup")
    async def twofa_setup(request: Request):
        if not PYOTP_AVAILABLE or not QRCODE_AVAILABLE:
            raise HTTPException(status_code=503, detail="2FA is unavailable: required libraries are not installed")
        user = await get_current_user(request)
        secret = pyotp.random_base32()
        issuer = "WAH-LAH"
        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name=issuer)
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"twofa_pending_secret": secret}})
        return {"secret": secret, "otpauth_uri": uri, "qr_code_base64": f"data:image/png;base64,{qr_b64}"}

    @router.post("/2fa/enable")
    async def twofa_enable(data: TwoFAVerify, request: Request):
        if not PYOTP_AVAILABLE:
            raise HTTPException(status_code=503, detail="2FA is unavailable: required libraries are not installed")
        user = await get_current_user(request)
        db_user = await db.users.find_one({"_id": ObjectId(user["id"])})
        secret = db_user.get("twofa_pending_secret")
        if not secret:
            raise HTTPException(status_code=400, detail="Start 2FA setup first")
        if not pyotp.TOTP(secret).verify(data.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid code")
        await db.users.update_one(
            {"_id": ObjectId(user["id"])},
            {"$set": {"twofa_secret": secret, "twofa_enabled": True}, "$unset": {"twofa_pending_secret": ""}},
        )
        return {"message": "2FA enabled"}

    @router.post("/2fa/disable")
    async def twofa_disable(data: TwoFAVerify, request: Request):
        if not PYOTP_AVAILABLE:
            raise HTTPException(status_code=503, detail="2FA is unavailable: required libraries are not installed")
        user = await get_current_user(request)
        db_user = await db.users.find_one({"_id": ObjectId(user["id"])})
        if not db_user.get("twofa_enabled"):
            raise HTTPException(status_code=400, detail="2FA is not enabled")
        if not pyotp.TOTP(db_user["twofa_secret"]).verify(data.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid code")
        await db.users.update_one(
            {"_id": ObjectId(user["id"])},
            {"$set": {"twofa_enabled": False}, "$unset": {"twofa_secret": ""}},
        )
        return {"message": "2FA disabled"}

    @router.get("/2fa/status")
    async def twofa_status(request: Request):
        user = await get_current_user(request)
        db_user = await db.users.find_one({"_id": ObjectId(user["id"])}, {"twofa_enabled": 1})
        return {"enabled": bool(db_user and db_user.get("twofa_enabled"))}

    @router.post("/auth/login-2fa")
    async def login_with_2fa(data: TwoFALoginBody, response: Response):
        """Login that requires a TOTP code when the account has 2FA enabled."""
        email = data.email.lower()
        db_user = await db.users.find_one({"email": email})
        if not db_user or not _verify_password(data.password, db_user.get("password_hash", "")):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if db_user.get("twofa_enabled"):
            if not PYOTP_AVAILABLE:
                raise HTTPException(status_code=503, detail="2FA unavailable: server is missing support libraries")
            secret = db_user.get("twofa_secret")
            if not secret or not pyotp.TOTP(secret).verify(data.code or "", valid_window=1):
                raise HTTPException(status_code=401, detail="Invalid 2FA code")
        user_id = str(db_user["_id"])
        access = _create_access_token(user_id, email)
        refresh = _create_refresh_token(user_id)
        cookie_secure = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
        cookie_samesite = os.environ.get("COOKIE_SAMESITE", "lax")
        response.set_cookie("access_token", access, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=3600, path="/")
        response.set_cookie("refresh_token", refresh, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=604800, path="/")
        return {"id": user_id, "email": email, "name": db_user.get("name"), "role": db_user.get("role", "user")}

    return router
