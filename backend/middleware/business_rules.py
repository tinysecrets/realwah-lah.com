"""
Business Rules Engine
Configurable logic for bonuses, VIP tiers, promotions

LEGAL USE: Standard promotional and loyalty programs
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class BusinessRulesEngine:
    """
    Manages configurable business logic:
    - Happy hour bonuses
    - VIP tier benefits
    - Promotional campaigns
    - Auto-withdrawal thresholds
    """
    
    def __init__(self, db):
        self.db = db
        self.rules = self.load_rules()
    
    def load_rules(self) -> Dict:
        """Load business rules from configuration"""
        rules_path = Path("/app/backend/config/business_rules.json")
        
        if rules_path.exists():
            with open(rules_path, "r") as f:
                return json.load(f)
        else:
            # Default rules
            return {
                "happy_hour": {
                    "enabled": False,
                    "day_of_week": 5,  # Friday = 5
                    "start_hour": 17,  # 5 PM
                    "end_hour": 20,    # 8 PM
                    "bonus_percentage": 10
                },
                "vip_tiers": {
                    "enabled": True,
                    "tiers": [
                        {
                            "name": "Bronze",
                            "min_lifetime_deposits": 0,
                            "max_lifetime_deposits": 500,
                            "withdrawal_priority": "normal",
                            "bonus_multiplier": 1.0
                        },
                        {
                            "name": "Silver",
                            "min_lifetime_deposits": 500,
                            "max_lifetime_deposits": 2000,
                            "withdrawal_priority": "high",
                            "bonus_multiplier": 1.1
                        },
                        {
                            "name": "Gold",
                            "min_lifetime_deposits": 2000,
                            "max_lifetime_deposits": 10000,
                            "withdrawal_priority": "urgent",
                            "bonus_multiplier": 1.25
                        },
                        {
                            "name": "Diamond",
                            "min_lifetime_deposits": 10000,
                            "max_lifetime_deposits": float('inf'),
                            "withdrawal_priority": "instant",
                            "bonus_multiplier": 1.5
                        }
                    ]
                },
                "auto_withdrawal": {
                    "enabled": True,
                    "threshold_usd": 50,  # Auto-process withdrawals under $50
                    "require_kyc_above": 500  # Require KYC for withdrawals over $500
                },
                "promotions": {
                    "first_deposit": {
                        "enabled": True,
                        "percentage": 10,
                        "min_deposit": 20,
                        "max_bonus": 100
                    },
                    "weekend_bonus": {
                        "enabled": False,
                        "percentage": 5,
                        "days": [6, 0]  # Saturday, Sunday
                    }
                }
            }
    
    def is_happy_hour(self) -> bool:
        """Check if current time is within happy hour"""
        if not self.rules["happy_hour"]["enabled"]:
            return False
        
        now = datetime.now(timezone.utc)
        
        is_correct_day = now.weekday() == self.rules["happy_hour"]["day_of_week"]
        is_correct_hour = (
            self.rules["happy_hour"]["start_hour"] <= now.hour < self.rules["happy_hour"]["end_hour"]
        )
        
        return is_correct_day and is_correct_hour
    
    def calculate_deposit_bonus(self, amount: float, is_first_deposit: bool = False) -> float:
        """
        Calculate bonus for a deposit based on active promotions.
        
        Returns:
            bonus_amount in USD
        """
        bonus = 0.0
        
        # Happy hour bonus
        if self.is_happy_hour():
            happy_hour_bonus = amount * (self.rules["happy_hour"]["bonus_percentage"] / 100)
            bonus += happy_hour_bonus
            logger.info(f"🎉 Happy Hour bonus: ${happy_hour_bonus:.2f}")
        
        # First deposit bonus
        if is_first_deposit and self.rules["promotions"]["first_deposit"]["enabled"]:
            if amount >= self.rules["promotions"]["first_deposit"]["min_deposit"]:
                first_bonus = amount * (self.rules["promotions"]["first_deposit"]["percentage"] / 100)
                first_bonus = min(first_bonus, self.rules["promotions"]["first_deposit"]["max_bonus"])
                bonus += first_bonus
                logger.info(f"🎁 First deposit bonus: ${first_bonus:.2f}")
        
        # Weekend bonus
        weekend_promo = self.rules["promotions"]["weekend_bonus"]
        if weekend_promo["enabled"]:
            now = datetime.now(timezone.utc)
            if now.weekday() in weekend_promo["days"]:
                weekend_bonus = amount * (weekend_promo["percentage"] / 100)
                bonus += weekend_bonus
                logger.info(f"🎊 Weekend bonus: ${weekend_bonus:.2f}")
        
        return bonus
    
    async def get_user_vip_tier(self, user_id: str) -> Optional[Dict]:
        """
        Determine user's VIP tier based on lifetime deposits.
        
        Returns:
            VIP tier dict or None
        """
        if not self.rules["vip_tiers"]["enabled"]:
            return None
        
        # Calculate lifetime deposits
        lifetime_deposits = await self.db.payment_transactions.aggregate([
            {
                "$match": {
                    "user_id": user_id,
                    "type": "deposit",
                    "status": "completed"
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]).to_list(1)
        
        total = lifetime_deposits[0]["total"] if lifetime_deposits else 0
        
        # Find matching tier
        for tier in self.rules["vip_tiers"]["tiers"]:
            if tier["min_lifetime_deposits"] <= total < tier["max_lifetime_deposits"]:
                return {
                    **tier,
                    "current_deposits": total
                }
        
        return None
    
    def should_auto_process_withdrawal(self, amount: float) -> bool:
        """Check if withdrawal should be auto-processed"""
        if not self.rules["auto_withdrawal"]["enabled"]:
            return False
        
        return amount < self.rules["auto_withdrawal"]["threshold_usd"]
    
    def requires_kyc(self, amount: float) -> bool:
        """Check if transaction requires KYC verification"""
        return amount >= self.rules["auto_withdrawal"]["require_kyc_above"]
    
    def save_rules(self):
        """Save current rules to file"""
        rules_path = Path("/app/backend/config/business_rules.json")
        with open(rules_path, "w") as f:
            json.dump(self.rules, f, indent=2)
        logger.info("Business rules saved")
