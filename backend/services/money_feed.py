"""Unified money feed — the ONE source of truth for transaction history.

Both the admin feed (``GET /api/admin/transactions``) and the player Ledger
(``GET /api/user/transactions``) are projections of :func:`get_feed`. Any
change to what a transaction *means* is made here, once — never in two
route handlers.

Covered rails (kind -> collection):
- purchase       -> sugar_token_purchases
- btc_deposit    -> btc_deposits
- manual_deposit -> manual_deposits (Cash App / Chime)
- redemption     -> redemption_requests (BTC cash-outs)
- giftcard       -> gift_card_redemptions
- grant          -> bonus_credit_grants
- adjustment     -> credit_adjustments (audited manual edits)

User scoping matches on the NORMALIZED row (``user_id`` stringified, or
email fallback) so legacy rows that stored an ObjectId instead of a string
still resolve to the right player.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

VALID_KINDS = (
    "all", "purchase", "btc_deposit", "manual_deposit",
    "redemption", "giftcard", "grant", "adjustment",
)

_PULLS = (
    ("sugar_token_purchases", "purchase"),
    ("btc_deposits", "btc_deposit"),
    ("manual_deposits", "manual_deposit"),
    ("redemption_requests", "redemption"),
    ("gift_card_redemptions", "giftcard"),
    ("bonus_credit_grants", "grant"),
    ("credit_adjustments", "adjustment"),
)

# Never sent to the player themself, only to admins.
PLAYER_STRIPPED_FIELDS = ("btc_address", "actor")


def normalize_tx(kind: str, d: Dict[str, Any]) -> Dict[str, Any]:
    """Project one raw money doc onto the canonical feed row shape."""
    base = {
        "kind": kind,
        "id": d.get("id") or str(d.get("_id", "")),
        "user_email": d.get("user_email"),
        "user_id": str(d.get("user_id") or ""),
        "status": d.get("status"),
        "created_at": d.get("created_at"),
    }
    if kind == "purchase":
        base.update({"amount_usd": d.get("amount_usd"), "sugar_tokens": d.get("sugar_tokens"),
                     "purchase_type": d.get("purchase_type")})
    elif kind in ("btc_deposit", "manual_deposit"):
        base.update({"amount_usd": d.get("amount_usd"), "net_usd": d.get("net_usd"),
                     "fee_usd": d.get("fee_usd"), "platform": d.get("platform"),
                     "tx_ref": d.get("tx_hash") or d.get("receipt"),
                     "pool_transfer_status": d.get("pool_transfer_status")})
    elif kind == "redemption":
        base.update({"game_credits": d.get("game_credits"), "amount_usd": d.get("amount_usd"),
                     "btc_address": d.get("btc_address")})
    elif kind == "giftcard":
        base.update({"amount_usd": d.get("amount_usd"), "gross_usd": d.get("gross_usd"),
                     "fee_usd": d.get("fee_usd"), "brand": d.get("brand_label") or d.get("brand"),
                     "fulfilled_at": d.get("fulfilled_at")})
    elif kind == "grant":
        base.update({"game_credits": d.get("game_credits"), "grant_type": d.get("grant_type")})
    elif kind == "adjustment":
        base.update({"inc": d.get("inc"), "set": d.get("set"), "note": d.get("note"),
                     "actor": d.get("actor")})
    return base


def _belongs_to(row: Dict[str, Any], user_id: str, user_email: Optional[str]) -> bool:
    if row.get("user_id") and row["user_id"] == user_id:
        return True
    return bool(user_email and row.get("user_email") == user_email)


async def get_feed(
    db,
    *,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    kind: str = "all",
    skip: int = 0,
    limit: int = 50,
    strip_private: bool = False,
) -> Dict[str, Any]:
    """Return ``{"total", "skip", "limit", "transactions"}``.

    Pass ``user_id``/``user_email`` for a player-scoped Ledger (with
    ``strip_private=True``); omit both for the full admin feed.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"Unknown kind filter: {kind}")
    rows: List[Dict[str, Any]] = []
    for coll, row_kind in _PULLS:
        if kind != "all" and row_kind != kind:
            continue
        try:
            docs = await db[coll].find({}).sort("created_at", -1).limit(500).to_list(500)
        except Exception:
            continue
        for d in docs:
            rows.append(normalize_tx(row_kind, d))

    if user_id is not None or user_email is not None:
        rows = [r for r in rows if _belongs_to(r, user_id or "", user_email)]

    if strip_private:
        for r in rows:
            for field in PLAYER_STRIPPED_FIELDS:
                r.pop(field, None)

    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"total": len(rows), "skip": skip, "limit": limit,
            "transactions": rows[skip:skip + limit]}


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ledger header numbers for one player's full row set."""
    def _f(v):
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0

    deposits = [_f(r.get("amount_usd")) for r in rows
                if r["kind"] in ("btc_deposit", "manual_deposit")]
    paid = [_f(r.get("amount_usd")) for r in rows
            if (r["kind"] == "redemption" and r.get("status") == "approved")
            or (r["kind"] == "giftcard" and r.get("status") == "fulfilled")]
    pending = sum(1 for r in rows if (r.get("status") or "") in
                  ("pending", "hold_admin_review", "settling", "awaiting_send"))
    return {
        "deposited_usd": round(sum(deposits), 2),
        "received_usd": round(sum(paid), 2),
        "entries": len(rows),
        "pending_items": pending,
    }
