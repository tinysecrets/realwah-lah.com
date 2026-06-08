import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

class BonusService:
    """
    Handles bonus and promotion logic
    """
    
    def __init__(self, db):
        self.db = db
        
        # Bonus configurations
        self.first_deposit_bonus_percent = 10  # 10% bonus
        self.min_deposit_for_bonus = 20  # Minimum $20 deposit
        self.max_bonus_amount = 100  # Max $100 bonus
    
    async def check_first_deposit_bonus(
        self,
        user_id: str,
        deposit_amount: float
    ) -> tuple[bool, float, str]:
        """
        Check if user qualifies for first deposit bonus.
        Returns: (eligible, bonus_amount, message)
        """
        try:
            # Check if user has any previous successful deposits
            previous_deposits = await self.db.payment_transactions.count_documents({
                "user_id": user_id,
                "type": "deposit",
                "status": "completed"
            })
            
            if previous_deposits > 0:
                return False, 0.0, "First deposit bonus already claimed"
            
            # Check minimum deposit
            if deposit_amount < self.min_deposit_for_bonus:
                return False, 0.0, f"Minimum ${self.min_deposit_for_bonus} deposit required for bonus"
            
            # Calculate bonus
            bonus_amount = deposit_amount * (self.first_deposit_bonus_percent / 100)
            
            # Cap at max bonus
            if bonus_amount > self.max_bonus_amount:
                bonus_amount = self.max_bonus_amount
            
            logger.info(f"First deposit bonus: {user_id} eligible for ${bonus_amount:.2f}")
            
            return True, bonus_amount, f"{self.first_deposit_bonus_percent}% First Deposit Bonus!"
        
        except Exception as e:
            logger.error(f"Error checking first deposit bonus: {str(e)}")
            return False, 0.0, "Error checking bonus eligibility"
    
    async def apply_bonus(
        self,
        user_id: str,
        bonus_amount: float,
        bonus_type: str,
        source_transaction_id: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Apply bonus credits to user account
        """
        try:
            # Update user credits
            result = await self.db.users.update_one(
                {"id": user_id},
                {"$inc": {"credits": bonus_amount}}
            )
            
            if result.modified_count == 0:
                return False, "Failed to apply bonus"
            
            # Log bonus transaction
            bonus_record = {
                "user_id": user_id,
                "type": "bonus",
                "bonus_type": bonus_type,
                "amount": bonus_amount,
                "source_transaction_id": source_transaction_id,
                "status": "completed",
                "created_at": datetime.now(timezone.utc)
            }
            
            await self.db.bonus_transactions.insert_one(bonus_record)
            
            logger.info(f"Bonus applied: {user_id} received ${bonus_amount:.2f} ({bonus_type})")
            
            return True, f"${bonus_amount:.2f} bonus added!"
        
        except Exception as e:
            logger.error(f"Error applying bonus: {str(e)}")
            return False, f"Error applying bonus: {str(e)}"
    
    async def get_user_bonuses(self, user_id: str) -> list:
        """Get all bonuses claimed by user"""
        try:
            bonuses = await self.db.bonus_transactions.find(
                {"user_id": user_id},
                {"_id": 0}
            ).sort("created_at", -1).to_list(100)
            
            return bonuses
        except Exception as e:
            logger.error(f"Error getting user bonuses: {str(e)}")
            return []
