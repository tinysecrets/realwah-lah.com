from fastapi import APIRouter, Request


def build_webhooks_router(db=None):
    """Return webhook routes mounted under /api/webhooks."""
    router = APIRouter(prefix="/webhooks", tags=["webhooks"])

    @router.post("/bitcoin")
    async def bitcoin_webhook(request: Request):
        await request.json()
        # Placeholder handler — integrate BTC webhook processing logic here
        return {"status": "ok", "received": True}

    return router
