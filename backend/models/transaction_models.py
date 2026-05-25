from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum

class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    CREDIT_ALLOCATION = "credit_allocation"
    CREDIT_DEDUCTION = "credit_deduction"

class TransactionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"

class PaymentMethod(str, Enum):
    BITCOIN = "bitcoin"
    LIGHTNING = "lightning"
    STRIPE = "stripe"
    CASH_APP = "cash_app"
    CHIME = "chime"

class GameTransaction:
    """Model for tracking all game credit transactions"""
    
    def __init__(
        self,
        transaction_id: str,
        user_id: str,
        game_id: str,
        platform_id: str,
        transaction_type: TransactionType,
        amount_usd: float,
        credits: float,
        status: TransactionStatus,
        payment_method: Optional[PaymentMethod] = None,
        btc_tx_hash: Optional[str] = None,
        platform_tx_id: Optional[str] = None,
        user_balance_before: float = 0.0,
        user_balance_after: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.transaction_id = transaction_id
        self.user_id = user_id
        self.game_id = game_id
        self.platform_id = platform_id
        self.transaction_type = transaction_type
        self.amount_usd = amount_usd
        self.credits = credits
        self.status = status
        self.payment_method = payment_method
        self.btc_tx_hash = btc_tx_hash
        self.platform_tx_id = platform_tx_id
        self.user_balance_before = user_balance_before
        self.user_balance_after = user_balance_after
        self.metadata = metadata or {}
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.approved_by = None
        self.approved_at = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "user_id": self.user_id,
            "game_id": self.game_id,
            "platform_id": self.platform_id,
            "transaction_type": self.transaction_type.value,
            "amount_usd": self.amount_usd,
            "credits": self.credits,
            "status": self.status.value,
            "payment_method": self.payment_method.value if self.payment_method else None,
            "btc_tx_hash": self.btc_tx_hash,
            "platform_tx_id": self.platform_tx_id,
            "user_balance_before": self.user_balance_before,
            "user_balance_after": self.user_balance_after,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None
        }

class PendingPayout:
    """Model for payouts awaiting approval"""
    
    def __init__(
        self,
        payout_id: str,
        user_id: str,
        game_id: str,
        platform_id: str,
        amount_usd: float,
        credits: float,
        btc_address: str,
        user_email: str
    ):
        self.payout_id = payout_id
        self.user_id = user_id
        self.game_id = game_id
        self.platform_id = platform_id
        self.amount_usd = amount_usd
        self.credits = credits
        self.btc_address = btc_address
        self.user_email = user_email
        self.status = TransactionStatus.PENDING_APPROVAL
        self.created_at = datetime.now(timezone.utc)
        self.approved_by = None
        self.approved_at = None
        self.rejection_reason = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "payout_id": self.payout_id,
            "user_id": self.user_id,
            "game_id": self.game_id,
            "platform_id": self.platform_id,
            "amount_usd": self.amount_usd,
            "credits": self.credits,
            "btc_address": self.btc_address,
            "user_email": self.user_email,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejection_reason": self.rejection_reason
        }
