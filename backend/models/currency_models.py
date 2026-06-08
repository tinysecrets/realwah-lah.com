"""
Dual-Currency Models for Legal Sweepstakes Compliance

SUGAR TOKENS: Purchased digital product ($1 = 100 tokens)
GAME CREDITS: Free sweepstakes entries (bonus with purchase or AMOE)
"""

from pydantic import BaseModel
from typing import Optional, Literal
from enum import Enum

class PurchaseType(str, Enum):
    """Type of purchase transaction"""
    STRIPE_CARD = "stripe_card"
    BITCOIN = "bitcoin"
    MANUAL_ADMIN = "manual_admin"

class BonusGrantType(str, Enum):
    """Type of bonus credit grant"""
    PURCHASE_BONUS = "purchase_bonus"  # Bonus from Sugar Token purchase
    AMOE_DAILY = "amoe_daily"  # Daily free credits (AMOE)
    AMOE_MAIL = "amoe_mail"  # Mail-in entry
    PROMO_CODE = "promo_code"  # Promotional code
    ADMIN_GRANT = "admin_grant"  # Manual admin grant
    REFERRAL = "referral"  # Referral bonus
    VIP_BONUS = "vip_bonus"  # VIP tier bonus

class SugarTokenPurchase(BaseModel):
    """Record of Sugar Token purchase (the legal product)"""
    id: str
    user_id: str
    user_email: str
    amount_usd: float  # Purchase price
    sugar_tokens: int  # Tokens purchased (amount_usd * 100)
    purchase_type: PurchaseType
    payment_reference: Optional[str] = None  # Stripe session ID or BTC tx hash
    status: Literal["pending", "completed", "failed", "refunded"] = "pending"
    created_at: str
    completed_at: Optional[str] = None

class BonusCreditGrant(BaseModel):
    """Record of Game Credit bonus grant (sweepstakes entries)"""
    id: str
    user_id: str
    user_email: str
    game_credits: int  # Credits granted
    grant_type: BonusGrantType
    source_purchase_id: Optional[str] = None  # Links to SugarTokenPurchase if applicable
    metadata: Optional[dict] = None  # Additional context (promo code, referrer, etc.)
    status: Literal["pending", "granted", "expired", "revoked"] = "pending"
    created_at: str
    granted_at: Optional[str] = None
    
    # Audit trail for compliance
    injected_to_platform: bool = False
    platform_id: Optional[str] = None
    platform_tx_id: Optional[str] = None
    injected_at: Optional[str] = None

class UserBalance(BaseModel):
    """User's dual-currency balance"""
    user_id: str
    sugar_tokens: int = 0  # Purchased product (cannot be redeemed for cash)
    game_credits: int = 0  # Sweepstakes entries (can be redeemed)
    last_updated: str

class RedemptionRequest(BaseModel):
    """User request to redeem Game Credits for Bitcoin"""
    id: str
    user_id: str
    user_email: str
    game_credits: int  # Credits being redeemed
    amount_usd: float  # Equivalent USD value (credits / 100)
    btc_address: str
    status: Literal["pending", "approved", "processing", "completed", "rejected"] = "pending"
    requires_kyc: bool = False  # True if amount >= $500
    reviewed_by: Optional[str] = None  # Admin ID who reviewed
    platform_deduction_verified: bool = False
    created_at: str
    approved_at: Optional[str] = None
    completed_at: Optional[str] = None
    rejection_reason: Optional[str] = None

class AMOEClaimRecord(BaseModel):
    """Record of AMOE (Alternate Method of Entry) claims"""
    id: str
    user_id: str
    user_email: str
    claim_type: Literal["daily_login", "mail_in", "social_promo"] = "daily_login"
    credits_granted: int
    claimed_at: str
    next_eligible_claim: str  # When user can claim again (24hrs later)
