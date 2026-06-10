import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URI = (
    os.getenv("MONGODB_URI")
    or os.getenv("MONGO_URL")
    or os.getenv("MONGO_URI")
)
if not MONGODB_URI:
    raise RuntimeError(
        "MONGODB_URI is required. Set it in .env for local testing or via production secrets."
    )
DB_NAME = os.getenv("DB_NAME", "wahlah_prod")
client = AsyncIOMotorClient(MONGODB_URI)
db = client[DB_NAME]

async def queue_transaction(platform, action, payload):
    return await db.task_queue.insert_one({"platform": platform, "action": action, "payload": payload, "status": "pending", "created_at": datetime.now(timezone.utc)})
