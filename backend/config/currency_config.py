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

def requires_kyc(amount_usd: float) -> bool:
    """Check if redemption requires KYC review"""
    return amount_usd >= KYC_THRESHOLD_USD
