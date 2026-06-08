from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import logging
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])

async def get_admin_user(request: Request, db):
    access_token = request.cookies.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        import jwt
        import os
        from bson import ObjectId
        secret = os.environ.get("JWT_SECRET", "sugar-city-secret-key-2024")
        payload = jwt.decode(access_token, secret, algorithms=["HS256"])
        user_id = payload.get("sub")
        
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user or user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_analytics_routes(db):
    
    @router.get("/overview")
    async def get_analytics_overview(request: Request):
        """Get analytics overview dashboard"""
        await get_admin_user(request, db)
        
        # Total users
        total_users = await db.users.count_documents({"role": "user"})
        
        # Users registered in last 30 days
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        new_users_30d = await db.users.count_documents({
            "role": "user",
            "created_at": {"$gte": thirty_days_ago}
        })
        
        # Total deposits
        deposits = await db.payment_transactions.aggregate([
            {"$match": {"type": "deposit", "status": "completed"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
        ]).to_list(1)
        
        total_deposits = deposits[0]["total"] if deposits else 0
        deposit_count = deposits[0]["count"] if deposits else 0
        
        # Total withdrawals
        withdrawals = await db.completed_payouts.aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}, "count": {"$sum": 1}}}
        ]).to_list(1)
        
        total_withdrawals = withdrawals[0]["total"] if withdrawals else 0
        withdrawal_count = withdrawals[0]["count"] if withdrawals else 0
        
        # Pending payouts
        pending_payouts = await db.pending_payouts.count_documents({"status": "pending_approval"})
        
        # Revenue (deposits - withdrawals)
        revenue = total_deposits - total_withdrawals
        
        # Active games
        active_games = await db.games.count_documents({"is_active": True})
        
        return {
            "users": {
                "total": total_users,
                "new_30d": new_users_30d
            },
            "deposits": {
                "total_amount": round(total_deposits, 2),
                "count": deposit_count,
                "average": round(total_deposits / deposit_count, 2) if deposit_count > 0 else 0
            },
            "withdrawals": {
                "total_amount": round(total_withdrawals, 2),
                "count": withdrawal_count,
                "average": round(total_withdrawals / withdrawal_count, 2) if withdrawal_count > 0 else 0
            },
            "revenue": round(revenue, 2),
            "pending_payouts": pending_payouts,
            "active_games": active_games
        }
    
    @router.get("/support-tickets")
    async def get_support_tickets(request: Request, status: Optional[str] = None):
        """Get support tickets for admin"""
        await get_admin_user(request, db)
        
        query = {}
        if status:
            query["status"] = status
        
        tickets = await db.support_tickets.find(
            query,
            {"_id": 1, "user_email": 1, "user_name": 1, "subject": 1, "message": 1, "status": 1, "priority": 1, "created_at": 1}
        ).sort("created_at", -1).to_list(100)
        
        return [
            {
                "ticket_id": str(t["_id"]),
                "user_email": t.get("user_email"),
                "user_name": t.get("user_name"),
                "subject": t["subject"],
                "message": t.get("message", ""),
                "status": t["status"],
                "priority": t.get("priority", "normal"),
                "created_at": t["created_at"]
            }
            for t in tickets
        ]
    
    @router.post("/support-tickets/{ticket_id}/close")
    async def close_support_ticket(ticket_id: str, request: Request):
        """Close a support ticket"""
        await get_admin_user(request, db)
        
        from bson import ObjectId
        
        result = await db.support_tickets.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": {"status": "closed", "updated_at": datetime.now(timezone.utc)}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        return {"message": "Ticket closed successfully"}
    
    return router
