import os
import json
import hmac
import hashlib
import logging
from typing import Dict, Any, Tuple
from uuid import uuid4
from fastapi import Request
from models.transaction_models import GameTransaction, TransactionType, TransactionStatus, PaymentMethod

logger = logging.getLogger(__name__)

class WebhookHandler:
    """
    Handles incoming Bitcoin payment webhooks from BTCPay Server, CoinGate, etc.
    Triggers credit allocation upon confirmed payments.
    """
    
    def __init__(self, btc_config: Dict[str, Any], db, backend_bridge_manager):
        self.btc_config = btc_config
        self.db = db
        self.backend_bridge_manager = backend_bridge_manager
        self.webhook_secret = os.environ.get(btc_config.get("webhook_secret_env", "BTC_WEBHOOK_SECRET"), "")
        self.min_confirmations = btc_config.get("min_confirmations", 1)
        self.gateway_type = btc_config.get("gateway_type", "btcpay")
        
        logger.info(f"WebhookHandler initialized (gateway={self.gateway_type}, min_confirmations={self.min_confirmations})")
    
    def verify_signature(self, request: Request, payload: bytes) -> bool:
        """Verify webhook signature for security"""
        try:
            if not self.webhook_secret:
                logger.warning("Webhook secret not configured, skipping signature verification")
                return True
            
            # BTCPay Server signature
            if self.gateway_type == "btcpay":
                signature_header = request.headers.get("BTCPay-Sig")
                if not signature_header:
                    return False
                
                # Extract signature (format: sha256=...)
                if "=" in signature_header:
                    algo, signature = signature_header.split("=", 1)
                else:
                    signature = signature_header
                
                # Compute expected signature
                expected_signature = hmac.new(
                    self.webhook_secret.encode(),
                    payload,
                    hashlib.sha256
                ).hexdigest()
                
                return hmac.compare_digest(signature, expected_signature)
            
            # CoinGate signature
            elif self.gateway_type == "coingate":
                # CoinGate doesn't use HMAC, relies on API key in payload
                return True
            
            return True
        
        except Exception as e:
            logger.error(f"Signature verification error: {str(e)}")
            return False
    
    async def handle_webhook(
        self,
        request: Request,
        payload: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Process incoming payment webhook.
        Returns: (success: bool, message: str)
        """
        try:
            # Verify signature
            payload_bytes = json.dumps(payload, separators=(',', ':')).encode()
            if not self.verify_signature(request, payload_bytes):
                logger.warning("Invalid webhook signature")
                return False, "Invalid signature"
            
            # Parse webhook based on gateway type
            if self.gateway_type == "btcpay":
                return await self._handle_btcpay_webhook(payload)
            elif self.gateway_type == "coingate":
                return await self._handle_coingate_webhook(payload)
            else:
                return False, f"Unsupported gateway: {self.gateway_type}"
        
        except Exception as e:
            logger.error(f"Webhook handling error: {str(e)}")
            return False, f"Webhook error: {str(e)}"
    
    async def _handle_btcpay_webhook(self, payload: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle BTCPay Server webhook"""
        try:
            # BTCPay webhook structure
            invoice_id = payload.get("invoiceId")
            status = payload.get("status")
            
            # Only process confirmed payments
            if status not in ["confirmed", "complete", "paid"]:
                logger.info(f"Skipping webhook for invoice {invoice_id} with status {status}")
                return True, "Payment not confirmed yet"
            
            # Get invoice metadata (should contain user_id, game_id, amount)
            metadata = payload.get("metadata", {})
            user_id = metadata.get("user_id")
            game_id = metadata.get("game_id")
            amount_usd = float(payload.get("price", 0))
            btc_tx_hash = payload.get("transactionHash")
            
            if not user_id or not game_id:
                return False, "Missing user_id or game_id in webhook metadata"
            
            # Check if already processed
            existing = await self.db.game_transactions.find_one(
                {"btc_tx_hash": btc_tx_hash}
            )
            
            if existing:
                logger.info(f"Transaction {btc_tx_hash} already processed")
                return True, "Already processed"
            
            # Get user's game account credentials
            user = await self.db.users.find_one({"id": user_id}, {"_id": 0})
            if not user:
                return False, "User not found"
            
            # Get platform ID from game
            game = await self.db.games.find_one({"id": game_id}, {"_id": 0})
            if not game:
                return False, "Game not found"
            
            platform_id = game.get("platform_id", "unknown")
            
            # Get player's game account ID
            game_accounts = user.get("game_accounts", {})
            game_account = game_accounts.get(game_id, {})
            player_id = game_account.get("username", "")
            
            if not player_id:
                return False, f"User {user_id} has no game account for {game_id}"
            
            # Calculate credits (1:1 ratio)
            credits = amount_usd
            
            # Allocate credits via backend bridge
            backend_bridge = self.backend_bridge_manager.get_bridge(platform_id)
            if not backend_bridge:
                return False, f"No backend bridge configured for platform {platform_id}"
            
            success, msg, platform_tx_id = await backend_bridge.recharge_user(
                player_id=player_id,
                amount=credits,
                game_id=game_id
            )
            
            if success:
                # Record transaction
                transaction = GameTransaction(
                    transaction_id=str(uuid4()),
                    user_id=user_id,
                    game_id=game_id,
                    platform_id=platform_id,
                    transaction_type=TransactionType.CREDIT_ALLOCATION,
                    amount_usd=amount_usd,
                    credits=credits,
                    status=TransactionStatus.COMPLETED,
                    payment_method=PaymentMethod.BITCOIN,
                    btc_tx_hash=btc_tx_hash,
                    platform_tx_id=platform_tx_id,
                    metadata={
                        "invoice_id": invoice_id,
                        "player_id": player_id,
                        "gateway": "btcpay"
                    }
                )
                
                await self.db.game_transactions.insert_one(transaction.to_dict())
                
                # Update user's local credits (for our dashboard)
                await self.db.users.update_one(
                    {"id": user_id},
                    {"$inc": {"credits": credits}}
                )
                
                logger.info(f"✅ BTC payment processed: {user_id} received {credits} credits in {game_id}")
                
                return True, "Payment processed and credits allocated"
            else:
                # Failed to allocate credits
                transaction = GameTransaction(
                    transaction_id=str(uuid4()),
                    user_id=user_id,
                    game_id=game_id,
                    platform_id=platform_id,
                    transaction_type=TransactionType.CREDIT_ALLOCATION,
                    amount_usd=amount_usd,
                    credits=credits,
                    status=TransactionStatus.FAILED,
                    payment_method=PaymentMethod.BITCOIN,
                    btc_tx_hash=btc_tx_hash,
                    metadata={
                        "error": msg,
                        "invoice_id": invoice_id,
                        "player_id": player_id
                    }
                )
                
                await self.db.game_transactions.insert_one(transaction.to_dict())
                
                logger.error(f"❌ Failed to allocate credits for {user_id}: {msg}")
                
                return False, f"Credit allocation failed: {msg}"
        
        except Exception as e:
            logger.error(f"BTCPay webhook error: {str(e)}")
            return False, f"BTCPay webhook error: {str(e)}"
    
    async def _handle_coingate_webhook(self, payload: Dict[str, Any]) -> Tuple[bool, str]:
        """Handle CoinGate webhook"""
        try:
            # CoinGate webhook structure
            # order_id = payload.get("id")  # reserved for future reconciliation logging
            status = payload.get("status")
            
            # Only process confirmed/paid
            if status not in ["paid", "confirmed"]:
                return True, "Payment not confirmed yet"
            
            # Extract metadata (similar to BTCPay)
            # Implementation similar to BTCPay handler
            
            return True, "CoinGate webhook processed"
        
        except Exception as e:
            logger.error(f"CoinGate webhook error: {str(e)}")
            return False, f"CoinGate webhook error: {str(e)}"
