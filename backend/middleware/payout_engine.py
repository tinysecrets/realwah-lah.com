import os
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from uuid import uuid4
from dataclasses import dataclass
import requests

logger = logging.getLogger(__name__)


@dataclass
class PayoutRequest:
    """Encapsulates all data needed to process a payout."""
    user_id: str
    game_id: str
    platform_id: str
    amount_usd: float
    credits: float
    btc_address: str
    user_email: str

class PayoutEngine:
    """
    Handles Bitcoin payouts for user withdrawals.
    Includes approval workflow for large amounts.
    """
    
    def __init__(self, btc_config: Dict[str, Any], db):
        self.btc_config = btc_config
        self.db = db
        self.gateway_type = btc_config.get("gateway_type", "btcpay")
        self.approval_threshold = btc_config.get("payout_approval_threshold_usd", 500)
        self.manual_approval_required = btc_config.get("manual_approval_required", True)
        
        # BTC Gateway credentials
        self.gateway_api_url = os.environ.get("BTC_GATEWAY_API_URL", "")
        self.gateway_api_key = os.environ.get("BTC_GATEWAY_API_KEY", "")
        
        logger.info(f"PayoutEngine initialized (gateway={self.gateway_type}, threshold=${self.approval_threshold})")
    
    async def initiate_payout(
        self,
        user_id: str,
        game_id: str,
        platform_id: str,
        amount_usd: float,
        credits: float,
        btc_address: str,
        user_email: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Initiate a Bitcoin payout.
        Returns: (success: bool, message: str, payout_id: Optional[str])
        """
        req = PayoutRequest(
            user_id=user_id,
            game_id=game_id,
            platform_id=platform_id,
            amount_usd=amount_usd,
            credits=credits,
            btc_address=btc_address,
            user_email=user_email,
        )
        return await self._process_payout_request(req)
    
    async def _process_payout_request(self, req: PayoutRequest) -> Tuple[bool, str, Optional[str]]:
        """Core payout processing logic."""
        try:
            payout_id = str(uuid4())
            requires_approval = self.manual_approval_required and req.amount_usd >= self.approval_threshold
            
            if requires_approval:
                return await self._create_pending_payout(payout_id, req)
            else:
                return await self._execute_immediate_payout(payout_id, req)
        
        except Exception as e:
            logger.error(f"Payout initiation error: {str(e)}")
            return False, f"Payout error: {str(e)}", None
    
    async def _create_pending_payout(self, payout_id: str, req: PayoutRequest) -> Tuple[bool, str, Optional[str]]:
        """Create a payout record that requires manual approval."""
        payout_record = {
            "payout_id": payout_id,
            "user_id": req.user_id,
            "game_id": req.game_id,
            "platform_id": req.platform_id,
            "amount_usd": req.amount_usd,
            "credits": req.credits,
            "btc_address": req.btc_address,
            "user_email": req.user_email,
            "status": "pending_approval",
            "created_at": datetime.now(timezone.utc),
            "approved_by": None,
            "approved_at": None,
            "rejection_reason": None
        }
        
        await self.db.pending_payouts.insert_one(payout_record)
        logger.info(f"⚠️ Payout {payout_id} pending approval (${req.amount_usd} > ${self.approval_threshold})")
        return True, f"Payout pending approval (amount ${req.amount_usd} requires manual review)", payout_id
    
    async def _execute_immediate_payout(self, payout_id: str, req: PayoutRequest) -> Tuple[bool, str, Optional[str]]:
        """Process a payout immediately without manual approval."""
        success, msg, tx_hash = await self._execute_payout(
            payout_id,
            req.btc_address,
            req.amount_usd
        )
        
        if success:
            payout_record = {
                "payout_id": payout_id,
                "user_id": req.user_id,
                "game_id": req.game_id,
                "platform_id": req.platform_id,
                "amount_usd": req.amount_usd,
                "credits": req.credits,
                "btc_address": req.btc_address,
                "user_email": req.user_email,
                "status": "completed",
                "btc_tx_hash": tx_hash,
                "created_at": datetime.now(timezone.utc),
                "completed_at": datetime.now(timezone.utc)
            }
            
            await self.db.completed_payouts.insert_one(payout_record)
            logger.info(f"✅ Payout {payout_id} completed: ${req.amount_usd} to {req.btc_address}")
            return True, "Payout completed successfully", payout_id
        else:
            return False, msg, payout_id
    
    async def _execute_payout(
        self,
        payout_id: str,
        btc_address: str,
        amount_usd: float
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Execute the actual BTC payout via gateway.
        Returns: (success: bool, message: str, tx_hash: Optional[str])
        """
        try:
            if self.gateway_type == "btcpay":
                return await self._btcpay_payout(payout_id, btc_address, amount_usd)
            elif self.gateway_type == "coingate":
                return await self._coingate_payout(payout_id, btc_address, amount_usd)
            else:
                return False, f"Unsupported gateway type: {self.gateway_type}", None
        
        except Exception as e:
            logger.error(f"Payout execution error: {str(e)}")
            return False, f"Payout execution error: {str(e)}", None
    
    async def _btcpay_payout(self, payout_id: str, btc_address: str, amount_usd: float) -> Tuple[bool, str, Optional[str]]:
        """Execute payout via BTCPay Server"""
        try:
            if not self.gateway_api_url or not self.gateway_api_key:
                return False, "BTCPay Server credentials not configured", None
            
            # BTCPay Server Payout API
            url = f"{self.gateway_api_url}/api/v1/stores/{os.environ.get('BTCPAY_STORE_ID')}/payouts"
            
            headers = {
                "Authorization": f"token {self.gateway_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "destination": btc_address,
                "amount": str(amount_usd),
                "paymentMethod": "BTC",
                "description": f"Sugar City Sweeps Withdrawal - {payout_id}"
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200 or response.status_code == 201:
                data = response.json()
                tx_hash = data.get("transactionHash") or data.get("id")
                return True, "BTCPay payout successful", tx_hash
            else:
                error_msg = f"BTCPay error: {response.status_code} - {response.text[:200]}"
                logger.error(error_msg)
                return False, error_msg, None
        
        except Exception as e:
            logger.error(f"BTCPay payout error: {str(e)}")
            return False, f"BTCPay error: {str(e)}", None
    
    async def _coingate_payout(self, payout_id: str, btc_address: str, amount_usd: float) -> Tuple[bool, str, Optional[str]]:
        """Execute payout via CoinGate"""
        try:
            if not self.gateway_api_key:
                return False, "CoinGate API key not configured", None
            
            url = "https://api.coingate.com/v2/withdrawals"
            
            headers = {
                "Authorization": f"Token {self.gateway_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "address": btc_address,
                "amount": amount_usd,
                "currency": "USD",
                "platform_currency": "BTC",
                "note": f"Sugar City Sweeps - {payout_id}"
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200 or response.status_code == 201:
                data = response.json()
                tx_hash = data.get("txid") or data.get("id")
                return True, "CoinGate payout successful", tx_hash
            else:
                error_msg = f"CoinGate error: {response.status_code} - {response.text[:200]}"
                logger.error(error_msg)
                return False, error_msg, None
        
        except Exception as e:
            logger.error(f"CoinGate payout error: {str(e)}")
            return False, f"CoinGate error: {str(e)}", None
    
    async def approve_payout(self, payout_id: str, admin_user_id: str) -> Tuple[bool, str]:
        """Approve a pending payout"""
        try:
            # Get pending payout
            payout = await self.db.pending_payouts.find_one({"payout_id": payout_id})
            
            if not payout:
                return False, "Payout not found"
            
            if payout["status"] != "pending_approval":
                return False, f"Payout status is {payout['status']}, not pending"
            
            # Execute payout
            success, msg, tx_hash = await self._execute_payout(
                payout_id,
                payout["btc_address"],
                payout["amount_usd"]
            )
            
            if success:
                # Update payout record
                await self.db.pending_payouts.update_one(
                    {"payout_id": payout_id},
                    {
                        "$set": {
                            "status": "approved",
                            "approved_by": admin_user_id,
                            "approved_at": datetime.now(timezone.utc),
                            "btc_tx_hash": tx_hash,
                            "completed_at": datetime.now(timezone.utc)
                        }
                    }
                )
                
                logger.info(f"✅ Payout {payout_id} approved by {admin_user_id}")
                return True, "Payout approved and executed"
            else:
                return False, f"Payout execution failed: {msg}"
        
        except Exception as e:
            logger.error(f"Payout approval error: {str(e)}")
            return False, f"Approval error: {str(e)}"
    
    async def reject_payout(self, payout_id: str, admin_user_id: str, reason: str) -> Tuple[bool, str]:
        """Reject a pending payout"""
        try:
            result = await self.db.pending_payouts.update_one(
                {"payout_id": payout_id, "status": "pending_approval"},
                {
                    "$set": {
                        "status": "rejected",
                        "approved_by": admin_user_id,
                        "approved_at": datetime.now(timezone.utc),
                        "rejection_reason": reason
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"❌ Payout {payout_id} rejected by {admin_user_id}: {reason}")
                return True, "Payout rejected"
            else:
                return False, "Payout not found or already processed"
        
        except Exception as e:
            logger.error(f"Payout rejection error: {str(e)}")
            return False, f"Rejection error: {str(e)}"
    
    async def get_pending_payouts(self) -> list:
        """Get all pending payouts requiring approval"""
        try:
            payouts = await self.db.pending_payouts.find(
                {"status": "pending_approval"},
                {"_id": 0}
            ).sort("created_at", 1).to_list(100)
            
            return payouts
        
        except Exception as e:
            logger.error(f"Get pending payouts error: {str(e)}")
            return []
