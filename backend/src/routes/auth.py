from fastapi import APIRouter, Depends, Body
from ..services.auth import create_tokens, verify_token, get_current_user

router = APIRouter()

@router.post("/api/v1/auth/refresh")
async def refresh_session(refresh_token: str = Body(..., embed=True)):
    # 1. Verify structural integrity and expiration of the old refresh token
    payload = verify_token(refresh_token, "refresh")
    
    # 2. Issue a brand new Access/Refresh pair (Rotation)
    new_access, new_refresh = create_tokens(payload["sub"], payload.get("role", "user"))
    
    return {
        "access_token": new_access, 
        "refresh_token": new_refresh
    }

@router.get("/api/v1/auth/me")
async def get_me(user_payload: dict = Depends(get_current_user)):
    # Example protected route verifying the Dependency injection works
    return {"status": "authenticated", "user": user_payload}
