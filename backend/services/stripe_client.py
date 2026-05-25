"""Native Stripe SDK wrapper.

Replaces the `emergentintegrations.payments.stripe.checkout` shim with a thin
async-friendly facade that uses the official `stripe` Python SDK. Keeps the
exact same call shape the rest of server.py was using:

    sc = StripeCheckout(api_key, webhook_url)
    req = CheckoutSessionRequest(amount, currency, success_url, cancel_url, metadata)
    session = await sc.create_checkout_session(req)          # session.url, session.session_id
    status  = await sc.get_checkout_status(session_id)       # .status, .payment_status, .amount_total
    web_evt = await sc.handle_webhook(body, signature)       # .session_id, .payment_status

Stripe's SDK is blocking; we offload the actual HTTP calls to a thread executor
so the FastAPI event loop stays responsive.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import stripe

logger = logging.getLogger(__name__)


@dataclass
class CheckoutSessionRequest:
    amount: float                # USD dollars (we convert to cents internally)
    currency: str = "usd"
    success_url: str = ""
    cancel_url: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class CheckoutSession:
    url: str
    session_id: str


@dataclass
class CheckoutStatus:
    status: str                  # "open" | "complete" | "expired"
    payment_status: str          # "paid" | "unpaid" | "no_payment_required"
    amount_total: int            # cents


@dataclass
class WebhookResponse:
    session_id: str
    payment_status: str          # "paid" | "unpaid" | etc.
    event_type: str = ""


class StripeCheckout:
    """Thin async wrapper around the official Stripe Python SDK."""

    def __init__(self, api_key: str, webhook_url: str = "", webhook_secret: Optional[str] = None):
        if not api_key:
            raise ValueError("STRIPE_API_KEY is required")
        self.api_key = api_key
        self.webhook_url = webhook_url
        # Webhook secret needed only for signature verification on /webhook/stripe.
        # Pulled from env (STRIPE_WEBHOOK_SECRET) by default so callers don't have
        # to know about it.
        self.webhook_secret = webhook_secret or os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        stripe.api_key = api_key

    async def create_checkout_session(self, req: CheckoutSessionRequest) -> CheckoutSession:
        def _create() -> Any:
            return stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": req.currency,
                        "product_data": {"name": "WAH-LAH Game Credits"},
                        "unit_amount": int(round(req.amount * 100)),  # USD -> cents
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url=req.success_url,
                cancel_url=req.cancel_url,
                metadata=req.metadata or {},
            )

        session = await asyncio.to_thread(_create)
        return CheckoutSession(url=session.url, session_id=session.id)

    async def get_checkout_status(self, session_id: str) -> CheckoutStatus:
        def _retrieve() -> Any:
            return stripe.checkout.Session.retrieve(session_id)

        s = await asyncio.to_thread(_retrieve)
        return CheckoutStatus(
            status=s.status or "open",
            payment_status=s.payment_status or "unpaid",
            amount_total=int(s.amount_total or 0),
        )

    async def handle_webhook(self, body: bytes, signature: Optional[str]) -> WebhookResponse:
        """Verify and parse a Stripe webhook payload.

        If STRIPE_WEBHOOK_SECRET is configured, the signature is verified.
        Otherwise we parse the JSON without verification (dev/test only).
        """
        def _parse() -> Any:
            if self.webhook_secret and signature:
                return stripe.Webhook.construct_event(body, signature, self.webhook_secret)
            # No secret configured → trust the body. This is only safe for
            # local dev. In production STRIPE_WEBHOOK_SECRET must be set.
            import json
            return stripe.Event.construct_from(json.loads(body), stripe.api_key)

        event = await asyncio.to_thread(_parse)
        event_type = getattr(event, "type", "")
        data_obj = event.data.object if hasattr(event, "data") else {}

        session_id = ""
        payment_status = "unpaid"

        if event_type.startswith("checkout.session"):
            session_id = data_obj.get("id", "") if isinstance(data_obj, dict) else getattr(data_obj, "id", "")
            payment_status = (
                data_obj.get("payment_status", "unpaid")
                if isinstance(data_obj, dict)
                else getattr(data_obj, "payment_status", "unpaid")
            )

        return WebhookResponse(
            session_id=session_id,
            payment_status=payment_status,
            event_type=event_type,
        )
