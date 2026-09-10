"""Competition (sweepstakes) models: campaign config, entry ledger, winners.

Stored in the ``competitions`` and ``competition_entries`` collections. The
service layer works with plain dicts (consistent with the rest of the
codebase); these models are thin, declarative contracts for validation and
typing only.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union
from enum import Enum


class CompetitionStatus(str, Enum):
    UPCOMING = "upcoming"        # advertised; entries not yet accruing
    LIVE = "live"                # accepting entries until draws_at
    DRAWING = "drawing"          # draw in progress / about to run
    CONCLUDED = "concluded"      # winner selected; prize pending or paid
    CANCELLED = "cancelled"      # voided; no entry awarding or draw


class EntrySource(str, Enum):
    PURCHASE = "purchase"        # sugar token / bonus credit purchase (1 entry per $1)
    AMOE_DAILY = "amoe_daily"    # alternative method of entry (1 free entry/day)


class CompetitionRules(BaseModel):
    # 1 entry per USD of purchase (derived from bonus grant purchase_amount_usd)
    entry_per_purchase_usd: float = Field(default=1.0, ge=0)
    # 1 entry per successful AMOE daily claim
    entry_amoe_daily: float = Field(default=1.0, ge=0)


class Competition(BaseModel):
    id: str
    name: str = "Million Dollar Sweepstakes"
    prize_usd: float = Field(default=1_000_000, ge=0)
    status: CompetitionStatus = CompetitionStatus.UPCOMING
    starts_at: Optional[str] = None
    draws_at: Optional[str] = None
    rules: CompetitionRules = CompetitionRules()
    # winner populated by run_draw
    winner: Optional[Dict] = None
    # none | pending_payout | paid
    prize_status: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CompetitionEntry(BaseModel):
    id: str
    competition_id: str
    user_id: str
    user_email: str
    source: EntrySource
    quantity: int = Field(default=1, ge=1)
    source_ref: str = Field(description="Purchase/grant id the entries derive from (idempotency key)")
    created_at: Optional[str] = None