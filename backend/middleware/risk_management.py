"""
Risk Management & Fraud Detection System
Monitors transactions for suspicious patterns

COMPLIANCE: Prevents money laundering, fraud, and abuse
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

class RiskManagementEngine:
    """
    Monitors transactions for fraud and abuse.
    Implements standard financial compliance rules.
    """
    
    def __init__(self, db):
        self.db = db
        
        # Configurable thresholds
        self.config = {
            "max_deposit_per_hour": 1000,  # USD
            "max_deposit_per_day": 5000,  # USD
            "suspicious_velocity_threshold": 5,  # transactions in 10 minutes
            "large_transaction_threshold": 500,  # USD
            "max_withdrawal_attempts": 3,  # per hour
            "velocity_window_minutes": 10
        }
        
        # In-memory tracking
        self.recent_activity = defaultdict(list)
    
    async def check_deposit_risk(
        self,
        user_id: str,
        amount: float,
        payment_method: str
    ) -> Tuple[bool, Optional[str], str]:
        """
        Check if deposit should be allowed.
        
        Returns:
            (allowed: bool, reason: str, risk_level: str)
        """
        
        # Check 1: Amount limits
        if amount > self.config["large_transaction_threshold"]:
            logger.warning(f"⚠️ Large deposit: {user_id} attempting ${amount}")
            # Allow but flag for review
            await self._flag_for_review(user_id, "large_deposit", amount)
        
        # Check 2: Hourly limit
        hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        hourly_total = await self.db.payment_transactions.aggregate([
            {
                "$match": {
                    "user_id": user_id,
                    "type": "deposit",
                    "status": "completed",
                    "created_at": {"$gte": hour_ago.isoformat()}
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]).to_list(1)
        
        hourly_sum = hourly_total[0]["total"] if hourly_total else 0
        
        if hourly_sum + amount > self.config["max_deposit_per_hour"]:
            logger.error(f"🚫 BLOCKED: {user_id} exceeded hourly limit (${hourly_sum + amount})")
            return False, f"Hourly deposit limit of ${self.config['max_deposit_per_hour']} exceeded", "high"
        
        # Check 3: Daily limit
        day_ago = datetime.now(timezone.utc) - timedelta(days=1)
        daily_total = await self.db.payment_transactions.aggregate([
            {
                "$match": {
                    "user_id": user_id,
                    "type": "deposit",
                    "status": "completed",
                    "created_at": {"$gte": day_ago.isoformat()}
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]).to_list(1)
        
        daily_sum = daily_total[0]["total"] if daily_total else 0
        
        if daily_sum + amount > self.config["max_deposit_per_day"]:
            logger.error(f"🚫 BLOCKED: {user_id} exceeded daily limit (${daily_sum + amount})")
            return False, f"Daily deposit limit of ${self.config['max_deposit_per_day']} exceeded", "high"
        
        # Check 4: Velocity (rapid transactions)
        velocity_window = datetime.now(timezone.utc) - timedelta(minutes=self.config["velocity_window_minutes"])
        recent_count = await self.db.payment_transactions.count_documents({
            "user_id": user_id,
            "type": "deposit",
            "created_at": {"$gte": velocity_window.isoformat()}
        })
        
        if recent_count >= self.config["suspicious_velocity_threshold"]:
            logger.error(f"🚫 BLOCKED: {user_id} suspicious velocity ({recent_count} deposits in {self.config['velocity_window_minutes']} min)")
            await self._flag_for_review(user_id, "suspicious_velocity", amount)
            return False, "Too many rapid transactions. Please wait before depositing again.", "critical"
        
        # All checks passed
        return True, None, "low"
    
    async def check_withdrawal_risk(
        self,
        user_id: str,
        amount: float,
        btc_address: str
    ) -> Tuple[bool, Optional[str], str]:
        """
        Check if withdrawal should be allowed.
        
        Returns:
            (allowed: bool, reason: str, risk_level: str)
        """
        
        # Check 1: First withdrawal (extra scrutiny)
        previous_withdrawals = await self.db.completed_payouts.count_documents({
            "user_id": user_id,
            "status": {"$in": ["completed", "approved"]}
        })
        
        if previous_withdrawals == 0:
            logger.info(f"ℹ️ First withdrawal for {user_id}")
            if amount > 100:
                # Flag large first withdrawals for manual review
                await self._flag_for_review(user_id, "first_large_withdrawal", amount)
        
        # Check 2: Withdrawal velocity
        hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_withdrawals = await self.db.pending_payouts.count_documents({
            "user_id": user_id,
            "created_at": {"$gte": hour_ago.isoformat()}
        })
        
        if recent_withdrawals >= self.config["max_withdrawal_attempts"]:
            logger.error(f"🚫 BLOCKED: {user_id} too many withdrawal attempts")
            return False, "Too many withdrawal attempts. Please wait 1 hour.", "high"
        
        # Check 3: Deposit/Withdrawal ratio (potential money laundering)
        total_deposits = await self.db.payment_transactions.aggregate([
            {
                "$match": {
                    "user_id": user_id,
                    "type": "deposit",
                    "status": "completed"
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]).to_list(1)
        
        total_withdrawals = await self.db.completed_payouts.aggregate([
            {
                "$match": {
                    "user_id": user_id,
                    "status": {"$in": ["completed", "approved"]}
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}}
        ]).to_list(1)
        
        deposit_total = total_deposits[0]["total"] if total_deposits else 0
        withdrawal_total = total_withdrawals[0]["total"] if total_withdrawals else 0
        
        # Flag if trying to withdraw more than deposited (impossible unless they won)
        if amount + withdrawal_total > deposit_total * 1.5:  # Allow 50% winnings
            logger.warning(f"⚠️ Suspicious withdrawal ratio: {user_id}")
            await self._flag_for_review(user_id, "suspicious_withdrawal_ratio", amount)
        
        # All checks passed
        return True, None, "low"
    
    async def _flag_for_review(self, user_id: str, reason: str, amount: float):
        """Flag transaction for manual admin review"""
        flag_record = {
            "user_id": user_id,
            "reason": reason,
            "amount": amount,
            "flagged_at": datetime.now(timezone.utc),
            "reviewed": False,
            "action_taken": None
        }
        
        await self.db.risk_flags.insert_one(flag_record)
        logger.warning(f"🚩 FLAGGED: {user_id} - {reason} (${amount})")
    
    async def get_pending_reviews(self) -> List[Dict]:
        """Get all flagged transactions awaiting review"""
        flags = await self.db.risk_flags.find(
            {"reviewed": False},
            {"_id": 0}
        ).sort("flagged_at", -1).to_list(100)
        
        return flags
    
    async def resolve_flag(self, user_id: str, admin_id: str, action: str):
        """Admin resolves a flagged transaction"""
        await self.db.risk_flags.update_many(
            {"user_id": user_id, "reviewed": False},
            {
                "$set": {
                    "reviewed": True,
                    "reviewed_by": admin_id,
                    "reviewed_at": datetime.now(timezone.utc),
                    "action_taken": action
                }
            }
        )
        
        logger.info(f"✅ Risk flag resolved for {user_id} by {admin_id}: {action}")
