from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from typing import Optional
import bcrypt
import logging
import os
import jwt
from bson import ObjectId
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])

# Request models
class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None

class SupportTicketRequest(BaseModel):
    subject: str
    message: str
    priority: str = "normal"  # low, normal, high

# Helper functions
async def get_current_user(request: Request, db):
    access_token = request.cookies.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        secret = os.environ.get("JWT_SECRET", "sugar-city-secret-key-2024")
        payload = jwt.decode(access_token, secret, algorithms=["HS256"])
        user_id = payload.get("sub")
        
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        # Maintenance Mode check: Block non-admins if active
        if user.get("role") != "admin":
            try:
                from services.feature_flags import get_flag
                if await get_flag(db, "maintenance_mode_enabled"):
                    raise HTTPException(
                        status_code=503, 
                        detail="WAH-LAH is currently undergoing maintenance. Please check back later."
                    )
            except (ImportError, Exception):
                pass # Fallback to allowing if service is missing or fails

        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Invalid JWT token: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token")

def get_user_routes(db):
    """Factory function to create routes with database dependency"""
    
    @router.get("/profile")
    async def get_profile(request: Request):
        """Get user profile"""
        user = await get_current_user(request, db)
        
        game_credits = user.get("game_credits", user.get("credits", 0.0))
        playthrough_bal = user.get("playthrough_balance", 0.0)
        redeemable = max(0.0, game_credits - playthrough_bal)

        return {
            "email": user["email"],
            "name": user.get("name", ""),
            "credits": game_credits,
            "redeemable_credits": round(redeemable, 2),
            "playthrough_balance": round(playthrough_bal, 2),
            "role": user.get("role", "user"),
            "age_verified": user.get("age_verified", False),
            "created_at": user.get("created_at"),
            "game_accounts": user.get("game_accounts", {})
        }
    
    @router.put("/profile")
    async def update_profile(data: ProfileUpdateRequest, request: Request):
        """Update user profile"""
        user = await get_current_user(request, db)
        
        update_data = {}
        if data.name:
            update_data["name"] = data.name
        
        if data.email and data.email != user["email"]:
            # Check if email already exists
            existing = await db.users.find_one({"email": data.email.lower()})
            if existing:
                raise HTTPException(status_code=400, detail="Email already in use")
            update_data["email"] = data.email.lower()
        
        if update_data:
            await db.users.update_one(
                {"_id": user["_id"]},
                {"$set": update_data}
            )
        
        return {"message": "Profile updated successfully"}
    
    @router.post("/password/change")
    async def change_password(data: PasswordChangeRequest, request: Request):
        """Change user password"""
        user = await get_current_user(request, db)
        
        # Verify current password
        if not bcrypt.checkpw(data.current_password.encode(), user["password_hash"].encode()):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Hash new password
        new_hash = bcrypt.hashpw(data.new_password.encode(), bcrypt.gensalt()).decode()
        
        # Update password
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"password_hash": new_hash}}
        )
        
        return {"message": "Password changed successfully"}
    
    @router.get("/bonuses")
    async def get_user_bonuses(request: Request):
        """Get user's bonus history"""
        user = await get_current_user(request, db)
        
        bonuses = await db.bonus_transactions.find(
            {"user_id": str(user["_id"])},
            {"_id": 0}
        ).sort("created_at", -1).to_list(100)
        
        return bonuses
    
    @router.post("/support/ticket")
    async def create_support_ticket(data: SupportTicketRequest, request: Request):
        """Create a support ticket"""
        user = await get_current_user(request, db)
        
        ticket = {
            "user_id": str(user["_id"]),
            "user_email": user["email"],
            "user_name": user.get("name", ""),
            "subject": data.subject,
            "message": data.message,
            "priority": data.priority,
            "status": "open",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "responses": []
        }
        
        result = await db.support_tickets.insert_one(ticket)
        
        logger.info(f"Support ticket created: {user['email']} - {data.subject}")
        
        return {
            "message": "Support ticket created successfully",
            "ticket_id": str(result.inserted_id)
        }
    
    @router.get("/support/tickets")
    async def get_user_tickets(request: Request):
        """Get user's support tickets"""
        user = await get_current_user(request, db)
        
        tickets = await db.support_tickets.find(
            {"user_id": str(user["_id"])},
            {"_id": 1, "subject": 1, "status": 1, "priority": 1, "created_at": 1}
        ).sort("created_at", -1).to_list(50)
        
        return [
            {
                "ticket_id": str(t["_id"]),
                "subject": t["subject"],
                "status": t["status"],
                "priority": t["priority"],
                "created_at": t["created_at"]
            }
            for t in tickets
        ]
    
    return router
