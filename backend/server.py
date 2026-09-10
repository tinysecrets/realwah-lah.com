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
from routes.distributor_admin import build_distributor_admin_router
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
from routes.legal import build_legal_router
from routes.public_stats import build_public_stats_router
from routes.scout import build_scout_router
from routes.competition import build_competition_router, build_competition_admin_router

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
        "(Render dashboard environment, never in git)."
    )
client = AsyncIOMotorClient(mongoodb_uri)
db = client[os.environ.get("DB_NAME", "wahlah_prod")]


@asynccontextmanager
async def lifespan(app):
    """Run startup/shutdown tasks for the FastAPI app."""
    # Initialize Currency Service so AMOE daily free credits (a legal
    # requirement) and balance reads work. Was previously left None, which
    # made /api/amoe/claim-daily always return 503. The deposit path builds
    # its own instance in payment.py, which is why it kept working.
    global currency_service
    try:
        currency_service = CurrencyService(db)
    except Exception:
        logger.exception("Currency service init failed (non-fatal).")

    # Start the on-duty watchdog (24/7 health monitoring + email alerts).
    try:
        from services.on_duty import OnDuty
        global _on_duty
        _on_duty = OnDuty(db)
        _on_duty.start()
    except Exception:
        logger.exception("On-duty watchdog failed to start (non-fatal).")

    # Start the deposit reconciler (settles confirmed BTC deposits even when
    # the BlockCypher webhook was missed). Restart-safe and idempotent.
    try:
        from services.deposit_reconciler import DepositReconciler
        global _deposit_reconciler
        _deposit_reconciler = DepositReconciler(db)
        _deposit_reconciler.start()
    except Exception:
        logger.exception("Deposit reconciler failed to start (non-fatal).")

    # Start the pool resync worker (refreshes each distributor seat's real
    # balance from its hub, then runs a SAFE dry-run rebalance on the fresh
    # picture). Gives the credit rebalancer's floor/sweep rules ground truth.
    try:
        from services.pool_resync import PoolResyncWorker
        global _pool_resync
        _pool_resync = PoolResyncWorker(db)
        _pool_resync.start()
    except Exception:
        logger.exception("Pool resync worker failed to start (non-fatal).")

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

    # TTL index so the token denylist self-cleans (idempotent).
    try:
        await db.revoked_tokens.create_index("expire_at", expireAfterSeconds=0)
    except Exception:
        logger.exception("revoked_tokens TTL index creation failed (non-fatal).")

    # Fail fast on weak auth config (better a loud boot error than silent risk).
    try:
        get_jwt_secret()
    except ValueError as e:
        logger.error("Auth misconfiguration: %s", e)
        raise

    logger.info(
        "Startup: cors_origins=%d trust_proxy_headers=%s cookie_secure=%s cookie_samesite=%s",
        len(cors_origins), TRUST_PROXY_HEADERS, COOKIE_SECURE, COOKIE_SAMESITE,
    )

    yield


app = FastAPI(title="WAH-LAH API", version="1.0.0", lifespan=lifespan)
api_router = APIRouter(prefix="/api")

