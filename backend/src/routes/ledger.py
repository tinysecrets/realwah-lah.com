from fastapi import APIRouter, Depends
from ..services.ledger import claim_daily_amoe
from ..services.auth import get_current_user

router = APIRouter()

@router.post("/api/v1/wallet/amoe")
async def claim_amoe(user: dict = Depends(get_current_user)):
    # Requires valid JWT from the Auth service we just built
    new_balance = await claim_daily_amoe(user["sub"])
    return {
        "status": "success", 
        "credits_awarded": 100, 
        "new_balance": new_balance
    }
