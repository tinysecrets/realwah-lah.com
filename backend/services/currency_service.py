"""
Currency Service - Handles dual-currency operations for legal sweepstakes compliance

Manages:
- Sugar Token purchases
- Bonus Game Credit grants
- AMOE (Alternate Method of Entry) claims
- Redemption requests
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Dict
from uuid import uuid4
from bson import ObjectId

from config.currency_config import (
    calculate_sugar_tokens,
    calculate_bonus_credits,
    calculate_redemption_usd,
    requires_kyc,
    AMOE_DAILY_CREDITS,
    AMOE_COOLDOWN_HOURS,
    MIN_REDEMPTION_CREDITS,
    CREDITS_TO_USD_RATIO
)
from models.currency_models import (
    PurchaseType,
    BonusGrantType
)

logger = logging.getLogger(__name__)

# Strong references to background distributor-transfer tasks. Without holding a
# reference, CPython can garbage-collect an in-flight asyncio task and silently
# truncate the transfer, leaving the deposit stuck in "in_progress" forever.
_TRANSFER_TASKS: set = set()

class CurrencyService:
    """Manages dual-currency system for legal sweepstakes compliance"""
    
    def __init__(self, db):
        self.db = db
    
    async def create_sugar_token_purchase(
        self,
        user_id: str,
        user_email: str,
        amount_usd: float,
        purchase_type: PurchaseType,
        payment_reference: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Create a Sugar Token purchase record.
        
        This is the PRODUCT that the user is buying.
        Game Credits are granted separately as a BONUS.
        
        Returns: (success, message, purchase_id)
        """
        try:
            sugar_tokens = calculate_sugar_tokens(amount_usd)
            
            purchase_doc = {
                "id": str(uuid4()),
                "user_id": user_id,
                "user_email": user_email,
                "amount_usd": amount_usd,
                "sugar_tokens": sugar_tokens,
                "purchase_type": purchase_type.value,
                "payment_reference": payment_reference,
                "status": "completed",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Insert purchase record
            await self.db.sugar_token_purchases.insert_one(purchase_doc)
            
            # Update user's Sugar Token balance
            await self.db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$inc": {"sugar_tokens": sugar_tokens}}
            )
            
            logger.info(f"✅ Sugar Token purchase: {user_email} bought {sugar_tokens} tokens (${amount_usd})")
            
            return True, f"Purchased {sugar_tokens} Sugar Tokens", purchase_doc["id"]
        
        except Exception as e:
            logger.error(f"Sugar Token purchase error: {str(e)}")
            return False, f"Purchase error: {str(e)}", None
    
    async def grant_bonus_credits(
        self,
        user_id: str,
        user_email: str,
        game_credits: int,
        grant_type: BonusGrantType,
        source_purchase_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Grant Game Credits as a bonus.
        
        This is the FREE SWEEPSTAKES ENTRY that comes with purchase or AMOE.
        
        Returns: (success, message, grant_id)
        """
        try:
            grant_doc = {
                "id": str(uuid4()),
                "user_id": user_id,
                "user_email": user_email,
                "game_credits": game_credits,
                "grant_type": grant_type.value,
                "source_purchase_id": source_purchase_id,
                "metadata": metadata or {},
                "status": "granted",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "granted_at": datetime.now(timezone.utc).isoformat(),
                "injected_to_platform": False,
                "platform_id": None,
                "platform_tx_id": None,
                "injected_at": None
            }
            
            # Insert bonus grant record
            await self.db.bonus_credit_grants.insert_one(grant_doc)
            
            # Update user's Game Credit balance
            await self.db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$inc": {"game_credits": game_credits}}
            )
            
            logger.info(f"✅ Bonus credits granted: {user_email} received {game_credits} credits ({grant_type.value})")
            
            return True, f"Granted {game_credits} Game Credits", grant_doc["id"]
        
        except Exception as e:
            logger.error(f"Bonus credit grant error: {str(e)}")
            return False, f"Grant error: {str(e)}", None
    
    async def process_purchase_with_bonus(
        self,
        user_id: str,
        user_email: str,
        amount_usd: float,
        purchase_type: PurchaseType,
        payment_reference: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Complete flow: Create Sugar Token purchase + Grant bonus Game Credits.
        
        This maintains LEGAL COMPLIANCE by separating the purchase from the bonus.
        
        Returns: (success, message, purchase_id, bonus_grant_id)
        """
        try:
            # Step 1: Create Sugar Token purchase (the PRODUCT)
            purchase_success, purchase_msg, purchase_id = await self.create_sugar_token_purchase(
                user_id, user_email, amount_usd, purchase_type, payment_reference
            )
            
            if not purchase_success:
                return False, purchase_msg, None, None
            
            # Step 2: Calculate and grant bonus Game Credits (the FREE ENTRY)
            sugar_tokens = calculate_sugar_tokens(amount_usd)
            bonus_credits = calculate_bonus_credits(sugar_tokens)
            
            bonus_success, bonus_msg, bonus_id = await self.grant_bonus_credits(
                user_id, user_email, bonus_credits,
                BonusGrantType.PURCHASE_BONUS,
                source_purchase_id=purchase_id,
                metadata={
                    "purchase_amount_usd": amount_usd,
                    "sugar_tokens_purchased": sugar_tokens,
                    "bonus_match_percentage": 100
                }
            )
            
            if not bonus_success:
                logger.error(f"Purchase succeeded but bonus grant failed: {bonus_msg}")
                return True, f"Purchase completed but bonus grant failed: {bonus_msg}", purchase_id, None
            
            logger.info(f"🎉 Complete purchase: {user_email} - ${amount_usd} → {sugar_tokens} tokens + {bonus_credits} bonus credits")
            
            return True, f"Purchase complete: {sugar_tokens} tokens + {bonus_credits} bonus credits", purchase_id, bonus_id
        
        except Exception as e:
            logger.error(f"Purchase with bonus error: {str(e)}")
            return False, f"Error: {str(e)}", None, None

    async def create_pending_btc_purchase(
        self,
        user_id: str,
        user_email: str,
        amount_usd: float,
        btc_address: str,
        btc_satoshis: int,
        btc_usd_rate: float,
        payment_reference: Optional[str] = None,
        expires_at: Optional[str] = None,
        deposit_index: Optional[int] = None,
        platform: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Create a PENDING Sugar Token purchase held until the BTC deposit is
        confirmed on-chain (≥1 confirmation).

        LEGAL MODEL: The shop record must NOT be marked completed until the
        buyer's money has actually arrived on the blockchain. Tokens and bonus
        Game Credits are only credited once the webhook confirms the deposit.

        Returns: (success, message, btc_deposit_id)
        """
        try:
            sugar_tokens = calculate_sugar_tokens(amount_usd)
            now = datetime.now(timezone.utc)

            deposit_id = str(uuid4())
            deposit_doc = {
                "id": deposit_id,
                "user_id": user_id,
                "user_email": user_email,
                "amount_usd": amount_usd,
                "sugar_tokens": sugar_tokens,
                "btc_address": btc_address,
                "btc_satoshis": btc_satoshis,
                "btc_usd_rate": btc_usd_rate,
                "payment_reference": payment_reference,
                "deposit_index": deposit_index,
                "platform": platform,
                "status": "pending",
                "confirmations": 0,
                "tx_hash": None,
                "created_at": now.isoformat(),
                "expires_at": expires_at or (now + timedelta(hours=24)).isoformat(),
                "completed_at": None,
                "webhook_id": None,
            }
            await self.db.btc_deposits.insert_one(deposit_doc)

            # Purchase record exists but is pending — no token/credit delta yet.
            purchase_doc = {
                "id": str(uuid4()),
                "user_id": user_id,
                "user_email": user_email,
                "amount_usd": amount_usd,
                "sugar_tokens": sugar_tokens,
                "purchase_type": PurchaseType.BITCOIN.value,
                "payment_reference": deposit_id,
                "status": "pending",
                "created_at": now.isoformat(),
                "completed_at": None,
            }
            await self.db.sugar_token_purchases.insert_one(purchase_doc)

            logger.info(f"⏳ Pending BTC purchase created: {user_email} ${amount_usd} -> {btc_address}")
            return True, "Deposit address ready — waiting for Bitcoin confirmation", deposit_id

        except Exception as e:
            logger.error(f"Pending BTC purchase error: {str(e)}")
            return False, f"Error: {str(e)}", None

    async def complete_btc_purchase(
        self,
        deposit_id: str,
        tx_hash: str,
        confirmations: int = 1,
        payment_reference: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Finalize a BTC deposit once confirmed on-chain: mark the purchase
        completed, credit Sugar Tokens, and grant bonus Game Credits.

        This is called from the BlockCypher webhook (and the manual admin
        fallback). Idempotent: a deposit in a completed state is a no-op.
        """
        try:
            deposit = await self.db.btc_deposits.find_one({"id": deposit_id})
            if not deposit:
                return False, "Deposit not found"
            if deposit.get("status") == "completed":
                return True, "Deposit already completed"

            user_id = deposit.get("user_id")
            user_email = deposit.get("user_email")
            amount_usd = float(deposit.get("amount_usd") or 0)

            now = datetime.now(timezone.utc)

            # Flip purchase from pending -> completed.
            await self.db.sugar_token_purchases.update_one(
                {"payment_reference": deposit_id},
                {"$set": {
                    "status": "completed",
                    "payment_reference": payment_reference or tx_hash,
                    "completed_at": now.isoformat(),
                }},
            )

            # Credit Sugar Tokens + bonus Game Credits (dual-currency model).
            purchase_success, purchase_msg, purchase_id = await self.create_sugar_token_purchase(
                user_id, user_email, amount_usd, PurchaseType.BITCOIN, payment_reference or tx_hash
            )
            if not purchase_success:
                # Keep deposit pending so a retry can reconcile later.
                return False, purchase_msg

            bonus_credits = calculate_bonus_credits(calculate_sugar_tokens(amount_usd))
            await self.grant_bonus_credits(
                user_id, user_email, bonus_credits,
                BonusGrantType.PURCHASE_BONUS,
                source_purchase_id=purchase_id,
                metadata={"btc_deposit_id": deposit_id, "tx_hash": tx_hash},
            )

            # Mark the deposit completed, atomically guarding against duplicate
            # transfer dispatch (webhook retries must never send credits twice).
            deposit_set = {
                "status": "completed",
                "tx_hash": tx_hash,
                "confirmations": max(confirmations, 1),
                "payment_reference": payment_reference or tx_hash,
                "completed_at": now.isoformat(),
                "pool_transfer_status": "pending",
            }
            await self.db.btc_deposits.update_one(
                {"id": deposit_id, "status": {"$ne": "completed"}},
                {"$set": deposit_set},
            )

            logger.info(f"✅ BTC deposit completed: {user_email} ${amount_usd} tx={tx_hash}")

            # Dispatch the funded Game Credits to the chosen game platform via the
            # distributor proxy pool. Runs in the background so the webhook returns
            # fast; idempotency is enforced by pool_transfer_status on the deposit.
            await self._dispatch_platform_transfer(deposit_id, tx_hash, bonus_credits)
            return True, f"Deposit completed ({amount_usd} USD)"

        except Exception as e:
            logger.error(f"Complete BTC purchase error: {str(e)}")
            return False, f"Error: {str(e)}"

    async def _dispatch_platform_transfer(self, deposit_id: str, tx_hash: str, amount: float):
        """Kick off funding the player's Game Credits to their chosen game.

        Async + idempotent: called from ``complete_btc_purchase`` and safe for
        webhook retries. Atomic compare-and-set on ``pool_transfer_status``
        guarantees the transfer is dispatched exactly once even if this runs
        concurrently. No-op when the deposit has no target ``platform``.
        """
        try:
            deposit = await self.db.btc_deposits.find_one({"id": deposit_id})
            if not deposit:
                return
            platform = deposit.get("platform")
            if not platform:
                # No game selected — leave Game Credits on the local balance only.
                await self.db.btc_deposits.update_one(
                    {"id": deposit_id},
                    {"$set": {"pool_transfer_status": "skipped_no_platform"}},
                )
                return
            if deposit.get("pool_transfer_status") in ("in_progress", "done", "failed"):
                return

            user_id = deposit.get("user_id")
            user = await self.db.users.find_one({"_id": ObjectId(user_id)}) if user_id else None
            recipient = (user or {}).get("game_username")
            if not recipient:
                await self.db.btc_deposits.update_one(
                    {"id": deposit_id},
                    {"$set": {"pool_transfer_status": "failed_no_username"}},
                )
                return

            # Atomic claim: only one dispatcher flips pending -> in_progress.
            claimed = await self.db.btc_deposits.update_one(
                {"id": deposit_id, "pool_transfer_status": "pending"},
                {"$set": {
                    "pool_transfer_status": "in_progress",
                    "pool_transfer_started_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            if claimed.modified_count == 0:
                return

            # Run in the background so the webhook never blocks on a 20-45s
            # Playwright/HTTP proxy transfer. Errors are recorded on the deposit
            # for admin retry rather than crashing the request.
            import asyncio

            task = asyncio.create_task(
                self._run_platform_transfer(
                    deposit_id=deposit_id,
                    user_id=user_id,
                    recipient=recipient,
                    platform=platform,
                    amount=amount,
                    tx_hash=tx_hash,
                )
            )
            _TRANSFER_TASKS.add(task)
            task.add_done_callback(_TRANSFER_TASKS.discard)
        except Exception as e:
            logger.error(f"Platform transfer dispatch error: {e}")

    async def _run_platform_transfer(
        self, deposit_id: str, user_id: str, recipient: str, platform: str, amount: float, tx_hash: str
    ):
        from routes.distributor_pool import execute_pool_transfer

        ok, msg, detail = await execute_pool_transfer(
            self.db,
            recipient_username=recipient,
            amount=amount,
            platform=platform,
            user_id=user_id,
        )
        status = "done" if ok else "failed"
        await self.db.btc_deposits.update_one(
            {"id": deposit_id},
            {"$set": {
                "pool_transfer_status": status,
                "pool_transfer_message": msg,
                "pool_transfer_detail": detail,
                "pool_transfer_tx_hash": tx_hash,
                "pool_transfer_completed_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.info(
            f"[pool:transfer] deposit={deposit_id} platform={platform} "
            f"recipient={recipient} ok={ok} msg={msg}"
        )

    async def claim_amoe_daily(
        self,
        user_id: str,
        user_email: str
    ) -> Tuple[bool, str]:
        """
        Process AMOE (Alternate Method of Entry) daily claim.
        
        LEGAL REQUIREMENT: Users must be able to get entries WITHOUT purchasing.
        
        Returns: (success, message)
        """
        try:
            # Check user's last AMOE claim
            user = await self.db.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return False, "User not found"
            
            last_claim = user.get("last_amoe_claim")
            
            # Check cooldown
            if last_claim:
                last_claim_time = datetime.fromisoformat(last_claim)
                next_eligible = last_claim_time + timedelta(hours=AMOE_COOLDOWN_HOURS)
                
                if datetime.now(timezone.utc) < next_eligible:
                    hours_remaining = int((next_eligible - datetime.now(timezone.utc)).total_seconds() / 3600)
                    return False, f"Already claimed today. Try again in {hours_remaining} hours."
            
            # Grant AMOE credits
            success, msg, grant_id = await self.grant_bonus_credits(
                user_id, user_email, AMOE_DAILY_CREDITS,
                BonusGrantType.AMOE_DAILY,
                metadata={"claim_date": datetime.now(timezone.utc).isoformat()}
            )
            
            if not success:
                return False, msg
            
            # Update user's last AMOE claim timestamp
            await self.db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"last_amoe_claim": datetime.now(timezone.utc).isoformat()}}
            )
            
            logger.info(f"✅ AMOE claim: {user_email} claimed {AMOE_DAILY_CREDITS} free credits")
            
            return True, f"Claimed {AMOE_DAILY_CREDITS} free credits! Come back tomorrow for more."
        
        except Exception as e:
            logger.error(f"AMOE claim error: {str(e)}")
            return False, f"Claim error: {str(e)}"
    
    async def create_redemption_request(
        self,
        user_id: str,
        user_email: str,
        game_credits: int,
        btc_address: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Create a redemption request to convert Game Credits to Bitcoin.
        
        Only GAME CREDITS can be redeemed (not Sugar Tokens).
        
        Returns: (success, message, redemption_id)
        """
        try:
            # Validate minimum redemption
            if game_credits < MIN_REDEMPTION_CREDITS:
                return False, f"Minimum redemption is {MIN_REDEMPTION_CREDITS} credits (${MIN_REDEMPTION_CREDITS/CREDITS_TO_USD_RATIO})", None
            
            # Check user balance
            user = await self.db.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return False, "User not found", None
            
            user_credits = user.get("game_credits", 0)
            if user_credits < game_credits:
                return False, f"Insufficient credits. You have {user_credits}, need {game_credits}", None
            
            # Calculate USD value
            amount_usd = calculate_redemption_usd(game_credits)
            needs_kyc = requires_kyc(amount_usd)
            
            # Create redemption request
            redemption_doc = {
                "id": str(uuid4()),
                "user_id": user_id,
                "user_email": user_email,
                "game_credits": game_credits,
                "amount_usd": amount_usd,
                "btc_address": btc_address,
                "status": "pending",
                "requires_kyc": needs_kyc,
                "reviewed_by": None,
                "platform_deduction_verified": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "approved_at": None,
                "completed_at": None,
                "rejection_reason": None
            }
            
            await self.db.redemption_requests.insert_one(redemption_doc)
            
            # Deduct credits from user (hold them in pending state)
            await self.db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$inc": {"game_credits": -game_credits}}
            )
            
            status_msg = "pending manual review (KYC required)" if needs_kyc else "pending approval"
            logger.info(f"💰 Redemption request: {user_email} - {game_credits} credits (${amount_usd}) - {status_msg}")
            
            return True, f"Redemption request created (${amount_usd}) - {status_msg}", redemption_doc["id"]
        
        except Exception as e:
            logger.error(f"Redemption request error: {str(e)}")
            return False, f"Error: {str(e)}", None
    
    async def get_user_balance(self, user_id: str) -> Optional[Dict]:
        """Get user's current dual-currency balance"""
        try:
            user = await self.db.users.find_one({"_id": ObjectId(user_id)}, {"_id": 0})
            if not user:
                return None
            
            return {
                "sugar_tokens": user.get("sugar_tokens", 0),
                "game_credits": user.get("game_credits", 0),
                "last_amoe_claim": user.get("last_amoe_claim")
            }
        except Exception as e:
            logger.error(f"Get balance error: {str(e)}")
            return None
