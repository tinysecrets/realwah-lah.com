from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / '.env')

try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
except ImportError:
    sentry_sdk = None
    FastApiIntegration = None

if sentry_sdk and os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN"),
        integrations=[FastApiIntegration()],
        traces_sample_rate=1.0,
    )

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import re
import logging
import bcrypt
import jwt
import secrets
import string
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict
# Stripe integration removed. Payment endpoints are disabled unless re-enabled via environment and dependencies.

# Game Middleware imports
from middleware.game_middleware_manager import GameMiddlewareManager
from middleware.sugar_sweeps_bridge import SugarSweepsBridge

# Services
from services.email_service import email_service
from services.bonus_service import BonusService
from services.currency_service import CurrencyService

# Feature extensions
from routes.extensions import build_extensions_router
from routes.telegram_bridge import build_telegram_router
from routes.platform_jit import build_platform_router, ensure_platform_registered
from routes.distributor_pool import build_distributor_pool_router, execute_pool_transfer
from routes.nerve_center import build_nerve_center_router
from routes.telegram_bridge import build_telegram_router as _build_telegram_router  # included conditionally below
from routes.whatsapp_bridge import build_whatsapp_router as _build_whatsapp_router

# Currency models and config
from models.currency_models import PurchaseType, BonusGrantType
from config.currency_config import (
    AMOE_DAILY_CREDITS,
    calculate_redemption_usd
)

# MongoDB connection
mongodb_uri = (
    os.environ.get("MONGODB_URI")
    or os.environ.get("MONGO_URL")
    or os.environ.get("MONGO_URI")
)
if not mongodb_uri:
    raise RuntimeError(
        "MONGODB_URI is required. Set it in the root .env for local testing "
        "or via production environment variables / Fly secrets."
    )
client = AsyncIOMotorClient(mongodb_uri)
db = client[os.environ.get("DB_NAME", "wahlah_prod")]

app = FastAPI()
api_router = APIRouter(prefix="/api")

@api_router.get("/health")
async def health():
    try:
        await db.command("ping")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logging.getLogger(__name__).error("Health check database error: %s", e)
        return {"status": "ok", "database": "error"}


# Mount WhatsApp router if enabled via env
if os.environ.get("WHATSAPP_ENABLED", "false").lower() in ("1", "true", "yes"):
    try:
        api_router.include_router(_build_whatsapp_router())
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to mount WhatsApp router: {e}")

# Mount Telegram router if enabled via env
if os.environ.get("TELEGRAM_ENABLED", "false").lower() in ("1", "true", "yes"):
    try:
        api_router.include_router(_build_telegram_router())
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to mount Telegram router: {e}")


# Initialize Game Middleware Manager
middleware_manager = None

# Initialize Sugar Sweeps Bridge (Master Tank for P2P)
sugar_sweeps_bridge = None

# Initialize Bonus Service
bonus_service = None

# Initialize Currency Service
currency_service = None

# JWT Config
JWT_ALGORITHM = "HS256"

# Cookie security: drive from env so we can keep secure=False in local dev
# and secure=True on HTTPS production (wah-lah.com / api.wah-lah.com).
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax").lower()

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

# Password hashing
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

# JWT Token Management
def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "exp": datetime.now(timezone.utc) + timedelta(minutes=60), "type": "access"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

# Auth Helper
async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["id"] = str(user["_id"])
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_admin_user(request: Request) -> dict:
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# Pydantic Models
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None
    age_verified: bool = False

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    sugar_tokens: int = 0  # Purchased product
    game_credits: int = 0  # Sweepstakes entries (redeemable)
    credits: float = 0.0  # DEPRECATED: Keep for backward compatibility
    age_verified: bool = False
    game_accounts: Optional[Dict[str, dict]] = None
    game_password: Optional[str] = None
    last_amoe_claim: Optional[str] = None
    created_at: str

class UserUpdate(BaseModel):
    game_accounts: Optional[Dict[str, dict]] = None
    game_password: Optional[str] = None

class GameCreate(BaseModel):
    name: str
    logo_url: str
    game_url: str
    description: Optional[str] = ""
    is_active: bool = True
    accent_color: str = "#ff00ff"

class GameUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    game_url: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    accent_color: Optional[str] = None

class GameResponse(BaseModel):
    id: str
    name: str
    logo_url: str
    game_url: str
    description: str
    is_active: bool
    accent_color: str
    created_at: str

class PaymentPackage(BaseModel):
    id: str
    name: str
    amount: float
    credits: float
    description: str

class CheckoutRequest(BaseModel):
    amount: float  # Custom amount (min $1)
    game_id: str
    account_name: str
    origin_url: str
    payment_method: str = "stripe"

class ManualPaymentRequest(BaseModel):
    user_id: str
    amount: float
    credits: float
    game_id: str
    account_name: str
    payment_method: str
    notes: Optional[str] = ""

class TransactionResponse(BaseModel):
    id: str
    user_id: str
    user_email: str
    amount: float
    credits: float
    game_id: str
    game_name: str
    account_name: str
    payment_method: str
    status: str
    session_id: Optional[str] = None
    created_at: str
    updated_at: str

# Minimum deposit amount
MIN_DEPOSIT = 1.00

