from fastapi import FastAPI, Depends, BackgroundTasks
from .middleware.compliance import verify_region
from .services.queue import queue_transaction, process_transaction
from .routes.webhooks import router as webhook_router
from .routes.auth import router as auth_router

app = FastAPI()

# Mount routers
app.include_router(webhook_router)
app.include_router(auth_router)

@app.post("/api/v1/payouts/request", dependencies=[Depends(verify_region)])
async def request_payout(data: dict, background_tasks: BackgroundTasks):
    transaction_id = await queue_transaction("PandaMaster", "payout", data)
    background_tasks.add_task(process_transaction, transaction_id)
    return {"status": "queued", "id": str(transaction_id)}
