from dotenv import load_dotenv
from pathlib import Path
import os
import logging
from contextlib import asynccontextmanager

# Setup logging before any other imports
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

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
import bcrypt
import jwt
import secrets
import string
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict

try:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    from slowapi.middleware import SlowAPIMiddleware
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False

# Services
from services.email_service import email_service
from services.bonus_service import BonusService
from services.currency_service import CurrencyService
from game_seed import ensure_games_seeded

# Feature extensions
from routes.extensions import build_extensions_router
from routes.telegram_bridge import build_telegram_router
from routes.platform_jit import build_platform_router, ensure_platform_registered
from routes.distributor_pool import build_distributor_pool_router, execute_pool_transfer
from routes.self_distributor import build_self_distributor_router
from routes.nerve_center import build_nerve_center_router
from routes.genie import build_genie_router
from routes.user_routes import build_user_router
from routes.compliance import build_compliance_router
from routes.admin_analytics import build_admin_analytics_router
from routes.revenue_admin import build_revenue_admin_router
from routes.gift_cards import build_gift_cards_router
from routes.webhooks import build_webhooks_router
from routes.payment import build_payment_router
from routes.boss_genie import build_boss_router

# Currency models and config
from models.currency_models import PurchaseType, BonusGrantType
from config.currency_config import (
    AMOE_DAILY_CREDITS,
    calculate_redemption_usd
)

# MongoDB connection
mongoodb_uri = (
    os.environ.get("MONGODB_URI")
    or os.environ.get("MONGO_URL")
    or os.environ.get("MONGO_URI")
)
if not mongoodb_uri:
    raise RuntimeError(
        "MONGODB_URI (or MONGO_URL / MONGO_URI) is required. Set it in the root "
        ".env for local testing or via production environment variables "
        "(Render dashboard, Fly secrets, etc.)."
    )
client = AsyncIOMotorClient(mongoodb_uri)
db = client[os.environ.get("DB_NAME", "wahlah_prod")]


@asynccontextmanager
async def lifespan(app):
    """Run startup/shutdown tasks for the FastAPI app."""
    # Auto-seed the games collection (no-op if games already exist). Never
    # overwrites operator-managed data — only fills an empty collection.
    try:
        result = await ensure_games_seeded(db)
        if result.get("seeded"):
            logger.info("Seeded %d games into the games collection.", result["count"])
        else:
            logger.info("Games collection already seeded (%d games).", result.get("count", 0))
    except Exception:
        logger.exception("Game seed on startup failed (non-fatal).")

    # Bind real platform-registration adapters (replaces the dry-run stub for
    # the hub's supported platforms). Non-fatal: until api_paths.register is
    # captured in hub_registry.py the adapter degrades to dry-run behavior.
    try:
        from routes.platform_adapters import bind_hub_register_adapters
        bind_hub_register_adapters()
    except Exception:
        logger.exception("Binding platform register adapters failed (non-fatal).")

    yield


app = FastAPI(title="WAH-LAH API", version="1.0.0", lifespan=lifespan)
api_router = APIRouter(prefix="/api")

# Rate limiting: key on the first public-facing IP. Behind the Cloudflare
# API proxy we trust CF-Connecting-IP; fall back to the peer address.
if SLOWAPI_AVAILABLE:
    def _rate_key(request: Request) -> str:
        cf = request.headers.get("CF-Connecting-IP")
        if cf:
            return cf.strip()
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
        return get_remote_address(request)

    limiter = Limiter(
        key_func=_rate_key,
        default_limits=[os.environ.get("RATE_LIMIT_DEFAULT", "120/minute")],
        headers_enabled=True,
    )
    app.state.limiter = limiter

    def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
        return Response(
            content='{"detail":"Rate limit exceeded. Try again later."}',
            status_code=429,
            media_type="application/json",
            headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
        )

    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# CORS Configuration
cors_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@api_router.get("/health")
async def health():
    """Liveness check endpoint (never blocks on MongoDB)."""
    return {"status": "ok", "service": "wah-lah"}

# Mount Telegram router if enabled via env
if os.environ.get("TELEGRAM_ENABLED", "false").lower() in ("1", "true", "yes"):
    try:
        api_router.include_router(build_telegram_router())
        logger.info("✅ Telegram router mounted")
    except Exception as e:
        logger.warning(f"⚠️ Failed to mount Telegram router: {e}")

