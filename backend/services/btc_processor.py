"""Bitcoin payment processing via BlockCypher (HD wallet + address webhooks).

Provides:
- get_btc_usd_rate()          -> live BTC/USD price
- derive_deposit_address()    -> next address from the configured HD wallet
- create_webhook()            -> subscribe to tx-confirmation for a deposit address
- verify_webhook_signature()  -> server-side validation of incoming BlockCypher hooks

All network calls use httpx.AsyncClient (matching the rest of the backend).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

BLOCKCYPHER_BASE = os.getenv("BLOCKCYPHER_BASE", "https://api.blockcypher.com/v1/btc/main")
BLOCKCYPHER_TOKEN = os.getenv("BLOCKCYPHER_TOKEN", "")
BLOCKCYPHER_HD_WALLET = os.getenv("BLOCKCYPHER_HD_WALLET", "wah_lah_deposits")
BLOCKCYPHER_XPUB = os.getenv("BLOCKCYPHER_XPUB", "")

# Static deposit address fallback. When set, all deposits use this single
# address (no HD derivation needed) instead of the HD wallet.
BTC_STATIC_ADDRESS = os.getenv("BLOCKCYPHER_STATIC_ADDRESS", "")

# Keyless public spot price source (fallback: BLOCKCYPHER_BASE chain endpoint).
PRICE_URL = os.getenv("BTC_PRICE_URL", "https://api.coinbase.com/v2/prices/BTC-USD/spot")

# Required network confirmations before a deposit is credited.
MIN_CONFIRMATIONS = int(os.getenv("BTC_MIN_CONFIRMATIONS", "1"))

# Timeout for outbound BlockCypher requests.
_HTTP_TIMEOUT = httpx.Timeout(15.0)


def _token() -> str:
    return BLOCKCYPHER_TOKEN


def _has_credentials() -> bool:
    return bool(BLOCKCYPHER_TOKEN and (BLOCKCYPHER_XPUB or BLOCKCYPHER_HD_WALLET or BTC_STATIC_ADDRESS))


def _base_url() -> str:
    return BLOCKCYPHER_BASE.rstrip("/")


async def get_btc_usd_rate() -> float:
    """Return the current market price of 1 BTC in USD.

    Uses a keyless public spot-price source (default: Coinbase). Falls back to
    a configured constant if the network call fails or is unavailable.
    """
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(PRICE_URL)
            resp.raise_for_status()
            data = resp.json()
        amount = (data.get("data") or {}).get("amount") or data.get("amount")
        if amount:
            return float(amount)
    except Exception:
        logger.warning("BTC price fetch failed; using fallback", exc_info=True)
    return float(os.getenv("BTC_FALLBACK_USD", "60000.0"))


def usd_to_satoshis(amount_usd: float, usd_per_btc: float) -> int:
    """Convert a USD amount into satoshis at the given BTC/USD rate.

    We round to the nearest whole satoshi. Bitcoin amounts are priced so that
    underpayment/overpayment variance of a few cents is acceptable.
    """
    if amount_usd <= 0 or usd_per_btc <= 0:
        return 0
    return int(round(amount_usd / usd_per_btc * 1e8))


async def derive_deposit_address(wallet_name: Optional[str] = None) -> str:
    """Return a BTC deposit address.

    If a static deposit address is configured (BLOCKCYPHER_STATIC_ADDRESS) it is
    returned as-is. Otherwise the next P2PKH address is derived from the HD
    wallet (BlockCypher maintains a per-wallet derivation counter, so each call
    yields a fresh, never-reused receiving address).
    """
    if BTC_STATIC_ADDRESS:
        return BTC_STATIC_ADDRESS
    wallet = wallet_name or BLOCKCYPHER_HD_WALLET
    url = f"{_base_url()}/wallets/hd/{wallet}/addresses/derive"
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(url, params={"token": _token()})
        resp.raise_for_status()
        data = resp.json()
    try:
        address = data["chains"][0]["chain_addresses"][0]["address"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected BlockCypher derive response: {data}") from exc
    return address


async def create_webhook(
    address: str,
    callback_url: str,
    event: str = "tx-confirmation",
    confirmations: int = MIN_CONFIRMATIONS,
) -> str:
    """Subscribe to confirmation/transaction events for a deposit address.

    Returns the BlockCypher webhook id (used to look it up / delete it later).
    """
    url = f"{_base_url()}/hooks"
    body: Dict[str, object] = {
        "event": event,
        "address": address,
        "url": callback_url,
    }
    if event == "tx-confirmation":
        body["confirmations"] = confirmations
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(url, params={"token": _token()}, json=body)
        resp.raise_for_status()
        data = resp.json()
    return data.get("id", "")


def verify_webhook_signature(
    body: bytes,
    event_token: str,
    secondary_token: str = "",
    token: Optional[str] = None,
) -> bool:
    """Verify that an incoming BlockCypher webhook is authentic.

    BlockCypher signs the raw request body with the API token and exposes the
    digests in the `X-EventToken` (and optionally `X-EventToken-Secondary`)
    headers. We recompute and compare the primary digest.
    """
    if not body:
        return False
    secret = (token or _token()).encode("utf-8")
    computed = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if event_token and hmac.compare_digest(computed, event_token):
        return True
    if secondary_token and hmac.compare_digest(computed, secondary_token):
        return True
    return False
