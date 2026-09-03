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


class RedemptionRequestPayload(BaseModel):
    """Request to redeem Game Credits for Bitcoin."""
    game_credits: int = Field(..., gt=0, description="Credits to redeem")
    btc_address: str = Field(..., min_length=15, max_length=100, description="BTC payout address")
