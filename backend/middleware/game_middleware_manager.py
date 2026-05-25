import json
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Any
from .backend_bridge import BackendBridge
from .payout_engine import PayoutEngine
from .webhook_handler import WebhookHandler

logger = logging.getLogger(__name__)


@dataclass
class WithdrawalRequest:
    """Encapsulates all data needed to process a withdrawal."""
    user_id: str
    game_id: str
    platform_id: str
    player_id: str
    amount_usd: float
    credits: float
    btc_address: str
    user_email: str

class GameMiddlewareManager:
    """
    Central manager for all game platform integrations.
    Coordinates SessionManagers, BackendBridges, PayoutEngine, and WebhookHandler.
    """
    
    def __init__(self, config_path: str, db):
        self.db = db
        self.config_path = config_path
        self.config = None
        self.bridges: Dict[str, BackendBridge] = {}
        self.payout_engine: Optional[PayoutEngine] = None
        self.webhook_handler: Optional[WebhookHandler] = None
        self.initialized = False
        
        logger.info("GameMiddlewareManager created")
    
    async def initialize(self) -> bool:
        """Initialize all middleware components"""
        try:
            # Load configuration
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            
            logger.info("Configuration loaded")
            
            # Initialize backend bridges for each enabled platform
            for platform_config in self.config["platforms"]:
                if platform_config.get("enabled", False):
                    platform_id = platform_config["id"]
                    
                    bridge = BackendBridge(platform_config)
                    success, msg = await bridge.initialize()
                    
                    if success:
                        self.bridges[platform_id] = bridge
                        logger.info(f"✅ Bridge initialized for {platform_id}")
                    else:
                        logger.warning(f"⚠️ Failed to initialize bridge for {platform_id}: {msg}")
            
            # Initialize payout engine
            self.payout_engine = PayoutEngine(self.config["bitcoin"], self.db)
            logger.info("✅ PayoutEngine initialized")
            
            # Initialize webhook handler
            self.webhook_handler = WebhookHandler(self.config["bitcoin"], self.db, self)
            logger.info("✅ WebhookHandler initialized")
            
            self.initialized = True
            logger.info("✅ GameMiddlewareManager fully initialized")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Failed to initialize GameMiddlewareManager: {str(e)}")
            return False
    
    def get_bridge(self, platform_id: str) -> Optional[BackendBridge]:
        """Get backend bridge for a platform"""
        return self.bridges.get(platform_id)
    
    async def allocate_credits(
        self,
        user_id: str,
        game_id: str,
        platform_id: str,
        player_id: str,
        amount_usd: float
    ) -> tuple[bool, str]:
        """Allocate credits to a player (called after payment confirmation)"""
        try:
            bridge = self.get_bridge(platform_id)
            if not bridge:
                return False, f"No bridge available for platform {platform_id}"
            
            credits = amount_usd  # 1:1 ratio
            
            success, msg, tx_id = await bridge.recharge_user(
                player_id=player_id,
                amount=credits,
                game_id=game_id
            )
            
            return success, msg
        
        except Exception as e:
            logger.error(f"Credit allocation error: {str(e)}")
            return False, f"Error: {str(e)}"
    
    async def process_withdrawal(
        self,
        user_id: str,
        game_id: str,
        platform_id: str,
        player_id: str,
        amount_usd: float,
        credits: float,
        btc_address: str,
        user_email: str
    ) -> tuple[bool, str, Optional[str]]:
        """Process a withdrawal request."""
        req = WithdrawalRequest(
            user_id=user_id,
            game_id=game_id,
            platform_id=platform_id,
            player_id=player_id,
            amount_usd=amount_usd,
            credits=credits,
            btc_address=btc_address,
            user_email=user_email,
        )
        return await self._execute_withdrawal(req)
    
    async def _verify_player_balance(self, req: WithdrawalRequest):
        """Step 1: Verify player has sufficient balance on the game platform."""
        bridge = self.get_bridge(req.platform_id)
        if not bridge:
            return False, f"No bridge available for platform {req.platform_id}", None
        
        balance_success, balance = await bridge.get_player_balance(req.player_id, req.game_id)
        
        if not balance_success or balance is None:
            return False, "Unable to verify player balance", None
        
        if balance < req.credits:
            return False, f"Insufficient balance. Have {balance}, need {req.credits}", None
        
        return True, "Balance verified", bridge
    
    async def _deduct_game_credits(self, bridge, req: WithdrawalRequest):
        """Step 2: Deduct credits from the game platform."""
        deduct_success, deduct_msg, platform_tx_id = await bridge.deduct_credits(
            player_id=req.player_id,
            amount=req.credits,
            game_id=req.game_id
        )
        
        if not deduct_success:
            return False, f"Failed to deduct credits: {deduct_msg}", None
        
        logger.info(f"✅ Credits deducted from game: {req.player_id} -{req.credits}")
        return True, "Credits deducted", platform_tx_id
    
    async def _execute_withdrawal(self, req: WithdrawalRequest) -> tuple[bool, str, Optional[str]]:
        """Execute the full withdrawal pipeline: verify -> deduct -> payout."""
        try:
            # Step 1: Verify balance
            verified, verify_msg, bridge = await self._verify_player_balance(req)
            if not verified:
                return False, verify_msg, None
            
            # Step 2: Deduct credits from game
            deducted, deduct_msg, platform_tx_id = await self._deduct_game_credits(bridge, req)
            if not deducted:
                return False, deduct_msg, None
            
            # Step 3: Initiate BTC payout
            payout_success, payout_msg, payout_id = await self.payout_engine.initiate_payout(
                user_id=req.user_id,
                game_id=req.game_id,
                platform_id=req.platform_id,
                amount_usd=req.amount_usd,
                credits=req.credits,
                btc_address=req.btc_address,
                user_email=req.user_email
            )
            
            if payout_success:
                return True, payout_msg, payout_id
            else:
                logger.error(f"⚠️ CRITICAL: Credits deducted but payout failed for {req.user_id}. Platform TX: {platform_tx_id}")
                return False, f"Payout failed but credits deducted. Contact support. Ref: {platform_tx_id}", payout_id
        
        except Exception as e:
            logger.error(f"Withdrawal processing error: {str(e)}")
            return False, f"Withdrawal error: {str(e)}", None
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get status of all middleware components"""
        status = {
            "initialized": self.initialized,
            "bridges": {},
            "payout_engine": "initialized" if self.payout_engine else "not initialized",
            "webhook_handler": "initialized" if self.webhook_handler else "not initialized"
        }
        
        for platform_id, bridge in self.bridges.items():
            status["bridges"][platform_id] = bridge.session_manager.get_status()
        
        return status
    
    async def shutdown(self):
        """Gracefully shutdown all components"""
        logger.info("Shutting down GameMiddlewareManager...")
        
        for platform_id, bridge in self.bridges.items():
            await bridge.close()
            logger.info(f"Closed bridge for {platform_id}")
        
        self.initialized = False
        logger.info("✅ GameMiddlewareManager shutdown complete")