# Quick deposit suggestions (not packages, just suggestions)
DEPOSIT_SUGGESTIONS = [10, 20, 50, 100, 200]

# WALA MAGIC: Auto-generate game credentials
def generate_game_username(user_id: str) -> str:
    """Generate a unique game username of the form: sugar + 2-3 lowercase letters + 3 digits.

    The user_id is unused externally but kept to allow future seeding for uniqueness guarantees.
    """
    letters = string.ascii_lowercase
    digits = string.digits
    suffix_letters = "".join(secrets.choice(letters) for _ in range(secrets.choice([2, 3])))
    suffix_digits = "".join(secrets.choice(digits) for _ in range(3))
    return f"sugar{suffix_letters}{suffix_digits}"

def generate_game_password() -> str:
    """All passwords are preset to Abc123 until explicitly changed by the user."""
    return "Abc123"

# Auth Endpoints

# Feature extensions: password reset, 2FA, VIP, promos, referrals, etc.
api_router.include_router(
    build_extensions_router(
        db=db,
        get_current_user=get_current_user,
        get_admin_user=get_admin_user,
    )
)


@api_router.post("/auth/register")
async def register(data: UserRegister, response: Response):
    email = data.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    if not data.age_verified:
        raise HTTPException(status_code=400, detail="You must verify you are 18 or older")
    
    # Derive display name from email if not provided
    user_name = (data.name or email.split("@")[0]).strip() or email.split("@")[0]

    # Create user first to get ID
    temp_user_doc = {
        "email": email,
        "password_hash": hash_password(data.password),
        "name": user_name,
        "role": "user",
        "sugar_tokens": 0,
        "game_credits": 0,
        "credits": 0.0,
        "age_verified": data.age_verified,
        "game_accounts": {},
        "game_username": "",
        "game_password": "",
        "last_amoe_claim": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.users.insert_one(temp_user_doc)
    user_id = str(result.inserted_id)
    
    # WALA MAGIC: Auto-generate game credentials
    game_username = generate_game_username(user_id)
    game_password = generate_game_password()
    
    # Update user with game credentials
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "game_username": game_username,
            "game_password": game_password
        }}
    )
    
    logger.info(f"🎮 Generated game credentials for {email}: {game_username}")
    
    # Send welcome email
    try:
        email_service.send_welcome_rich(email, user_name)
    except Exception as e:
        logger.warning(f"Failed to send welcome email: {str(e)}")
    
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=604800, path="/")
    
    return {
        "id": user_id,
        "email": email,
        "name": user_name,
        "role": "user",
        "credits": 0.0,
        "age_verified": data.age_verified,
        "game_username": game_username,
        "game_password": game_password,
        "message": "🎮 SAVE THESE CREDENTIALS! Use them to sign up on ALL game platforms."
    }

@api_router.post("/auth/login")
async def login(data: UserLogin, response: Response, request: Request):
    email = data.email.lower()
    identifier = f"{request.client.host}:{email}"
    
    # Check brute force
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("count", 0) >= 5:
        lockout_time = attempt.get("locked_until")
        if lockout_time and datetime.fromisoformat(lockout_time) > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
        else:
            await db.login_attempts.delete_one({"identifier": identifier})
    
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        # Increment failed attempts
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"locked_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}},
            upsert=True
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Clear failed attempts on success
    await db.login_attempts.delete_one({"identifier": identifier})
    
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=604800, path="/")
    
    return {
        "id": user_id,
        "email": user["email"],
        "name": user["name"],
        "role": user.get("role", "user"),
        "credits": user.get("credits", 0.0),
        "game_username": user.get("game_username", ""),
        "game_password": user.get("game_password", "")
    }

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}

@api_router.get("/auth/me")
async def get_me(request: Request):
    user = await get_current_user(request)
    return user

@api_router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        access_token = create_access_token(str(user["_id"]), user["email"])
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=3600, path="/")
        return {"message": "Token refreshed"}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============================================
# AMOE (Alternate Method of Entry) - Legal Requirement
# ============================================

class AMOEClaimRequest(BaseModel):
    """Request to claim daily free credits (No Purchase Necessary)"""
    pass

@api_router.post("/amoe/claim-daily")
async def claim_daily_free_credits(request: Request):
    """
    AMOE - Alternate Method of Entry
    
    Legal Requirement: Users must be able to get sweepstakes entries WITHOUT purchasing.
    This endpoint grants free Game Credits every 24 hours.
    """
    user = await get_current_user(request)
    
    if not currency_service:
        raise HTTPException(status_code=503, detail="Currency service not initialized")
    
    success, message = await currency_service.claim_amoe_daily(
        user_id=user["id"],
        user_email=user["email"]
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # Get updated balance
    balance = await currency_service.get_user_balance(user["id"])
    
    return {
        "success": True,
        "message": message,
        "credits_granted": AMOE_DAILY_CREDITS,
        "new_balance": balance
    }

@api_router.get("/amoe/status")
async def get_amoe_status(request: Request):
    """Check AMOE claim eligibility"""
    user = await get_current_user(request)
    
    last_claim = user.get("last_amoe_claim")
    
    if not last_claim:
        return {
            "eligible": True,
            "message": "Claim your free credits!",
            "next_eligible": None
        }



# Mount all API routes.
app.include_router(api_router)
