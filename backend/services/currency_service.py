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

# Durable settlement state machine for BTC deposits. `settlement_stage` on a
# btc_deposits row advances monotonically through these stages. The coarse
# `status` field (pending/settling/completed) is derived and maintained in
# parallel so the webhook, the reconciler, the admin tools and checkout_status
# all keep working unchanged against the old field until every reader migrates.
#
#   PENDING            deposit created, on-chain verification not yet done
#   VERIFYING          on-chain confirmations are being checked / reached
#   SETTLING           atomic claim won; about to credit tokens
#   LEDGER_COMMITTED   sugar_token_purchase row committed (tokens credited)
#   BONUS_COMMITTED    bonus Game Credit grant committed (credits credited)
#   TRANSFER_PENDING   local credit + ledger done; platform/seat transfer runner
#   COMPLETED          fully settled (ledger + bonus + transfer finalised)
#   RETRYABLE_FAILURE  a step failed; safe to re-run (no double-credit)
SETTLEMENT_STAGES = (
    "PENDING",
    "VERIFYING",
    "SETTLING",
    "LEDGER_COMMITTED",
    "BONUS_COMMITTED",
    "TRANSFER_PENDING",
    "COMPLETED",
    "RETRYABLE_FAILURE",
)

class CurrencyService:
    """Manages dual-currency system for legal sweepstakes compliance"""
    
    def __init__(self, db):
        self.db = db

    async def _advance_settlement_stage(
        self,
        deposit_id: str,
        stage: str,
        *,
        expected_prior: str | None = None,
        reason: str = "",
        collection: str = "btc_deposits",
    ) -> bool:
        """Append a durable stage transition to a deposit row.

        Works on ``btc_deposits`` (chain-verified money) and
        ``manual_deposits`` (operator-verified Cash App / Chime money) alike —
        both flow through the same settle → credit → distribute machine.

        Stages are recorded in ``settlement_stage`` with an immutable
        ``stage_history`` log (each transition timestamped). An optional
        ``expected_prior`` guards the write so two concurrent writers cannot
        both claim the same (idempotent-safe) next stage. Returns True when the
        write was applied.

        The coarse ``status`` field is kept in sync so existing readers
        (webhook, reconciler, admin list, checkout_status) keep working while
        they read ``status``.
        """
        stage = stage.upper()
        ok_stages = set(SETTLEMENT_STAGES)
        if stage not in ok_stages:
            return False

        now = datetime.now(timezone.utc).isoformat()
        entry = {"stage": stage, "entered_at": now, "reason": reason or ""}

        # Map stage -> coarse status for backward-compatible readers.
        if stage in ("COMPLETED",):
            coarse = "completed"
        elif stage == "RETRYABLE_FAILURE":
            coarse = "settling"  # keep reconciler able to reclaim and retry
        else:
            coarse = "settling"

        filter_doc = {"id": deposit_id}
        if expected_prior:
            # For pre-migration deposits the settlement_stage field is absent
            # entirely; treat that as equivalent to PENDING so the atomic claim
            # works on both new and legacy rows.
            filter_doc["$or"] = [
                {"settlement_stage": expected_prior},
                {"settlement_stage": {"$exists": False}},
            ]

        update = {
            "$set": {
                "settlement_stage": stage,
                "stage_entered_at": now,
                "status": coarse,
            },
            "$push": {"stage_history": entry},
        }
        try:
            res = await self.db[collection].update_one(filter_doc, update)
        except Exception:  # noqa: BLE001 — a stage write must never kill a settle
            logger.warning("stage write failed deposit=%s stage=%s", deposit_id, stage)
            return False
        if res.modified_count == 0:
            return False
        return True
    
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

            # Best-effort sweepstakes entries: a live competition earns entries
            # from purchases (1 per $1) and AMOE daily claims. Failures here must
            # never break the credit grant itself.
            try:
                from services.competition_service import award_amoe_entries, award_purchase_entries
                if grant_type == BonusGrantType.PURCHASE_BONUS:
                    amount_usd = float((metadata or {}).get("purchase_amount_usd") or 0)
                    if source_purchase_id and amount_usd > 0:
                        await award_purchase_entries(
                            self.db,
                            user_id=user_id,
                            user_email=user_email,
                            purchase_id=source_purchase_id,
                            purchase_amount_usd=amount_usd,
                        )
                elif grant_type == BonusGrantType.AMOE_DAILY:
                    await award_amoe_entries(
                        self.db, user_id=user_id, user_email=user_email,
                        grant_id=grant_doc["id"],
                    )
            except Exception as e:
                logger.warning(f"Sweepstakes entry award skipped: {e}")

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
                # Durable settlement state-machine (Phase 1, item 1).
                # The coarse `status` field above is kept in sync for backward
                # compat; `settlement_stage` carries the authoritative stage.
                "settlement_stage": "PENDING",
                "stage_entered_at": now.isoformat(),
                "stage_history": [
                    {"stage": "PENDING", "entered_at": now.isoformat(), "reason": "deposit created"},
                ],
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

            # VERIFYING: on-chain confirmations have been observed for this
            # deposit. Idempotent — reentrant callers just re-observe.
            await self._advance_settlement_stage(
                deposit_id, "VERIFYING",
                reason=f"confirmations reached: {confirmations} (tx {tx_hash})",
            )

            # Atomic claim: one caller advances PENDING->SETTLING before crediting
            # anything. The webhook, the reconciliation loop and a manual admin
            # override race here; only the single winner proceeds to credit, so
            # tokens/credits are never double-granted. Reentrant callers that
            # didn't win the claim short-circuit safely.
            claimed = await self._advance_settlement_stage(
                deposit_id, "SETTLING",
                expected_prior="PENDING", reason="atomic settle-claim acquired",
            )
            # Also allow reclaiming a prior crashed attempt (VERIFYING/ledger
            # stages already recorded) exactly once: guarded on VERIFYING.
            if not claimed:
                claimed = await self._advance_settlement_stage(
                    deposit_id, "SETTLING",
                    expected_prior="VERIFYING", reason="reclaim after prior attempt",
                )
            if not claimed:
                # Neither PENDING nor VERIFYING — already mid-settle/completed.
                return True, "Deposit already being settled"

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
                # Record a retryable failure and release the settle-claim so a
                # later webhook / reconciler pass can reclaim and finish.
                await self._advance_settlement_stage(
                    deposit_id, "RETRYABLE_FAILURE",
                    expected_prior="SETTLING",
                    reason=f"ledger committed failed: {purchase_msg}",
                )
                return False, purchase_msg

            # Sugar Token ledger committed.
            await self._advance_settlement_stage(
                deposit_id, "LEDGER_COMMITTED",
                expected_prior="SETTLING",
                reason=f"purchase {purchase_id} credited",
            )

            bonus_credits = calculate_bonus_credits(calculate_sugar_tokens(amount_usd))
            try:
                await self.grant_bonus_credits(
                    user_id, user_email, bonus_credits,
                    BonusGrantType.PURCHASE_BONUS,
                    source_purchase_id=purchase_id,
                    metadata={"btc_deposit_id": deposit_id, "tx_hash": tx_hash, "purchase_amount_usd": amount_usd},
                )
            except Exception as exc:  # noqa: BLE001 — bonus failure is retryable
                await self._advance_settlement_stage(
                    deposit_id, "RETRYABLE_FAILURE",
                    expected_prior="LEDGER_COMMITTED",
                    reason=f"bonus grant failed: {exc}",
                )
                return False, f"Bonus grant failed: {exc}"

            # Bonus Game Credit grant committed.
            await self._advance_settlement_stage(
                deposit_id, "BONUS_COMMITTED",
                expected_prior="LEDGER_COMMITTED",
                reason=f"bonus {bonus_credits} credits granted",
            )

            # Finalise: mark completed + record tx facts, then dispatch the
            # platform/seat transfer via TRANSFER_PENDING. The coarse status flip
            # guards webhook retries from ever double-dispatching (the transfer
            # itself is additionally idempotent on pool_transfer_status).
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
            await self._advance_settlement_stage(
                deposit_id, "COMPLETED",
                expected_prior="BONUS_COMMITTED",
                reason="ledger + bonus committed; transfer dispatch pending",
            )

            logger.info(f"✅ BTC deposit completed: {user_email} ${amount_usd} tx={tx_hash}")

            # Dispatch the funded Game Credits to the chosen game platform via the
            # distributor proxy pool. Runs in the background so the webhook returns
            # fast; idempotency is enforced by pool_transfer_status on the deposit.
            await self._dispatch_platform_transfer(deposit_id, tx_hash, bonus_credits)
            return True, f"Deposit completed ({amount_usd} USD)"

        except Exception as e:
            logger.error(f"Complete BTC purchase error: {str(e)}")
            # Ensure a freshly-claimed deposit is never left half-claimed: back
            # out to a retryable state so the webhook/reconciler can reclaim.
            try:
                await self._advance_settlement_stage(
                    deposit_id, "RETRYABLE_FAILURE",
                    reason=f"settle error: {e}",
                )
            except Exception:
                pass
            return False, f"Error: {str(e)}"


    async def create_manual_deposit(
        self,
        user_id: str,
        user_email: str,
        amount_usd: float,
        source: str,
        receipt: str,
        admin_email: str,
        platform: Optional[str] = None,
        game_id: Optional[str] = None,
        apply_fee: bool = True,
        note: str = "",
    ) -> Tuple[bool, str, Optional[str]]:
        """Record an operator-verified Cash App / Chime deposit (idempotent).

        The operator has ALREADY seen the money in the provider app — this is
        the trust anchor (same role the blockchain plays for BTC deposits).
        The house fee is split here (gross → net); completion credits NET.

        Idempotency: ``(source, receipt)`` is unique. A repeated reconcile
        with the same receipt returns the ORIGINAL deposit id — double-clicks
        and retries can never double-credit.

        Returns: (success, message, manual_deposit_id)
        """
        from services.revenue import apply_fee as _split, get_rates

        source = (source or "").strip().lower()
        if source not in ("cashapp", "chime", "cashtag"):
            return False, "source must be cashapp, chime, or cashtag", None
        receipt = (receipt or "").strip()
        if not receipt:
            receipt = f"noreceipt-{uuid4().hex[:12]}"

        existing = await self.db.manual_deposits.find_one(
            {"source": source, "receipt": receipt}
        )
        if existing:
            return True, "Deposit already reconciled (duplicate receipt)", existing.get("id")

        rates = await get_rates(self.db)
        rate = float(rates.get("cashtag", 0.12)) if apply_fee else 0.0
        split = _split(amount_usd, rate)
        net_usd = split["net_usd"]
        sugar_tokens = calculate_sugar_tokens(net_usd)
        now = datetime.now(timezone.utc)

        deposit_id = str(uuid4())
        deposit_doc = {
            "id": deposit_id,
            "user_id": user_id,
            "user_email": user_email,
            "amount_usd": split["gross_usd"],      # what the player sent
            "fee_usd": split["fee_usd"],            # house keep
            "fee_rate": split["rate"],
            "net_usd": net_usd,                     # what gets credited
            "sugar_tokens": sugar_tokens,
            "source": source,
            "receipt": receipt,
            "note": (note or "")[:500],
            "reconciled_by": admin_email,
            "platform": platform,
            "game_id": game_id or platform,
            "status": "pending",
            "tx_hash": receipt,                     # receipt is the money ref
            "created_at": now.isoformat(),
            "completed_at": None,
            "pool_transfer_status": None,
            "settlement_stage": "PENDING",
            "stage_entered_at": now.isoformat(),
            "stage_history": [
                {"stage": "PENDING", "entered_at": now.isoformat(),
                 "reason": f"operator-verified {source} receipt {receipt}"},
            ],
        }
        await self.db.manual_deposits.insert_one(deposit_doc)

        purchase_doc = {
            "id": str(uuid4()),
            "user_id": user_id,
            "user_email": user_email,
            "amount_usd": net_usd,
            "sugar_tokens": sugar_tokens,
            "purchase_type": PurchaseType.MANUAL_ADMIN.value,
            "payment_reference": deposit_id,
            "status": "pending",
            "created_at": now.isoformat(),
            "completed_at": None,
        }
        await self.db.sugar_token_purchases.insert_one(purchase_doc)

        logger.info(
            "manual deposit recorded: %s $%s %s receipt=%s by=%s (net $%s)",
            user_email, split["gross_usd"], source, receipt, admin_email, net_usd,
        )
        return True, "Manual deposit recorded — completing", deposit_id

    async def complete_manual_deposit(self, deposit_id: str) -> Tuple[bool, str]:
        """Settle a manual deposit: credit NET, record the fee, distribute.

        Mirrors ``complete_btc_purchase`` stage-for-stage (same atomic claims,
        same idempotency) on the ``manual_deposits`` collection, then routes
        through the SAME dispatch: manual mode → distributor queue task,
        auto mode → proxy pool transfer.
        """
        from services.revenue import record_revenue

        try:
            deposit = await self.db.manual_deposits.find_one({"id": deposit_id})
            if not deposit:
                return False, "Deposit not found"
            if deposit.get("status") == "completed":
                return True, "Deposit already completed"

            user_id = deposit.get("user_id")
            user_email = deposit.get("user_email")
            net_usd = float(deposit.get("net_usd") or 0)
            receipt = deposit.get("receipt") or deposit_id
            now = datetime.now(timezone.utc)

            await self._advance_settlement_stage(
                deposit_id, "VERIFYING", collection="manual_deposits",
                reason=f"operator verified receipt: {receipt}",
            )
            claimed = await self._advance_settlement_stage(
                deposit_id, "SETTLING", collection="manual_deposits",
                expected_prior="PENDING", reason="atomic settle-claim acquired",
            )
            if not claimed:
                claimed = await self._advance_settlement_stage(
                    deposit_id, "SETTLING", collection="manual_deposits",
                    expected_prior="VERIFYING", reason="reclaim after prior attempt",
                )
            if not claimed:
                return True, "Deposit already being settled"

            await self.db.sugar_token_purchases.update_one(
                {"payment_reference": deposit_id},
                {"$set": {
                    "status": "completed",
                    "completed_at": now.isoformat(),
                }},
            )

            purchase_success, purchase_msg, purchase_id = await self.create_sugar_token_purchase(
                user_id, user_email, net_usd, PurchaseType.MANUAL_ADMIN, receipt
            )
            if not purchase_success:
                await self._advance_settlement_stage(
                    deposit_id, "RETRYABLE_FAILURE", collection="manual_deposits",
                    expected_prior="SETTLING",
                    reason=f"ledger commit failed: {purchase_msg}",
                )
                return False, purchase_msg

            await self._advance_settlement_stage(
                deposit_id, "LEDGER_COMMITTED", collection="manual_deposits",
                expected_prior="SETTLING",
                reason=f"purchase {purchase_id} credited (net ${net_usd})",
            )

            bonus_credits = calculate_bonus_credits(calculate_sugar_tokens(net_usd))
            try:
                await self.grant_bonus_credits(
                    user_id, user_email, bonus_credits,
                    BonusGrantType.PURCHASE_BONUS,
                    source_purchase_id=purchase_id,
                    metadata={"manual_deposit_id": deposit_id, "receipt": receipt,
                              "purchase_amount_usd": net_usd},
                )
            except Exception as exc:  # noqa: BLE001 — bonus failure is retryable
                await self._advance_settlement_stage(
                    deposit_id, "RETRYABLE_FAILURE", collection="manual_deposits",
                    expected_prior="LEDGER_COMMITTED",
                    reason=f"bonus grant failed: {exc}",
                )
                return False, f"Bonus grant failed: {exc}"

            await self._advance_settlement_stage(
                deposit_id, "BONUS_COMMITTED", collection="manual_deposits",
                expected_prior="LEDGER_COMMITTED",
                reason=f"bonus {bonus_credits} credits granted",
            )

            # House keep hits the ledger exactly once per completed deposit.
            fee_usd = float(deposit.get("fee_usd") or 0)
            if fee_usd > 0:
                await record_revenue(
                    self.db, kind="cashtag", user_id=user_id,
                    gross_usd=float(deposit.get("amount_usd") or 0),
                    fee_usd=fee_usd, net_usd=net_usd,
                    rate=float(deposit.get("fee_rate") or 0),
                    ref_id=deposit_id, ref_kind="cashtag_deposit",
                    metadata={"source": deposit.get("source"), "receipt": receipt},
                )

            await self.db.manual_deposits.update_one(
                {"id": deposit_id, "status": {"$ne": "completed"}},
                {"$set": {
                    "status": "completed",
                    "confirmations": 1,
                    "completed_at": now.isoformat(),
                    "pool_transfer_status": "pending",
                }},
            )
            await self._advance_settlement_stage(
                deposit_id, "COMPLETED", collection="manual_deposits",
                expected_prior="BONUS_COMMITTED",
                reason="ledger + bonus committed; transfer dispatch pending",
            )

            logger.info("manual deposit completed: %s net $%s receipt=%s", user_email, net_usd, receipt)

            await self._dispatch_platform_transfer(
                deposit_id, receipt, bonus_credits, collection="manual_deposits"
            )
            return True, f"Deposit completed (net ${net_usd})"

        except Exception as e:
            logger.error(f"Complete manual deposit error: {str(e)}")
            try:
                await self._advance_settlement_stage(
                    deposit_id, "RETRYABLE_FAILURE", collection="manual_deposits",
                    reason=f"settle error: {e}",
                )
            except Exception:
                pass
            return False, f"Error: {str(e)}"

    async def _dispatch_platform_transfer(
        self, deposit_id: str, tx_hash: str, amount: float,
        collection: str = "btc_deposits",
    ):
        """Kick off funding the player's Game Credits to their chosen game.

        Async + idempotent: called from ``complete_btc_purchase`` and safe for
        webhook retries. Atomic compare-and-set on ``pool_transfer_status``
        guarantees the transfer is dispatched exactly once even if this runs
        concurrently. No-op when the deposit has no target ``platform``.
        """
        try:
            col = self.db[collection]
            deposit = await col.find_one({"id": deposit_id})
            if not deposit:
                return
            platform = deposit.get("platform")
            if not platform:
                # No game selected — leave Game Credits on the local balance only.
                await col.update_one(
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
                await col.update_one(
                    {"id": deposit_id},
                    {"$set": {"pool_transfer_status": "failed_no_username"}},
                )
                return

            # UNITS: `amount` here is INTERNAL Game Credits (2,200). Game backends
            # display and accept DOLLARS (22.00). Convert once, here, at the
            # dispatch boundary — everything downstream of this point speaks
            # platform dollars, everything upstream speaks credits.
            from config.currency_config import credits_to_platform_amount
            from services.self_distributor import get_mode, create_manual_task

            platform_amount = credits_to_platform_amount(amount)

            # Self-Distributor mode: don't hit the automated proxy pool. Queue a
            # manual task ("send $22.00 to this username") for the operator, who
            # sends by hand on the game backend and confirms. Guarded by the same
            # atomic compare-and-set on pool_transfer_status so webhook retries
            # can never queue the same transfer twice.
            if (await get_mode(self.db)) == "manual":
                claimed = await col.update_one(
                    {"id": deposit_id, "pool_transfer_status": "pending"},
                    {"$set": {
                        "pool_transfer_status": "awaiting_manual_send",
                        "pool_transfer_started_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                if claimed.modified_count == 0:
                    return
                task_id = await create_manual_task(
                    self.db,
                    deposit_id=deposit_id,
                    user_id=user_id,
                    user_email=(user or {}).get("email", ""),
                    platform=platform,
                    recipient_username=recipient,
                    amount_credits=amount,
                    platform_amount=platform_amount,
                    tx_hash=tx_hash,
                    game_id=deposit.get("game_id"),
                )
                await col.update_one(
                    {"id": deposit_id},
                    {"$set": {"distribution_task_id": task_id}},
                )
                logger.info(
                    "manual-distributor queued: deposit=%s platform=%s recipient=%s "
                    "credits=%s platform_amount=%s",
                    deposit_id, platform, recipient, amount, platform_amount,
                )
                return

            # Atomic claim: only one dispatcher flips pending -> in_progress.
            claimed = await col.update_one(
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
                    amount=platform_amount,
                    amount_credits=amount,
                    tx_hash=tx_hash,
                    collection=collection,
                )
            )
            _TRANSFER_TASKS.add(task)
            task.add_done_callback(_TRANSFER_TASKS.discard)
        except Exception as e:
            logger.error(f"Platform transfer dispatch error: {e}")

    async def _run_platform_transfer(
        self, deposit_id: str, user_id: str, recipient: str, platform: str,
        amount: float, tx_hash: str, collection: str = "btc_deposits",
        amount_credits: Optional[float] = None,
    ):
        from routes.distributor_pool import execute_pool_transfer

        ok, msg, detail = await execute_pool_transfer(
            self.db,
            recipient_username=recipient,
            amount=amount,
            platform=platform,
            user_id=user_id,
            amount_credits=amount_credits,
        )
        status = "done" if ok else "failed"
        await self.db[collection].update_one(
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
