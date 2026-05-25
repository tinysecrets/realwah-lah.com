from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
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
from services.stripe_client import StripeCheckout, CheckoutSessionRequest

# Game Middleware imports
from middleware.game_middleware_manager import GameMiddlewareManager
from middleware.sugar_sweeps_bridge import SugarSweepsBridge

# Services
from services.email_service import email_service
from services.bonus_service import BonusService
from services.currency_service import CurrencyService

# Feature extensions
from routes.extensions import build_extensions_router
from routes.platform_jit import build_platform_router, ensure_platform_registered
from routes.distributor_pool import build_distributor_pool_router, execute_pool_transfer
from routes.nerve_center import build_nerve_center_router

# Currency models and config
from models.currency_models import PurchaseType, BonusGrantType
from config.currency_config import (
    AMOE_DAILY_CREDITS,
    calculate_redemption_usd
)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

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
        email_service.send_welcome_email(email, user_name)
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
    
    from datetime import timedelta
    from config.currency_config import AMOE_COOLDOWN_HOURS
    
    last_claim_time = datetime.fromisoformat(last_claim)
    next_eligible = last_claim_time + timedelta(hours=AMOE_COOLDOWN_HOURS)
    eligible = datetime.now(timezone.utc) >= next_eligible
    
    return {
        "eligible": eligible,
        "last_claim": last_claim,
        "next_eligible": next_eligible.isoformat(),
        "hours_remaining": max(0, int((next_eligible - datetime.now(timezone.utc)).total_seconds() / 3600))
    }

# ============================================
# Redemption Endpoints
# ============================================

class RedemptionRequestModel(BaseModel):
    game_credits: int
    btc_address: str
    game_id: Optional[str] = None  # If set, runs JIT registration gate on that platform.