# Rate limiting: key on the first public-facing IP. Proxy headers
# (CF-Connecting-IP / X-Forwarded-For) are ONLY trusted when the app is
# knowingly running behind the Cloudflare API proxy — otherwise any client
# could spoof its rate-limit identity. Set TRUST_PROXY_HEADERS=true on
# Render (production is always behind the Worker) and leave it unset/false
# everywhere else.
TRUST_PROXY_HEADERS = os.environ.get("TRUST_PROXY_HEADERS", "false").lower() in ("1", "true", "yes")


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Proxy headers honored only when trusted."""
    if TRUST_PROXY_HEADERS:
        cf = request.headers.get("CF-Connecting-IP")
        if cf:
            return cf.strip().split(",")[0].strip()
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
    peer = request.client.host if request.client else ""
    return (peer or "").strip()


if SLOWAPI_AVAILABLE:
    def _rate_key(request: Request) -> str:
        return _client_ip(request) or get_remote_address(request)

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

# CORS Configuration — locked down. Wildcards are rejected when
# allow_credentials is on (browsers would ignore them anyway, and a "*"
# in config signals "not reviewed"). Methods/headers are explicit.
cors_origins = [
    origin.strip().rstrip("/")
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
if "*" in cors_origins:
    raise RuntimeError(
        "CORS_ORIGINS must not contain '*': set explicit origins "
        "(e.g. https://wah-lah.com,https://www.wah-lah.com)."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    max_age=600,
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    """Baseline response headers + optional canonical-host enforcement."""
    if os.environ.get("ENFORCE_CANONICAL_HOST", "false").lower() in ("1", "true", "yes"):
        canonical = os.environ.get("CANONICAL_HOST", "wah-lah.com")
        fwd_host = request.headers.get("X-Forwarded-Host", "")
        host = (fwd_host.split(",")[0].strip() if fwd_host else request.headers.get("host", ""))
        allowed = {canonical, f"www.{canonical}", "api.wah-lah.com"}
        if host and host.split(":")[0].lower() not in allowed and "/health" not in request.url.path:
            return Response(
                content='{"detail":"Unrecognized host."}',
                status_code=421,
                media_type="application/json",
            )
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if COOKIE_SECURE:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
        )
    return response


@app.middleware("http")
async def _admin_audit_log(request: Request, call_next):
    """Append-only audit trail for every admin-surface request."""
    path = request.url.path
    is_admin = "/admin/" in path
    response = await call_next(request)
    if is_admin:
        try:
            await db["admin_access_log"].insert_one({
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "ip": _client_ip(request),
                "user_agent": (request.headers.get("user-agent") or "")[:200],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            logger.exception("Admin audit log write failed.")
    return response

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
_on_duty = None
_deposit_reconciler = None
_pool_resync = None

# JWT Config
JWT_ALGORITHM = "HS256"

# Cookie security: drive from env so we can keep secure=False in local dev
# and secure=True on HTTPS production (wah-lah.com / api.wah-lah.com).
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax").lower()
if COOKIE_SAMESITE not in ("lax", "strict", "none"):
    raise RuntimeError("COOKIE_SAMESITE must be one of: lax, strict, none")
if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
    raise RuntimeError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true (browser rule)")

def get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise ValueError("JWT_SECRET environment variable is required")
    if len(secret) < 32:
        raise ValueError("JWT_SECRET must be at least 32 characters (generate with: python -c 'import secrets; print(secrets.token_urlsafe(48))')")
    return secret

# Password hashing (bcrypt truncates >72 bytes — enforce the cap up front
# so long passwords fail loudly instead of hashing ambiguously).
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError("Password must be 72 bytes or less")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

# JWT Token Management — every token carries a jti so logout / password
# change / admin revoke can denylist it in `revoked_tokens` (TTL-indexed).
def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
        "type": "access",
        "jti": secrets.token_urlsafe(16),
        "iat": datetime.now(timezone.utc).timestamp(),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),
        "iat": datetime.now(timezone.utc).timestamp(),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


async def _is_token_revoked(jti: Optional[str]) -> bool:
    if not jti:
        return False  # legacy tokens without jti predate revocation
    try:
        return await db.revoked_tokens.find_one({"jti": jti}) is not None
    except Exception:
        logger.exception("Revocation lookup failed; failing closed.")
        return True


async def _revoke_token(payload: dict) -> None:
    jti = payload.get("jti")
    if not jti:
        return
    try:
        await db.revoked_tokens.update_one(
            {"jti": jti},
            {"$setOnInsert": {
                "jti": jti,
                "sub": payload.get("sub"),
                "type": payload.get("type"),
                "revoked_at": datetime.now(timezone.utc),
                # Auto-expire the denylist row after 8 days (past max token life).
                "expire_at": datetime.now(timezone.utc) + timedelta(days=8),
            }},
            upsert=True,
        )
    except Exception:
        logger.exception("Token revocation write failed.")


async def revoke_all_user_tokens(user_id: str) -> int:
    """Denylist every outstanding token for a user (compromise response).

    Implemented as a per-user cutoff: tokens issued before `revoked_before`
    are rejected. Returns 1 on success."""
    try:
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"tokens_revoked_before": datetime.now(timezone.utc).isoformat()}},
        )
        return 1
    except Exception:
        logger.exception("revoke_all_user_tokens failed.")
        return 0

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
        if await _is_token_revoked(payload.get("jti")):
            raise HTTPException(status_code=401, detail="Token revoked")
        try:
            user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        cutoff = user.get("tokens_revoked_before")
        if cutoff:
            try:
                iat = payload.get("iat")
                issued = datetime.fromtimestamp(iat, tz=timezone.utc).isoformat() if iat else None
                if issued is None or issued < cutoff:
                    raise HTTPException(status_code=401, detail="Token revoked")
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=401, detail="Token revoked")
        user["id"] = str(user["_id"])
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        user.pop("twofa_secret", None)
        user.pop("twofa_pending_secret", None)
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
    password: str = Field(min_length=1, max_length=72)
    totp_code: Optional[str] = Field(default=None, description="6-digit TOTP when the account has 2FA enabled")

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
    payment_method: str = "bitcoin"

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
    """Generate a unique random master password per user."""
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12))

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
    build_distributor_admin_router(db=db, get_admin_user=get_admin_user)
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
api_router.include_router(build_legal_router())
api_router.include_router(build_public_stats_router(db=db))
api_router.include_router(
    build_scout_router(db=db, get_admin_user=get_admin_user)
)
api_router.include_router(
    build_competition_router(db=db, get_current_user=get_current_user)
)
api_router.include_router(
    build_competition_admin_router(db=db, get_admin_user=get_admin_user)
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
    # Key brute-force tracking on the real client IP (proxy-aware), not the
    # proxy peer — otherwise one shared egress IP locks out every user.
    identifier = f"{_client_ip(request)}:{email}"

    async def _record_failure():
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {
                "$inc": {"count": 1},
                "$set": {"locked_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}
            },
            upsert=True
        )

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
        await _record_failure()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # 2FA is enforced on the PRIMARY login when the account enabled it
    # (previously only the parallel /ext/auth/login-2fa path checked TOTP,
    # so enabling 2FA did not actually protect the account).
    if user.get("twofa_enabled"):
        try:
            import pyotp
            secret = user.get("twofa_secret") or ""
            valid = bool(secret) and bool(data.totp_code) and pyotp.TOTP(secret).verify(data.totp_code, valid_window=1)
        except Exception:
            valid = False
        if not valid:
            await _record_failure()
            raise HTTPException(status_code=401, detail="2FA code required" if not data.totp_code else "Invalid 2FA code")

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
async def logout(request: Request, response: Response):
    # Denylist both tokens so stolen cookies die with the session.
    for cookie_name, kind in (("access_token", "access"), ("refresh_token", "refresh")):
        token = request.cookies.get(cookie_name)
        if token:
            try:
                payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
                if payload.get("type") == kind:
                    await _revoke_token(payload)
            except Exception:
                pass
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


@api_router.get("/onduty/status")
async def onduty_status():
    """Read-only status of the 24/7 on-duty watchdog (public)."""
    global _on_duty
    if _on_duty is None or not _on_duty.last_report:
        return {"ok": None, "time": None, "note": "Watchdog not yet run"}
    return _on_duty.last_report


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
