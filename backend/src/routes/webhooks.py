import os
import stripe
from fastapi import APIRouter, Request, Header, HTTPException

router = APIRouter()
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

@router.post("/api/v1/webhooks/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    # CRITICAL: Read raw bytes for signature verification. Do not parse as JSON.
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, endpoint_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Background processing integration point
    if event['type'] == 'payment_intent.succeeded':
        pass

    return {"status": "success"}