@api_router.post("/redemption/request")
async def create_redemption_request(data: RedemptionRequestModel, request: Request):
    """
    Request to redeem Game Credits for Bitcoin.
    
    Only GAME CREDITS can be redeemed (not Sugar Tokens).
    Minimum: 5,000 credits ($50)
    Compliance gates: geoblock → OFAC → tiered KYC → admin-hold queue.
    """
    user = await get_current_user(request)
    
    if not currency_service:
        raise HTTPException(status_code=503, detail="Currency service not initialized")

    # ================ MASTER BTC KILL SWITCH ================
    from services.feature_flags import get_flag as _ff_flag
    if not await _ff_flag(db, "btc_payouts_enabled"):
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Bitcoin redemption is not available yet. Gift card redemption is coming soon.",
                "btc_enabled": False,
                "reason": "feature_flag_off",
            },
        )

    # ================ COMPLIANCE GATES (pre-redemption) ================
    from services.compliance import (
        check_btc_address,
        check_geoblock,
    )
    from services.compliance.geoblock import client_ip_from_request, record_geoblock_event
    from services.compliance.ofac import record_ofac_hit
    from services.compliance.kyc import is_user_cleared_for
    from services.compliance import record_aml_event

    amount_usd = calculate_redemption_usd(data.game_credits)

    # ---------- HOUSE FEE (BTC redemption) ----------
    # Player asks for N credits → we pay out `net_usd` worth of BTC and keep
    # `fee_usd` as house revenue. KYC tiers and AML reporting still key off
    # the GROSS amount (player intent), not the net — that's the safer side
    # for compliance auditing.
    from services.revenue import get_rates, apply_fee, record_revenue
    _rev_rates = await get_rates(db)
    _split = apply_fee(amount_usd, _rev_rates["btc"])
    net_payout_usd = _split["net_usd"]
    fee_usd = _split["fee_usd"]

    # Gate 1: geoblock
    client_ip = client_ip_from_request(request)
    blocked, geo_reason, detected_state = await check_geoblock(client_ip)
    await record_geoblock_event(
        db, user_id=user["id"], ip=client_ip, state=detected_state,
        blocked=blocked, context="redemption/request",
    )
    if blocked:
        raise HTTPException(status_code=451, detail=f"Redemption unavailable in your region ({geo_reason}).")

    # Gate 2: OFAC screening on recipient BTC address
    flagged, ofac_reason = await check_btc_address(data.btc_address)
    if flagged:
        await record_ofac_hit(db, user_id=user["id"], btc_address=data.btc_address, context="redemption/request")
        raise HTTPException(status_code=451, detail=f"Recipient address blocked by compliance screening ({ofac_reason}).")

    # Gate 3: tiered KYC
    cleared, kyc_reason, req_tier = await is_user_cleared_for(db, user["id"], amount_usd)
    if not cleared:
        raise HTTPException(
            status_code=402,
            detail={
                "message": f"KYC required for redemptions ≥ ${amount_usd:.0f}. Complete {req_tier} verification to continue.",
                "required_tier": req_tier,
                "kyc_initiate_endpoint": "/api/ext/compliance/kyc/initiate",
                "reason": kyc_reason,
            },
        )

    # JIT platform registration gate: if the user is redeeming credits tied to
    # a specific game, ensure they are registered on that platform so we can
    # later reconcile the credit pull. If no game_id provided, require at
    # least one active platform_account (proves the user has deposited before).
    if data.game_id:
        game = await db.games.find_one({"_id": ObjectId(data.game_id)})
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        ok_reg, reg_msg, _ = await ensure_platform_registered(db, user, game)
        if not ok_reg:
            raise HTTPException(status_code=409, detail=f"Redemption held. {reg_msg}")
    else:
        db_user = await db.users.find_one({"_id": ObjectId(user["id"])})
        accounts = (db_user or {}).get("platform_accounts") or {}
        if not any(a.get("status") == "registered" for a in accounts.values()):
            raise HTTPException(
                status_code=409,
                detail="Redemption held. No registered game platform on file — deposit to at least one game before redeeming.",
            )

    success, message, redemption_id = await currency_service.create_redemption_request(
        user_id=user["id"],
        user_email=user["email"],
        game_credits=data.game_credits,
        btc_address=data.btc_address
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Force admin-hold state: NO auto-payout. Compliance officer must approve
    # every redemption in /admin/compliance → Payout Queue.
    try:
        await db["redemption_requests"].update_one(
            {"_id": ObjectId(redemption_id)},
            {"$set": {"status": "hold_admin_review", "held_at": datetime.now(timezone.utc).isoformat()}},
        )
    except Exception as e:
        logging.error(f"Failed to mark redemption on hold: {e}")

    # AML event + threshold checks
    await record_aml_event(
        db,
        user_id=user["id"],
        event_type="redemption_request",
        amount_usd=amount_usd,
        metadata={"redemption_id": redemption_id, "btc_address": data.btc_address, "credits": data.game_credits},
    )

    # Stamp the redemption with the fee breakdown so admin payout matches what
    # we already promised the player and the ledger.
    try:
        await db["redemption_requests"].update_one(
            {"_id": ObjectId(redemption_id)},
            {"$set": {
                "gross_usd": amount_usd,
                "net_payout_usd": net_payout_usd,
                "fee_usd": fee_usd,
                "fee_rate": _rev_rates["btc"],
            }},
        )
    except Exception as e:
        logger.warning(f"Could not stamp fee on redemption {redemption_id}: {e}")

    # Revenue ledger entry — house keeps `fee_usd` on this redemption
    await record_revenue(
        db,
        kind="btc",
        user_id=user["id"],
        gross_usd=amount_usd,
        fee_usd=fee_usd,
        net_usd=net_payout_usd,
        rate=_rev_rates["btc"],
        ref_id=redemption_id,
        ref_kind="btc_redemption",
        metadata={"btc_address": data.btc_address, "credits": data.game_credits},
    )

    return {
        "success": True,
        "message": message + " Held pending compliance officer review.",
        "redemption_id": redemption_id,
        "amount_usd": amount_usd,           # gross (credits → USD before fee)
        "net_payout_usd": net_payout_usd,   # what player actually receives in BTC value
        "fee_usd": fee_usd,                 # house keep
        "fee_rate": _rev_rates["btc"],
        "status": "hold_admin_review",
    }

@api_router.get("/redemption/history")
async def get_redemption_history(request: Request):
    """Get user's redemption history"""
    user = await get_current_user(request)
    
    redemptions = await db.redemption_requests.find(
        {"user_id": user["id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return redemptions

@api_router.get("/currency/balance")
async def get_currency_balance(request: Request):
    """Get user's dual-currency balance"""
    user = await get_current_user(request)
    
    if not currency_service:
        raise HTTPException(status_code=503, detail="Currency service not initialized")
    
    balance = await currency_service.get_user_balance(user["id"])
    
    if not balance:
        raise HTTPException(status_code=404, detail="User not found")
    
    return balance

# ============================================
# Games Endpoints
# ============================================
@api_router.get("/games")
async def get_games():
    games = await db.games.find({"is_active": True}, {"_id": 1, "name": 1, "logo_url": 1, "game_url": 1, "description": 1, "accent_color": 1, "is_active": 1, "created_at": 1}).to_list(100)
    return [{"id": str(g["_id"]), **{k: v for k, v in g.items() if k != "_id"}} for g in games]

@api_router.get("/games/all")
async def get_all_games(request: Request):
    await get_admin_user(request)
    games = await db.games.find({}, {"_id": 1, "name": 1, "logo_url": 1, "game_url": 1, "description": 1, "accent_color": 1, "is_active": 1, "created_at": 1}).to_list(100)
    return [{"id": str(g["_id"]), **{k: v for k, v in g.items() if k != "_id"}} for g in games]

@api_router.post("/games")
async def create_game(data: GameCreate, request: Request):
    await get_admin_user(request)
    game_doc = {
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.games.insert_one(game_doc)
    return {"id": str(result.inserted_id), **game_doc}

@api_router.put("/games/{game_id}")
async def update_game(game_id: str, data: GameUpdate, request: Request):
    await get_admin_user(request)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No data to update")
    await db.games.update_one({"_id": ObjectId(game_id)}, {"$set": update_data})
    game = await db.games.find_one({"_id": ObjectId(game_id)})
    return {"id": str(game["_id"]), **{k: v for k, v in game.items() if k != "_id"}}

@api_router.delete("/games/{game_id}")
async def delete_game(game_id: str, request: Request):
    await get_admin_user(request)
    await db.games.delete_one({"_id": ObjectId(game_id)})
    return {"message": "Game deleted"}

# Payment Info
@api_router.get("/packages")
async def get_deposit_info():
    return {
        "min_deposit": MIN_DEPOSIT,
        "suggestions": DEPOSIT_SUGGESTIONS,
        "rate": "1:1"  # Dollar for dollar
    }

# Stripe Checkout
@api_router.post("/checkout/create")
async def create_checkout(data: CheckoutRequest, request: Request):
    user = await get_current_user(request)
    
    # Validate amount (min $1)
    if data.amount < MIN_DEPOSIT:
        raise HTTPException(status_code=400, detail=f"Minimum deposit is ${MIN_DEPOSIT}")

    # Geoblock gate: block deposits from prohibited sweepstakes states.
    from services.compliance import check_geoblock
    from services.compliance.geoblock import client_ip_from_request, record_geoblock_event
    client_ip = client_ip_from_request(request)
    blocked, geo_reason, detected_state = await check_geoblock(client_ip)
    await record_geoblock_event(
        db, user_id=user["id"], ip=client_ip, state=detected_state,
        blocked=blocked, context="checkout/create",
    )
    if blocked:
        raise HTTPException(status_code=451, detail=f"Deposits unavailable in your region ({geo_reason}).")
    
    # Dollar for dollar - credits equal amount
    credits = data.amount
    
    game = await db.games.find_one({"_id": ObjectId(data.game_id)})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # JIT platform registration: ensure user is registered on the target game
    # platform BEFORE money is moved. If registration fails, hold the deposit
    # and an admin alert is emitted by ensure_platform_registered().
    ok_reg, reg_msg, platform_uid = await ensure_platform_registered(db, user, game)
    if not ok_reg:
        raise HTTPException(
            status_code=409,
            detail=f"Deposit held. {reg_msg}",
        )
    
    # Create Stripe checkout
    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=os.environ["STRIPE_API_KEY"], webhook_url=webhook_url)
    
    success_url = f"{data.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{data.origin_url}/payment/cancel"
    
    checkout_request = CheckoutSessionRequest(
        amount=data.amount,
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "user_id": user["id"],
            "user_email": user["email"],
            "amount": str(data.amount),
            "game_id": data.game_id,
            "game_name": game["name"],
            "account_name": data.account_name,
            "credits": str(credits)
        }
    )
    
    session = await stripe_checkout.create_checkout_session(checkout_request)
    
    # Create transaction record
    transaction = {
        "user_id": user["id"],
        "user_email": user["email"],
        "amount": data.amount,
        "credits": credits,
        "game_id": data.game_id,
        "game_name": game["name"],
        "account_name": data.account_name,
        "payment_method": "stripe",
        "status": "pending",
        "payment_status": "initiated",
        "session_id": session.session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.payment_transactions.insert_one(transaction)
    
    return {"url": session.url, "session_id": session.session_id}

@api_router.get("/checkout/status/{session_id}")
async def get_checkout_status(session_id: str, request: Request):
    # Auth gate — raises 401 if no valid session cookie
    await get_current_user(request)
    
    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=os.environ["STRIPE_API_KEY"], webhook_url=webhook_url)
    
    status = await stripe_checkout.get_checkout_status(session_id)
    
    # Update transaction
    transaction = await db.payment_transactions.find_one({"session_id": session_id})
    if transaction and transaction.get("payment_status") != "paid":
        new_status = "completed" if status.payment_status == "paid" else ("failed" if status.status == "expired" else "pending")
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"status": new_status, "payment_status": status.payment_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        # Add credits if paid
        if status.payment_status == "paid" and transaction.get("payment_status") != "paid":
            await db.users.update_one(
                {"_id": ObjectId(transaction["user_id"])},
                {"$inc": {"credits": transaction["credits"]}}
            )

        # Distributor Pool payout (belt + suspenders: webhook may have missed)
        if status.payment_status == "paid":
            try:
                await _trigger_pool_payout(session_id)
            except Exception as e:
                logging.error(f"Pool payout trigger (status path) error: {e}")
    
    game = await db.games.find_one({"_id": ObjectId(transaction["game_id"])}) if transaction else None
    
    return {
        "status": status.status,
        "payment_status": status.payment_status,
        "amount": status.amount_total / 100,
        "game_url": game["game_url"] if game else None,
        "game_name": game["name"] if game else None,
        "account_name": transaction["account_name"] if transaction else None
    }

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("Stripe-Signature")
    
    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=os.environ["STRIPE_API_KEY"], webhook_url=webhook_url)
    
    try:
        webhook_response = await stripe_checkout.handle_webhook(body, signature)
        
        if webhook_response.payment_status == "paid":
            transaction = await db.payment_transactions.find_one({"session_id": webhook_response.session_id})
            if transaction and transaction.get("payment_status") != "paid":
                # Update transaction status
                await db.payment_transactions.update_one(
                    {"session_id": webhook_response.session_id},
                    {"$set": {"status": "completed", "payment_status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                
                # DUAL-CURRENCY FLOW: Create Sugar Token purchase + Grant bonus Game Credits
                if currency_service:
                    try:
                        success, msg, purchase_id, bonus_id = await currency_service.process_purchase_with_bonus(
                            user_id=transaction["user_id"],
                            user_email=transaction["user_email"],
                            amount_usd=transaction["amount"],
                            purchase_type=PurchaseType.STRIPE_CARD,
                            payment_reference=webhook_response.session_id
                        )
                        
                        if success:
                            logger.info(f"✅ Dual-currency grant: {transaction['user_email']} - {msg}")
                        else:
                            logger.error(f"❌ Dual-currency grant failed: {msg}")
                    except Exception as e:
                        logger.error(f"Dual-currency processing error: {str(e)}")
                
                # BACKWARD COMPATIBILITY: Also update old credits field
                await db.users.update_one(
                    {"_id": ObjectId(transaction["user_id"])},
                    {"$inc": {"credits": transaction["credits"]}}
                )

                # Distributor Pool payout (idempotent)
                await _trigger_pool_payout(webhook_response.session_id)

                # AML event for deposit (CTR/SAR threshold tracking)
                try:
                    from services.compliance import record_aml_event
                    await record_aml_event(
                        db,
                        user_id=str(transaction.get("user_id")),
                        event_type="deposit",
                        amount_usd=float(transaction.get("amount") or 0),
                        metadata={"session_id": webhook_response.session_id, "method": "stripe"},
                    )
                except Exception as e:
                    logger.error(f"AML record (stripe webhook) error: {e}")
        
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return {"status": "error"}


async def _trigger_pool_payout(session_id: str) -> None: 
    """Idempotent trigger for distributor-pool P2P transfer.

    Called from both the Stripe webhook and the /checkout/status redirect
    (belt + suspenders). The conditional update ensures exactly-once execution.
    """
    claimed = await db.payment_transactions.update_one(
        {"session_id": session_id, "payment_status": "paid", "payout_triggered_at": {"$exists": False}},
        {"$set": {"payout_triggered_at": datetime.now(timezone.utc).isoformat()}},
    )
    if claimed.modified_count == 0:
        return  # Already triggered by the other handler.

    tx = await db.payment_transactions.find_one({"session_id": session_id})
    if not tx:
        return

    user = await db.users.find_one({"_id": ObjectId(tx["user_id"])})
    recipient = (user or {}).get("game_username") or tx.get("account_name") or ""
    platform = (tx.get("game_name") or "").lower().replace(" ", "_") or tx.get("game_id", "")
    amount = float(tx.get("credits") or tx.get("amount") or 0)

    if not recipient or amount <= 0:
        await db.admin_alerts.insert_one({
            "type": "pool_payout_missing_data",
            "session_id": session_id,
            "user_id": tx.get("user_id"),
            "message": "Cannot run pool payout — missing recipient/amount.",
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return

    ok, msg, detail = await execute_pool_transfer(db, recipient, amount, platform)
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {
            "payout_status": "completed" if ok else "failed",
            "payout_message": msg,
            "payout_proxy_id": detail.get("proxy_id"),
            "payout_proxy_label": detail.get("proxy_label"),
            "payout_completed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    if not ok:
        await db.admin_alerts.insert_one({
            "type": "pool_payout_failed",
            "session_id": session_id,
            "user_id": tx.get("user_id"),
            "user_email": tx.get("user_email"),
            "recipient": recipient,
            "amount": amount,
            "platform": platform,
            "proxy_id": detail.get("proxy_id"),
            "proxy_label": detail.get("proxy_label"),
            "message": msg,
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

# Manual Payment (Admin creates for Cash App, Chime, Crypto)
@api_router.post("/admin/payments/manual")
async def create_manual_payment(data: ManualPaymentRequest, request: Request):
    await get_admin_user(request)
    
    user = await db.users.find_one({"_id": ObjectId(data.user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    game = await db.games.find_one({"_id": ObjectId(data.game_id)})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    transaction = {
        "user_id": data.user_id,
        "user_email": user["email"],
        "amount": data.amount,
        "credits": data.credits,
        "game_id": data.game_id,
        "game_name": game["name"],
        "account_name": data.account_name,
        "payment_method": data.payment_method,
        "status": "completed",
        "payment_status": "paid",
        "notes": data.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.payment_transactions.insert_one(transaction)
    
    # DUAL-CURRENCY FLOW: Create Sugar Token purchase + Grant bonus Game Credits
    if currency_service:
        try:
            success, msg, purchase_id, bonus_id = await currency_service.process_purchase_with_bonus(
                user_id=data.user_id,
                user_email=user["email"],
                amount_usd=data.amount,
                purchase_type=PurchaseType.MANUAL_ADMIN,
                payment_reference=f"manual_{data.payment_method}"
            )
            
            if success:
                logger.info(f"✅ Admin manual payment: {user['email']} - {msg}")
            else:
                logger.error(f"❌ Admin manual payment failed: {msg}")
        except Exception as e:
            logger.error(f"Admin payment dual-currency error: {str(e)}")
    
    # BACKWARD COMPATIBILITY: Also update old credits field
    await db.users.update_one(
        {"_id": ObjectId(data.user_id)},
        {"$inc": {"credits": data.credits}}
    )
    
    return {"id": str(result.inserted_id), "message": "Payment recorded and credits added"}

# Admin Endpoints
@api_router.get("/admin/users")
async def get_all_users(request: Request):
    await get_admin_user(request)
    users = await db.users.find({}, {"_id": 1, "email": 1, "name": 1, "role": 1, "credits": 1, "age_verified": 1, "game_accounts": 1, "game_password": 1, "created_at": 1}).to_list(1000)
    return [{"id": str(u["_id"]), **{k: v for k, v in u.items() if k != "_id"}} for u in users]

@api_router.put("/admin/users/{user_id}")
async def update_user(user_id: str, data: UserUpdate, request: Request):
    await get_admin_user(request)
    update_data = {}
    if data.game_accounts is not None:
        update_data["game_accounts"] = data.game_accounts
    if data.game_password is not None:
        update_data["game_password"] = data.game_password
    
    if update_data:
        await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
    
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    return {"id": str(user["_id"]), **{k: v for k, v in user.items() if k not in ["_id", "password_hash"]}}

@api_router.get("/admin/transactions")
async def get_all_transactions(request: Request):
    await get_admin_user(request)
    transactions = await db.payment_transactions.find({}).sort("created_at", -1).to_list(1000)
    return [{"id": str(t["_id"]), **{k: v for k, v in t.items() if k != "_id"}} for t in transactions]

@api_router.get("/admin/stats")
async def get_admin_stats(request: Request):
    await get_admin_user(request)
    
    total_users = await db.users.count_documents({})
    total_transactions = await db.payment_transactions.count_documents({})
    completed_transactions = await db.payment_transactions.count_documents({"status": "completed"})
    
    # Calculate total revenue
    pipeline = [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    revenue_result = await db.payment_transactions.aggregate(pipeline).to_list(1)
    total_revenue = revenue_result[0]["total"] if revenue_result else 0
    
    return {
        "total_users": total_users,
        "total_transactions": total_transactions,
        "completed_transactions": completed_transactions,
        "total_revenue": total_revenue
    }

@api_router.put("/admin/users/{user_id}/credits")
async def update_user_credits(user_id: str, credits: float, request: Request):
    await get_admin_user(request)
    await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"credits": credits}})
    return {"message": "Credits updated"}

# Payment Info Endpoints
@api_router.get("/payment/crypto-info")
async def get_crypto_info():
    return {
        "btc_address": os.environ.get("CRYPTO_WALLET_ADDRESS", ""),
        "lightning_address": os.environ.get("LIGHTNING_ADDRESS", ""),
        "instructions": "Send payment via Bitcoin or Lightning Network and contact support with transaction ID"
    }

@api_router.get("/payment/card-info")
async def get_card_info():
    from services.revenue import get_rates
    rates = await get_rates(db)
    keep = rates["cashtag"]
    return {
        "tag": os.environ.get("CARD_PAYMENT_TAG", "$SugarCitySweeps"),
        "instructions": "Send payment via Cash App or Chime and include your game tag in the note",
        "fee_rate": keep,
        "fee_disclosure": (
            f"A {int(keep*100)}% processing fee is applied to Cash App / Chime deposits. "
            f"Example: $25 sent = {round(25 * (1 - keep), 2)} game credits. "
            "Use a card deposit for full-value credit."
        ),
    }

# User Transactions
@api_router.get("/user/transactions")
async def get_user_transactions(request: Request):
    user = await get_current_user(request)
    transactions = await db.payment_transactions.find({"user_id": user["id"]}).sort("created_at", -1).to_list(100)
    return [{"id": str(t["_id"]), **{k: v for k, v in t.items() if k != "_id"}} for t in transactions]

# Root
@api_router.get("/")
async def root():
    return {"message": "WAH-LAH API"}

# Lightweight health endpoint — NO DB, NO imports. Used by Cloudflare/uptime
# monitors and keep-alive pingers so the container stays warm and doesn't
# cold-boot crash (which was throwing intermittent 520s in production).
@api_router.get("/health")
async def health():
    return {"status": "ok", "service": "wah-lah", "ts": datetime.now(timezone.utc).isoformat()}

# ============ GAME MIDDLEWARE ENDPOINTS ============

# Bitcoin Webhook Handler
@api_router.post("/webhooks/bitcoin")
async def bitcoin_webhook(request: Request):
    """Handle incoming Bitcoin payment webhooks from BTCPay/CoinGate"""
    try:
        payload = await request.json()
        
        if not middleware_manager or not middleware_manager.webhook_handler:
            raise HTTPException(status_code=503, detail="Middleware not initialized")
        
        success, msg = await middleware_manager.webhook_handler.handle_webhook(request, payload)
        
        if success:
            return {"status": "success", "message": msg}
        else:
            raise HTTPException(status_code=400, detail=msg)
    
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Withdrawal Request
class WithdrawalRequest(BaseModel):
    game_id: str
    amount_usd: float
    btc_address: str

@api_router.post("/withdraw/request")
async def request_withdrawal(withdrawal: WithdrawalRequest, request: Request):
    """Request a Bitcoin withdrawal — gated by geoblock → OFAC → KYC → admin-hold."""
    try:
        user = await get_current_user(request)

        # ================ MASTER BTC KILL SWITCH ================
        from services.feature_flags import get_flag as _ff_flag
        if not await _ff_flag(db, "btc_payouts_enabled"):
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Bitcoin withdrawals are disabled. Check back soon.",
                    "btc_enabled": False,
                },
            )

        # ============ COMPLIANCE GATES (same chain as /redemption/request) ============
        from services.compliance import (
            check_btc_address,
            check_geoblock,
            record_aml_event,
        )
        from services.compliance.geoblock import client_ip_from_request, record_geoblock_event
        from services.compliance.ofac import record_ofac_hit
        from services.compliance.kyc import is_user_cleared_for

        # Gate 1: geoblock
        client_ip = client_ip_from_request(request)
        blocked, geo_reason, detected_state = await check_geoblock(client_ip)
        await record_geoblock_event(
            db, user_id=user["id"], ip=client_ip, state=detected_state,
            blocked=blocked, context="withdraw/request",
        )
        if blocked:
            raise HTTPException(status_code=451, detail=f"Withdrawals unavailable in your region ({geo_reason}).")

        # Gate 2: OFAC
        flagged, ofac_reason = await check_btc_address(withdrawal.btc_address)
        if flagged:
            await record_ofac_hit(db, user_id=user["id"], btc_address=withdrawal.btc_address, context="withdraw/request")
            raise HTTPException(status_code=451, detail=f"Recipient address blocked ({ofac_reason}).")

        # Gate 3: tiered KYC
        cleared, kyc_reason, req_tier = await is_user_cleared_for(db, user["id"], withdrawal.amount_usd)
        if not cleared:
            raise HTTPException(
                status_code=402,
                detail={
                    "message": f"KYC required for withdrawals ≥ ${withdrawal.amount_usd:.0f}. Complete {req_tier} verification to continue.",
                    "required_tier": req_tier,
                    "kyc_initiate_endpoint": "/api/ext/compliance/kyc/initiate",
                    "reason": kyc_reason,
                },
            )

        if not middleware_manager or not middleware_manager.payout_engine:
            raise HTTPException(status_code=503, detail="Withdrawal system not available")
        
        # Get game and platform info
        game = await db.games.find_one({"id": withdrawal.game_id}, {"_id": 0})
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        platform_id = game.get("platform_id", "unknown")
        
        # Get user's game account
        game_accounts = user.get("game_accounts", {})
        game_account = game_accounts.get(withdrawal.game_id, {})
        player_id = game_account.get("username", "")
        
        if not player_id:
            raise HTTPException(
                status_code=400,
                detail=f"No game account configured for {game['name']}. Contact admin to set up your account."
            )
        
        # Calculate credits (1:1 ratio)
        credits = withdrawal.amount_usd

        # Record AML event — every withdrawal request, whether or not it's executed.
        await record_aml_event(
            db,
            user_id=user["id"],
            event_type="redemption_request",
            amount_usd=float(withdrawal.amount_usd),
            metadata={"btc_address": withdrawal.btc_address, "game_id": withdrawal.game_id, "path": "withdraw/request"},
        )
        
        # Process withdrawal — payout_engine is configured to hold large payouts itself
        # ($500+ threshold defined in payout_engine). We do NOT bypass that.
        success, msg, payout_id = await middleware_manager.process_withdrawal(
            user_id=user["id"],
            game_id=withdrawal.game_id,
            platform_id=platform_id,
            player_id=player_id,
            amount_usd=withdrawal.amount_usd,
            credits=credits,
            btc_address=withdrawal.btc_address,
            user_email=user["email"]
        )
        
        if success:
            return {
                "status": "success",
                "message": msg,
                "payout_id": payout_id
            }
        else:
            raise HTTPException(status_code=400, detail=msg)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Withdrawal request error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Get Pending Payouts (Admin Only)
@api_router.get("/admin/payouts/pending")
async def get_pending_payouts(request: Request):
    """Get all payouts awaiting approval"""
    await get_admin_user(request)
    
    if not middleware_manager or not middleware_manager.payout_engine:
        return []
    
    payouts = await middleware_manager.payout_engine.get_pending_payouts()
    return payouts

# Approve Payout (Admin Only)
@api_router.post("/admin/payouts/{payout_id}/approve")
async def approve_payout(payout_id: str, request: Request):
    """Approve a pending payout"""
    admin = await get_admin_user(request)
    
    if not middleware_manager or not middleware_manager.payout_engine:
        raise HTTPException(status_code=503, detail="Payout system not available")
    
    success, msg = await middleware_manager.payout_engine.approve_payout(
        payout_id=payout_id,
        admin_user_id=admin["id"]
    )
    
    if success:
        return {"status": "success", "message": msg}
    else:
        raise HTTPException(status_code=400, detail=msg)

# Reject Payout (Admin Only)
class RejectPayoutRequest(BaseModel):
    reason: str

@api_router.post("/admin/payouts/{payout_id}/reject")
async def reject_payout(payout_id: str, rejection: RejectPayoutRequest, request: Request):
    """Reject a pending payout"""
    admin = await get_admin_user(request)
    
    if not middleware_manager or not middleware_manager.payout_engine:
        raise HTTPException(status_code=503, detail="Payout system not available")
    
    success, msg = await middleware_manager.payout_engine.reject_payout(
        payout_id=payout_id,
        admin_user_id=admin["id"],
        reason=rejection.reason
    )
    
    if success:
        return {"status": "success", "message": msg}
    else:
        raise HTTPException(status_code=400, detail=msg)

# Get Middleware System Status (Admin Only)
@api_router.get("/admin/middleware/status")
async def get_middleware_status(request: Request):
    """Get status of game middleware systems"""
    await get_admin_user(request)
    
    if not middleware_manager:
        return {"status": "not_initialized"}
    
    status = await middleware_manager.get_system_status()
    
    # Add Firebase status if available
    try:
        from services.firebase_secrets import firebase_secrets
        firebase_status = firebase_secrets.verify_connection()
        status["firebase_secrets"] = firebase_status
    except Exception:
        status["firebase_secrets"] = {"firebase_enabled": False, "credentials_source": "Environment Variables"}
    
    return status

# Sugar Sweeps P2P Transfer (New Master Tank Strategy)
class P2PTransferRequest(BaseModel):
    user_id: str
    platform_id: str  # e.g., "fire_kirin", "juwa", "orion_stars"
    player_id: str    # User's game account ID
    amount: float     # Credits to transfer

@api_router.post("/admin/p2p-transfer")
async def initiate_p2p_transfer(transfer: P2PTransferRequest, request: Request):
    """
    Initiate P2P credit transfer using Sugar Sweeps Master Tank
    
    Admin endpoint to transfer Game Credits to user's platform account via Sugar Sweeps hub.
    This uses the unified "Master Tank" strategy instead of individual platform bots.
    """
    await get_admin_user(request)
    
    if not sugar_sweeps_bridge:
        raise HTTPException(
            status_code=503, 
            detail="Sugar Sweeps Bridge not available. P2P automation disabled."
        )
    
    if not sugar_sweeps_bridge.is_authenticated:
        # Try to reconnect
        success, msg = await sugar_sweeps_bridge.initialize()
        if not success:
            logger.warning(f"Sugar Sweeps bridge init failed: {msg}")
            raise HTTPException(status_code=503, detail="Sugar Sweeps bridge offline. P2P automation temporarily unavailable.")
    
    try:
        # Get user to verify they have enough credits
        user = await db.users.find_one({"_id": ObjectId(transfer.user_id)}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if user.get("game_credits", 0) < transfer.amount:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient credits. User has {user.get('game_credits', 0)}, needs {transfer.amount}"
            )
        
        # Execute P2P transfer via Sugar Sweeps
        success, msg, tx_id = await sugar_sweeps_bridge.transfer_credits(
            platform_id=transfer.platform_id,
            player_id=transfer.player_id,
            amount=transfer.amount
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=msg)
        
        # Deduct credits from user's account
        await db.users.update_one(
            {"_id": ObjectId(transfer.user_id)},
            {"$inc": {"game_credits": -transfer.amount}}
        )
        
        # Log transfer in database
        await db.p2p_transfers.insert_one({
            "user_id": transfer.user_id,
            "user_email": user["email"],
            "platform_id": transfer.platform_id,
            "player_id": transfer.player_id,
            "amount": transfer.amount,
            "transaction_id": tx_id,
            "status": "completed",
            "timestamp": datetime.now(timezone.utc)
        })
        
        logger.info(f"🎮 P2P Transfer: {transfer.amount} credits → {transfer.player_id} on {transfer.platform_id}")
        
        return {
            "success": True,
            "message": msg,
            "transaction_id": tx_id,
            "remaining_credits": user.get("game_credits", 0) - transfer.amount
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"P2P transfer error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transfer failed: {str(e)}")

@api_router.post("/admin/middleware/inject")
async def manual_credit_injection(request: Request, data: dict):
    """
    Manual credit injection via Playwright (Admin override)
    
    Boss Control: Manually inject credits to a player without waiting for payment
    """
    await get_admin_user(request)
    
    if not middleware_manager:
        raise HTTPException(status_code=503, detail="Middleware not initialized")
    
    platform_id = data.get("platform_id")
    user_id = data.get("user_id")
    player_id = data.get("player_id")
    game_id = data.get("game_id")
    credits = data.get("credits")
    reason = data.get("reason", "Manual admin injection")
    # When admin is reconciling a Cash App / Chime deposit, `source` tells us
    # to apply the house keep fee. For any other reason (bonus, refund) the
    # admin can pass apply_fee=false explicitly.
    source = (data.get("source") or "").lower()
    apply_house_fee = bool(data.get("apply_fee", source in ("cashapp", "chime", "cashtag")))
    
    if not all([platform_id, user_id, player_id, credits]):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    try:
        # Get user info
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # ---------- HOUSE FEE (Cash App / Chime convenience fee) ----------
        from services.revenue import get_rates as _rget, apply_fee as _rapply, record_revenue as _rrec
        gross_amount = float(credits)
        fee_amount = 0.0
        net_amount = gross_amount
        applied_rate = 0.0
        if apply_house_fee:
            _rates = await _rget(db)
            applied_rate = _rates["cashtag"]
            _split = _rapply(gross_amount, applied_rate)
            net_amount = _split["net_usd"]
            fee_amount = _split["fee_usd"]
        
        # Allocate credits via Playwright (use NET amount — what the player actually gets)
        success, msg = await middleware_manager.allocate_credits(
            user_id=user_id,
            game_id=game_id or platform_id,
            platform_id=platform_id,
            player_id=player_id,
            amount_usd=net_amount
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=msg)
        
        # Revenue ledger entry — house keeps `fee_amount` on this deposit
        if apply_house_fee and fee_amount > 0:
            await _rrec(
                db,
                kind="cashtag",
                user_id=user_id,
                gross_usd=gross_amount,
                fee_usd=fee_amount,
                net_usd=net_amount,
                rate=applied_rate,
                ref_id=None,
                ref_kind="cashtag_deposit",
                metadata={
                    "source": source or "cashapp",
                    "player_id": player_id,
                    "platform_id": platform_id,
                    "reason": reason,
                },
            )
        
        # Create manual grant record for audit trail (use NET — credits actually delivered)
        if currency_service:
            await currency_service.grant_bonus_credits(
                user_id=user_id,
                user_email=user["email"],
                game_credits=int(net_amount),
                grant_type=BonusGrantType.ADMIN_GRANT,
                metadata={
                    "platform_id": platform_id,
                    "player_id": player_id,
                    "reason": reason,
                    "manual_injection": True,
                    "gross_amount": gross_amount,
                    "fee_amount": fee_amount,
                    "fee_rate": applied_rate,
                    "source": source or None,
                },
            )

        logger.info(
            f"👑 ADMIN INJECTION: {player_id} got {net_amount} credits "
            f"(gross={gross_amount}, fee={fee_amount}@{applied_rate*100:.0f}%) on {platform_id}"
        )

        return {
            "success": True,
            "message": f"Injected {net_amount} credits to {player_id}",
            "platform": platform_id,
            "gross_usd": gross_amount,
            "net_credits": net_amount,
            "fee_usd": fee_amount,
            "fee_rate": applied_rate,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual injection error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Injection failed: {str(e)}")


@api_router.post("/admin/cashtag/reconcile")
async def admin_cashtag_reconcile(request: Request):
    """
    Admin reconciles a Cash App / Chime deposit.

    Player sent USD to $jrs092393 → admin verifies → calls this with
    {user_id, amount_usd, source: 'cashapp'|'chime', note}.

    Applies the CASHTAG_KEEP_RATE house fee, credits the NET to the player's
    wallet, writes the fee to the revenue ledger.
    """
    admin = await get_admin_user(request)
    data = await request.json()

    user_id = data.get("user_id")
    amount_usd = data.get("amount_usd")
    source = (data.get("source") or "cashapp").lower()
    note = data.get("note", "")
    apply_house_fee = bool(data.get("apply_fee", True))

    if not user_id or amount_usd is None:
        raise HTTPException(status_code=400, detail="user_id and amount_usd are required")
    try:
        gross = float(amount_usd)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="amount_usd must be a number")
    if gross <= 0:
        raise HTTPException(status_code=400, detail="amount_usd must be positive")
    if source not in ("cashapp", "chime", "cashtag"):
        raise HTTPException(status_code=400, detail="source must be cashapp, chime, or cashtag")

    try:
        user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        user_doc = await db.users.find_one({"id": user_id})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    from services.revenue import get_rates as _rget, apply_fee as _rapply, record_revenue as _rrec
    import uuid as _uuid
    rates = await _rget(db)
    rate = rates["cashtag"] if apply_house_fee else 0.0
    split = _rapply(gross, rate)
    net_credits = split["net_usd"]
    fee_usd = split["fee_usd"]

    await db.users.update_one(
        {"_id": user_doc["_id"]},
        {"$inc": {"game_credits": net_credits}},
    )

    tx_id = str(_uuid.uuid4())
    await db.payment_transactions.insert_one({
        "id": tx_id,
        "user_id": str(user_doc["_id"]),
        "user_email": user_doc.get("email"),
        "kind": "cashtag_deposit",
        "source": source,
        "gross_usd": gross,
        "net_credits": net_credits,
        "fee_usd": fee_usd,
        "fee_rate": rate,
        "note": note,
        "reconciled_by": admin.get("email"),
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    if fee_usd > 0:
        await _rrec(
            db,
            kind="cashtag",
            user_id=str(user_doc["_id"]),
            gross_usd=gross,
            fee_usd=fee_usd,
            net_usd=net_credits,
            rate=rate,
            ref_id=tx_id,
            ref_kind="cashtag_deposit",
            metadata={"source": source, "note": note, "reconciled_by": admin.get("email")},
        )

    return {
        "success": True,
        "transaction_id": tx_id,
        "gross_usd": gross,
        "net_credits": net_credits,
        "fee_usd": fee_usd,
        "fee_rate": rate,
        "user_balance_after": user_doc.get("game_credits", 0) + net_credits,
    }


@api_router.post("/admin/middleware/restart/{platform_id}")
async def restart_platform_bot(platform_id: str, request: Request):
    """Restart Playwright bot for a specific platform"""
    await get_admin_user(request)
    
    if not middleware_manager:
        raise HTTPException(status_code=503, detail="Middleware not initialized")
    
    try:
        bridge = middleware_manager.get_bridge(platform_id)
        
        if not bridge:
            raise HTTPException(status_code=404, detail=f"No bridge found for platform: {platform_id}")
        
        # Close existing session
        await bridge.close()
        
        # Reinitialize
        success, msg = await bridge.initialize()
        
        if not success:
            raise HTTPException(status_code=500, detail=f"Restart failed: {msg}")
        
        logger.info(f"🔄 Platform bot restarted: {platform_id}")
        
        return {
            "success": True,
            "message": f"Bot restarted for {platform_id}",
            "status": msg
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Restart error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Restart failed: {str(e)}")



# ============ LEGAL PAGES ============

from fastapi.responses import HTMLResponse
from pathlib import Path

@api_router.get("/legal/terms", response_class=HTMLResponse)
async def terms_of_service():
    """Serve Terms of Service page"""
    try:
        with open(Path(__file__).parent / "static" / "terms.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Terms of Service page not found")

@api_router.get("/legal/privacy", response_class=HTMLResponse)
async def privacy_policy():
    """Serve Privacy Policy page"""
    try:
        with open(Path(__file__).parent / "static" / "privacy.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Privacy Policy page not found")

@api_router.get("/legal/responsible-gaming", response_class=HTMLResponse)
async def responsible_gaming():
    """Serve Responsible Gaming page"""
    try:
        with open(Path(__file__).parent / "static" / "responsible-gaming.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Responsible Gaming page not found")

app.include_router(api_router)

# Revenue admin router — fee rates + P&L ledger (Justin's money dashboard)
from routes.revenue_admin import register_revenue_admin_routes  # noqa: E402
_revenue_admin_router = APIRouter(prefix="/api")
register_revenue_admin_routes(_revenue_admin_router, db, get_admin_user)
app.include_router(_revenue_admin_router)

# Feature extensions router (password reset, 2FA, promo codes, referrals, VIP tiers,
# support tickets, enhanced analytics)
app.include_router(build_extensions_router(db, get_current_user, get_admin_user))

# Just-In-Time platform registration router (ensures a user is registered on
# each game platform before deposits/redemptions are accepted)
app.include_router(build_platform_router(db, get_current_user, get_admin_user))

# Distributor Proxy Pool router (Hybrid Buffer Strategy — rotation of Sugar Sweeps
# distributor accounts with health filter, safety caps, auto-cooldown, failover)
app.include_router(build_distributor_pool_router(db, get_admin_user))

# Nerve Center — mission-control aggregated ops dashboard
app.include_router(build_nerve_center_router(db, get_admin_user))

# Compliance router — KYC (Persona + manual), OFAC, Geoblock, AML, payout queue
from routes.compliance import build_compliance_router  # noqa: E402
app.include_router(build_compliance_router(db, get_current_user, get_admin_user))

# Boss Mode — the Genie sidekick (admin-only agentic chat over Claude Sonnet 4.5)
from routes.boss_genie import build_boss_router  # noqa: E402
app.include_router(build_boss_router(db, get_admin_user))

# Gift card redemptions + Pilot Launch Checklist
from routes.gift_cards import build_giftcard_router  # noqa: E402
app.include_router(build_giftcard_router(db, get_current_user, get_admin_user))

# CORS Configuration
cors_origins_str = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
if cors_origins_str.strip() == "*":
    allowed_origins = ["*"]
    use_credentials = False
else:
    allowed_origins = [origin.strip() for origin in cors_origins_str.split(",")]
    use_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=use_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Canonical Host Redirect (kill the "jit" preview URL in prod)
# ============================================================
# When ENFORCE_CANONICAL_HOST=true, any request with a Host header that
# doesn't match CANONICAL_HOST gets 301-redirected to the canonical domain.
# Disabled by default so the dev/preview container keeps working.
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.responses import RedirectResponse  # noqa: E402


class CanonicalHostMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        canonical = os.environ.get("CANONICAL_HOST", "wah-lah.com").lower()
        host = (request.headers.get("host") or "").split(":")[0].lower()

        # Hosts that always pass through unchanged:
        preview_ok = (
            host.endswith(".preview.emergentagent.com")
            or host.endswith(".emergent.sh")
            or host.endswith(".svc.cluster.local")
        )
        allowed = {canonical, f"www.{canonical}", "localhost", "127.0.0.1", "0.0.0.0"}
        if host in allowed or preview_ok:
            return await call_next(request)

        # CRITICAL: Never redirect API calls or non-idempotent methods. A 301 on
        # a POST loses the request body (login credentials, checkout payload, etc).
        # Only redirect top-level browser navigation (GET/HEAD of HTML pages).
        if (
            request.url.path.startswith("/api/")
            or request.method not in ("GET", "HEAD")
            or request.url.path in ("/api/health", "/health")
        ):
            return await call_next(request)

        # Legacy env flag still honored if someone wants to force-disable redirection.
        if os.environ.get("ENFORCE_CANONICAL_HOST", "true").lower() == "false":
            return await call_next(request)

        target = f"https://{canonical}{request.url.path}"
        if request.url.query:
            target += f"?{request.url.query}"
        return RedirectResponse(url=target, status_code=301)


app.add_middleware(CanonicalHostMiddleware)

# ============================================================
# Serve React SPA from /app/frontend_build (built in Docker stage 1).
# Registered LAST so /api/* routers above match first.
# ============================================================
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

FRONTEND_DIR = os.environ.get("FRONTEND_DIR", "/app/frontend_build")
if os.path.isdir(FRONTEND_DIR):
    _static_assets = os.path.join(FRONTEND_DIR, "static")
    if os.path.isdir(_static_assets):
        app.mount("/static", StaticFiles(directory=_static_assets), name="frontend_static")
    _index_html = os.path.join(FRONTEND_DIR, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Real files at repo root (favicon.ico, manifest.json, robots.txt,
        # logo.png, etc.) are served directly. Everything else falls back
        # to index.html so React Router can take over (/boss, /games, ...).
        if full_path:
            candidate = os.path.join(FRONTEND_DIR, full_path)
            if os.path.isfile(candidate):
                return FileResponse(candidate)
        return FileResponse(_index_html)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Background task for Sugar Sweeps Bridge initialization
async def initialize_sugar_sweeps_bridge():
    """Initialize Sugar Sweeps Bridge in background to not block startup"""
    global sugar_sweeps_bridge
    try:
        if sugar_sweeps_bridge:
            success, msg = await sugar_sweeps_bridge.initialize()
            if success:
                logger.info(f"🍬 Sugar Sweeps Bridge ONLINE: {msg}")
            else:
                logger.warning(f"⚠️  Sugar Sweeps Bridge failed: {msg}")
    except Exception as e:
        logger.error(f"Sugar Sweeps Bridge initialization error: {str(e)}")

# Seed data on startup
@app.on_event("startup")
async def startup_event():
    # Playwright readiness check — lazy/passive. We only verify the module
    # is importable; we do NOT launch chromium here. Launching on every
    # cold-boot caused OOM crashes on the hosted container (intermittent 520).
    # Real browser spin-up happens on-demand inside the distributor pool and
    # sugar_sweeps_bridge when a payout actually needs it.
    try:
        import importlib
        importlib.import_module("playwright.async_api")
        logger.info("✓ Playwright module importable (lazy launch mode).")
    except Exception as _e:
        logger.warning(
            "⚠ Playwright module NOT importable (%s). "
            "Distributor Pool Ping/Test-Transfer will fail until you run: "
            "bash /app/scripts/install_playwright_production.sh",
            _e,
        )

    # Create indexes
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    try:
        await db.users.create_index("referral_code", unique=True, sparse=True)
        await db.promo_codes.create_index("code", unique=True)
        await db.password_resets.create_index("token", unique=True)
        await db.password_resets.create_index("expires_at", expireAfterSeconds=0)
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")
    
    # Seed admin — and purge any stale admin accounts whose email does not
    # match the current ADMIN_EMAIL so only the canonical admin exists.
    # Emails are normalized to lowercase because /auth/login compares lowercase.
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@wah-lah.com").lower().strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "SugarCity2024!")

    # Remove stale admins (old rebrand holdovers + any accidentally-stored
    # mixed-case duplicates of the current admin email).
    await db.users.delete_many({
        "role": "admin",
        "email": {"$not": {"$regex": f"^{re.escape(admin_email)}$", "$options": "i"}}
    })

    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Admin",
            "role": "admin",
            "credits": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"Admin user created: {admin_email}")
    else:
        # Ensure existing user is an admin and password matches
        updates = {}
        if existing.get("role") != "admin":
            updates["role"] = "admin"
        if not verify_password(admin_password, existing["password_hash"]):
            updates["password_hash"] = hash_password(admin_password)
        if updates:
            await db.users.update_one({"email": admin_email}, {"$set": updates})
    
    # Seed default games
    games_count = await db.games.count_documents({})
    if games_count == 0:
        default_games = [
            {
                "id": "fire_kirin",
                "name": "Fire Kirin",
                "platform_id": "fire_kirin",
                "logo_url": "https://customer-assets.emergentagent.com/job_project-build-52/artifacts/yy7vuitz_download%20%285%29.jpeg",
                "game_url": "https://firekirin.xyz/download",
                "description": "Underwater adventure fishing game",
                "is_active": True,
                "accent_color": "#00ff00"
            },
            {
                "id": "juwa",
                "name": "Juwa",
                "platform_id": "juwa",
                "logo_url": "https://customer-assets.emergentagent.com/job_project-build-52/artifacts/zca7nng8_juwa.jpeg",
                "game_url": "https://dl.juwa777.com/",
                "description": "Classic casino slots experience",
                "is_active": True,
                "accent_color": "#ffd700"
            },
            {
                "id": "juwa2",
                "name": "Juwa 2",
                "platform_id": "juwa2",
                "logo_url": "https://customer-assets.emergentagent.com/job_project-build-52/artifacts/yfu87og5_download%20%283%29.jpeg",
                "game_url": "https://m.juwa2.com/",
                "description": "Next generation slots",
                "is_active": True,
                "accent_color": "#ff4444"
            },
            {
                "id": "ultra_panda",
                "name": "Ultra Panda",
                "platform_id": "ultra_panda",
                "logo_url": "https://customer-assets.emergentagent.com/job_project-build-52/artifacts/npa0nxre_download%20%284%29.jpeg",
                "game_url": "https://www.ultrapanda.mobi/",
                "description": "Premium panda slots",
                "is_active": True,
                "accent_color": "#00ff00"
            },
            {
                "id": "panda_master",
                "name": "Panda Master",
                "platform_id": "panda_master",
                "logo_url": "/game-logos/panda-master.svg",
                "game_url": "https://play.pandamaster.vip",
                "description": "Panda themed sweepstakes",
                "is_active": True,
                "accent_color": "#00d4ff"
            },
            {
                "id": "orion_stars",
                "name": "Orion Stars",
                "platform_id": "orion_stars",
                "logo_url": "/game-logos/orion-stars.svg",
                "game_url": "https://play.orionstars.vip",
                "description": "Space-themed sweepstakes",
                "is_active": True,
                "accent_color": "#4444ff"
            },
            {
                "id": "game_vault",
                "name": "Game Vault",
                "platform_id": "game_vault",
                "logo_url": "/game-logos/game-vault.svg",
                "game_url": "https://download.gamevault999.com",
                "description": "Premium game collection",
                "is_active": True,
                "accent_color": "#44ff44"
            },
        ]
        for game in default_games:
            game["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.games.insert_many(default_games)
        logger.info("Default games seeded")
    
    # Initialize Game Middleware Manager
    global middleware_manager
    global bonus_service
    
    try:
        config_path = os.path.join(ROOT_DIR, "config", "platforms.json")
        middleware_manager = GameMiddlewareManager(config_path, db)
        
        # Initialize in background
        import asyncio
        asyncio.create_task(middleware_manager.initialize())
        
        logger.info("Game Middleware Manager initialization started")
    except Exception as e:
        logger.error(f"Failed to start middleware manager: {str(e)}")
    
    # Initialize Bonus Service
    try:
        bonus_service = BonusService(db)
        logger.info("Bonus Service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize bonus service: {str(e)}")
    
    # Initialize Currency Service
    global currency_service
    try:
        currency_service = CurrencyService(db)
        logger.info("Currency Service initialized (Dual-currency sweepstakes compliance)")
    except Exception as e:
        logger.error(f"Failed to initialize currency service: {str(e)}")
    
    # Initialize Sugar Sweeps Bridge (Master Tank for P2P automation)
    # SKIPS gracefully when SUGAR_SWEEPS_USERNAME / PASSWORD are not set, so
    # cold-boot is quiet on Fly until the operator provides distributor creds.
    global sugar_sweeps_bridge
    if os.environ.get("SUGAR_SWEEPS_USERNAME") and os.environ.get("SUGAR_SWEEPS_PASSWORD"):
        try:
            sugar_sweeps_bridge = SugarSweepsBridge()
            asyncio.create_task(initialize_sugar_sweeps_bridge())
            logger.info("Sugar Sweeps Bridge initialization started in background")
        except Exception as e:
            logger.warning(f"Sugar Sweeps Bridge not available: {str(e)}")
            sugar_sweeps_bridge = None
    else:
        logger.info(
            "Sugar Sweeps Bridge skipped (SUGAR_SWEEPS_USERNAME / PASSWORD not set). "
            "P2P transfers will use the HTTP distributor pool via /api/distributor-pool/* instead."
        )
        sugar_sweeps_bridge = None
    
    # Write test credentials
    os.makedirs("/app/memory", exist_ok=True)
    with open("/app/memory/test_credentials.md", "w") as f:
        f.write("# Test Credentials\n\n")
        f.write("## Admin User\n")
        f.write(f"- Email: {admin_email}\n")
        f.write(f"- Password: {admin_password}\n")
        f.write("- Role: admin\n\n")
        f.write("## Auth Endpoints\n")
        f.write("- POST /api/auth/register\n")
        f.write("- POST /api/auth/login\n")
        f.write("- POST /api/auth/logout\n")
        f.write("- GET /api/auth/me\n")

@app.on_event("shutdown")
async def shutdown_db_client():
    if middleware_manager and middleware_manager.initialized:
        await middleware_manager.shutdown()
    client.close()
