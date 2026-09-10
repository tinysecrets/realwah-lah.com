"""
Currency Configuration for Legal Sweepstakes

Defines the ratios and thresholds for the dual-currency system.
"""

# Sugar Token Configuration
SUGAR_TOKEN_RATIO = 100  # $1 USD = 100 Sugar Tokens

# Bonus Game Credit Configuration
BONUS_MATCH_PERCENTAGE = 100  # 100% match (buy 100 tokens = get 100 credits free)

# AMOE (Alternate Method of Entry) Configuration
AMOE_DAILY_CREDITS = 100  # Free credits every 24 hours
AMOE_COOLDOWN_HOURS = 24  # Hours between AMOE claims

# Redemption Configuration
MIN_REDEMPTION_CREDITS = 5000  # Minimum 5,000 credits ($50 USD)
KYC_THRESHOLD_USD = 500  # Redemptions >= $500 require manual review
CREDITS_TO_USD_RATIO = 100  # 100 credits = $1 USD

# Platform denomination — game backends (Fire Kirin, Juwa, Orion Stars, ...)
# display and accept DOLLARS, not internal credits. 100 internal Game Credits
# = $1.00 on the platform. EVERY transfer out of WAH-LAH converts through the
# helpers below; nothing else in the codebase divides by 100.
PLATFORM_CREDITS_PER_USD = 100

# Purchase Limits (for compliance)
MIN_PURCHASE_USD = 1.00
MAX_PURCHASE_USD_PER_DAY = 5000
MAX_PURCHASE_USD_PER_HOUR = 1000

def calculate_sugar_tokens(amount_usd: float) -> int:
    """Calculate Sugar Tokens from USD amount"""
    return int(amount_usd * SUGAR_TOKEN_RATIO)

def calculate_bonus_credits(sugar_tokens: int) -> int:
    """Calculate bonus Game Credits from Sugar Token purchase"""
    return int(sugar_tokens * (BONUS_MATCH_PERCENTAGE / 100))

def calculate_redemption_usd(game_credits: int) -> float:
    """Calculate USD value of Game Credits for redemption"""
    return round(game_credits / CREDITS_TO_USD_RATIO, 2)

def credits_to_platform_amount(game_credits: float) -> float:
    """Internal Game Credits -> dollars to type/send on the game backend.

    $22 of value lives as 2,200 internal credits but MUST go to the platform
    as 22.00 — the games display dollars. Sending raw credits overpays 100x.
    """
    return round(float(game_credits or 0) / PLATFORM_CREDITS_PER_USD, 2)

def platform_amount_to_credits(platform_amount: float) -> int:
    """Dollars on the game backend -> internal Game Credits."""
    return int(round(float(platform_amount or 0) * PLATFORM_CREDITS_PER_USD))

def requires_kyc(amount_usd: float) -> bool:
    """Check if redemption requires KYC review"""
    return amount_usd >= KYC_THRESHOLD_USD
