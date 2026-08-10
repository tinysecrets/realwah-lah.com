from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"]) 

@router.post("/bitcoin")
async def bitcoin_webhook(request: Request):
    data = await request.json()
    # Placeholder handler — integrate BTC webhook processing logic here
    return {"status": "ok", "received": True}
