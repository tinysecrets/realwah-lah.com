import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
db = AsyncIOMotorClient(os.getenv("MONGO_URI")).wah_lah
async def queue_transaction(platform, action, payload):
    return await db.task_queue.insert_one({"platform": platform, "action": action, "payload": payload, "status": "pending", "created_at": datetime.now(timezone.utc)})
