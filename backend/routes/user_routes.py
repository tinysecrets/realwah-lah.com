from fastapi import APIRouter, HTTPException, Query, Request

from services.money_feed import VALID_KINDS, get_feed, summarize
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
        secret = os.environ.get("JWT_SECRET")
        if not secret:
            logger.error("JWT_SECRET not configured in environment")
            raise HTTPException(status_code=500, detail="Server misconfigured: JWT_SECRET not set")
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
    
    @router.get("/transactions")
    async def get_user_transactions(
        request: Request,
        kind: str = Query(default="all"),
        skip: int = Query(default=0, ge=0, le=100_000),
        limit: int = Query(default=50, ge=1, le=200),
    ):
        """Player Ledger — every money movement on this account.

        Same source of truth as the admin feed (services.money_feed),
        scoped to the caller with private fields stripped.
        """
        user = await get_current_user(request, db)
        if kind not in VALID_KINDS:
            raise HTTPException(status_code=400, detail="Unknown kind filter")
        feed = await get_feed(
            db,
            user_id=str(user["_id"]),
            user_email=user.get("email"),
            kind=kind,
            skip=0,
            limit=10_000,
            strip_private=True,
        )
        rows = feed["transactions"]
        return {
            "total": len(rows),
            "skip": skip,
            "limit": limit,
            "transactions": rows[skip:skip + limit],
            "summary": summarize(rows),
        }

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

    @router.get("/support/tickets/{ticket_id}")
    async def get_user_ticket_detail(ticket_id: str, request: Request):
        """One ticket with its full thread — owner-scoped."""
        user = await get_current_user(request, db)
        from bson.errors import InvalidId
        try:
            oid = ObjectId(ticket_id)
        except (InvalidId, TypeError):
            raise HTTPException(status_code=422, detail="ticket_id is not a valid id")
        t = await db.support_tickets.find_one({"_id": oid})
        if not t or str(t.get("user_id")) != str(user["_id"]):
            raise HTTPException(status_code=404, detail="Ticket not found")
        return {
            "ticket_id": str(t["_id"]),
            "subject": t.get("subject", ""),
            "message": t.get("message", ""),
            "status": t.get("status"),
            "priority": t.get("priority", "normal"),
            "created_at": t.get("created_at"),
            "responses": t.get("responses", []),
        }

    return router


def build_user_router(db, get_current_user=None):
    """Factory matching server.py mount contract."""
    return get_user_routes(db)