# Initialize Game Middleware Manager
middleware_manager = None

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
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise ValueError("JWT_SECRET environment variable is required")
    return secret

# Password hashing
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

# JWT Token Management
def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
        "type": "access"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh"
    }
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
    password: str = Field(min_length=8, description="Password must be at least 8 characters")
    name: Optional[str] = None
    age_verified: bool = Field(
        default=False,
        description="Must be true to confirm user is 21+ (legal requirement for sweepstakes)"
    )

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

# ============================================
# AUTH ENDPOINTS
# ============================================

# Feature extensions: password reset, 2FA, VIP, promos, referrals, etc.
api_router.include_router(
    build_extensions_router(
        db=db,
        get_current_user=get_current_user,
        get_admin_user=get_admin_user,
    )
)
api_router.include_router(
    build_genie_router(db=db, get_current_user=get_current_user)
)
api_router.include_router(
    build_user_router(db=db, get_current_user=get_current_user)
)
api_router.include_router(
    build_compliance_router(
        db=db,
        get_current_user=get_current_user,
        get_admin_user=get_admin_user,
    )
)
api_router.include_router(
    build_platform_router(
        db=db,
        get_current_user=get_current_user,
        get_admin_user=get_admin_user,
    )
)
api_router.include_router(
    build_distributor_pool_router(db=db, get_admin_user=get_admin_user)
)
api_router.include_router(
    build_self_distributor_router(db=db, get_admin_user=get_admin_user)
)
api_router.include_router(
    build_nerve_center_router(db=db, get_admin_user=get_admin_user)
)
api_router.include_router(
    build_boss_router(db=db, get_admin_user=get_admin_user)
)
api_router.include_router(
    build_admin_analytics_router(db=db, get_admin_user=get_admin_user)
)
api_router.include_router(
    build_revenue_admin_router(db=db, get_admin_user=get_admin_user)
)
api_router.include_router(
    build_gift_cards_router(
        db=db,
        get_current_user=get_current_user,
        get_admin_user=get_admin_user,
    )
)
api_router.include_router(
    build_webhooks_router(db=db)
)
api_router.include_router(
    build_payment_router(
        db=db,
        get_current_user=get_current_user,
        get_admin_user=get_admin_user,
    )
)


@api_router.post("/auth/register")
@limiter.limit(os.environ.get("RATE_LIMIT_REGISTER", "10/minute")) if SLOWAPI_AVAILABLE else (lambda f: f)
async def register(data: UserRegister, response: Response, request: Request):
    email = data.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    if not data.age_verified:
        raise HTTPException(
            status_code=400,
            detail="You must verify you are 21+ years old (legal requirement for sweepstakes)"
        )
    
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
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=3600,
        path="/"
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=604800,
        path="/"
    )
    
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
@limiter.limit(os.environ.get("RATE_LIMIT_LOGIN", "20/minute")) if SLOWAPI_AVAILABLE else (lambda f: f)
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
    if not user or not verify_password(data.password, user.get("password_hash", "")):
        # Increment failed attempts
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {
                "$inc": {"count": 1},
                "$set": {"locked_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}
            },
            upsert=True
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Clear failed attempts on success
    await db.login_attempts.delete_one({"identifier": identifier})
    
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=3600,
        path="/"
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=604800,
        path="/"
    )
    
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
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            max_age=3600,
            path="/"
        )
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
    
    try:
        last_claim_dt = datetime.fromisoformat(last_claim)
        now = datetime.now(timezone.utc)
        if last_claim_dt.tzinfo is None:
            last_claim_dt = last_claim_dt.replace(tzinfo=timezone.utc)
        
        next_eligible = last_claim_dt + timedelta(hours=24)
        is_eligible = now >= next_eligible
        
        return {
            "eligible": is_eligible,
            "message": "Claim your free credits!" if is_eligible else "Already claimed today. Come back tomorrow!",
            "next_eligible": next_eligible.isoformat() if not is_eligible else None,
            "last_claimed": last_claim
        }
    except (ValueError, TypeError):
        return {
            "eligible": True,
            "message": "Claim your free credits!",
            "next_eligible": None
        }

# ============================================
# MOUNT ALL ROUTERS
# ============================================

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
