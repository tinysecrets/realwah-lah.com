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


def _parse_price(data: dict) -> float | None:
    """Extract a USD price from Coinbase- or Kraken-shaped payloads."""
    try:
        amount = (data.get("data") or {}).get("amount") or data.get("amount")
        if amount:
            return float(amount)
        result = data.get("result") or {}
        for pair in result.values():
            close = (pair.get("c") or [None])[0]
            if close:
                return float(close)
    except (TypeError, ValueError, AttributeError):
        return None
    return None


async def get_btc_usd_rate() -> float:
    """Return the current market price of 1 BTC in USD.

    Tries Coinbase, then Kraken. A frozen constant is used ONLY when the
    operator explicitly sets BTC_FALLBACK_USD (a conscious choice, logged
    loudly at error level); otherwise a dead oracle raises instead of
    silently mispricing deposits and payouts.
    """
    last_error: Exception | None = None
    for url in (PRICE_URL, PRICE_URL_SECONDARY):
        if not url:
            continue
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            price = _parse_price(data)
            if price and price > 0:
                return price
        except Exception as e:
            last_error = e
            logger.warning("BTC price fetch failed for %s: %s", url, e)
    explicit_fallback = (os.getenv("BTC_FALLBACK_USD") or "").strip()
    if explicit_fallback:
        try:
            price = float(explicit_fallback)
            if price > 0:
                logger.error(
                    "BTC oracle DOWN — pricing at operator fallback $%s. "
                    "Deposits/payouts continue at a STALE price; investigate immediately.",
                    explicit_fallback,
                )
                return price
        except ValueError:
            pass
    raise RuntimeError(f"BTC price oracle unavailable and no BTC_FALLBACK_USD set ({last_error})")


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
    raw_secret = token or _token()
    if not raw_secret:
        # No shared secret configured -> nothing can authenticate. Fail closed
        # (an empty-key HMAC would be forgeable by anyone who guesses that).
        logger.error("BlockCypher webhook verify called with no BLOCKCYPHER_TOKEN configured.")
        return False
    secret = raw_secret.encode("utf-8")
    computed = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if event_token and hmac.compare_digest(computed, event_token):
        return True
    if secondary_token and hmac.compare_digest(computed, secondary_token):
        return True
    return False


async def fetch_address_txrefs(address: str, limit: int = 10) -> list[dict]:
    """Return the latest transaction refs touching ``address``.

    Used by the deposit reconciler to (a) notice funds that arrived even when
    the BlockCypher webhook never fired, and (b) re-read confirmations for a
    remembered ``tx_hash``. Each txref has ``tx_hash``, ``value`` (satoshis,
    negative for outbound), ``confirmations`` and ``confirmed``.

    Returns an empty list on any error so callers degrade to "try again later"
    rather than crash.
    """
    url = f"{_base_url()}/addrs/{address}"
    params: Dict[str, object] = {"limit": limit}
    if _token():
        params["token"] = _token()
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001 — reconciler must never crash
        logger.warning("BlockCypher address digest failed for %s", address, exc_info=True)
        return []
    return data.get("txrefs") or []


async def fetch_tx_confirmation_count(tx_hash: str) -> int:
    """Return the current on-chain confirmation count for a transaction.

    Returns ``-1`` on failure so callers can distinguish "still unconfirmed"
    from "could not reach the network".
    """
    url = f"{_base_url()}/txs/{tx_hash}"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, params={"token": _token()} if _token() else {})
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001 — reconciler must never crash
        logger.warning("BlockCypher tx lookup failed for %s", tx_hash, exc_info=True)
        return -1
    return int(data.get("confirmations") or 0)
