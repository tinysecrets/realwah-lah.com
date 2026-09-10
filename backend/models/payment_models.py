"""Payment/API request models for the crypto (Bitcoin) money path."""

from typing import Optional
from pydantic import BaseModel, Field


class CheckoutCreateRequest(BaseModel):
    """Request to start a Bitcoin deposit for Sugar Tokens."""
    amount_usd: float = Field(..., gt=0, description="USD amount being deposited")
    payment_method: Optional[str] = Field(
        default="bitcoin",
        description="Payment method — only 'bitcoin' is supported.",
    )
    platform: Optional[str] = Field(
        default=None,
        description="Target game platform id the deposit Game Credits will fund (e.g. 'fire_kirin').",
    )
    # The frontend sends the chosen game as ``game_id`` (the games collection _id
    # or its platform_id alias). Accepted so the existing UI needs no change; it
    # is folded into ``platform`` on the deposit.
    game_id: Optional[str] = Field(
        default=None,
        description="Alias for platform: the chosen game id from the frontend game picker.",
    )


class RedemptionRequestPayload(BaseModel):
    """Request to redeem Game Credits for Bitcoin."""
    game_credits: int = Field(..., gt=0, description="Credits to redeem")
    btc_address: str = Field(..., min_length=15, max_length=100, description="BTC payout address")


class GamePayload(BaseModel):
    """Admin create/update payload for a game card.

    Mirrors the shape the frontend's admin "Games" modal submits and the
    /api/games response returns.
    """
    name: str = Field(..., min_length=1)
    logo_url: str = Field(..., min_length=1)
    game_url: str = Field(default="", description="Download / play URL")
    description: str = Field(default="")
    is_active: bool = True
    accent_color: str = Field(default="#ff00ff")
