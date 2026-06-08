import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException

client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = client.wah_lah

async def claim_daily_amoe(user_id: str):
    now = datetime.now(timezone.utc)
    start_of_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    # Atomic check-and-update prevents race condition double-spends
    result = await db.users.find_one_and_update(
        {
            "_id": user_id,
            "$or": [
                {"last_amoe_claim": {"$lt": start_of_day}},
                {"last_amoe_claim": {"$exists": False}}
            ]
        },
        {
            "$inc": {"credits": 100},
            "$set": {"last_amoe_claim": now}
        },
        return_document=True
    )

    if not result:
        raise HTTPException(status_code=400, detail="AMOE already claimed today or user not found.")
    
    return result.get("credits", 0)
