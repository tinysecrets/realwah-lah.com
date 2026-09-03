"""Bitcoin payouts (Game Credits -> BTC) funded from a locally-custodied HD wallet.

Design
------
Payouts cannot be sent from the deposit address (Coinbase holds that key), so
a separate funding HD wallet keeps its *private* key server-side. Keys never
leave the server. BlockCypher is used only for chain lookup (UTXOs of the
funding address) and broadcasting the signed raw transaction.

Flow on approval:
  1. Derive the funding receive key/address (m/0'/0/0 and on).
  2. Fetch that address's UTXOs from BlockCypher.
  3. Build + sign a transaction server-side with `bit`, paying the user and
     sending any change back to the wallet's change key (m/0'/1/N).
  4. Broadcast the signed raw tx to BlockCypher `POST /txs/push`.

Key material (env): manage the funding wallet's xprv as BTC_PAYOUT_XPRV.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

import httpx
from bip_utils import Bip32Secp256k1
from bit import PrivateKey as BitPrivateKey
from bit.network.meta import Unspent

logger = logging.getLogger(__name__)

BLOCKCYPHER_BASE = os.getenv("BLOCKCYPHER_BASE", "https://api.blockcypher.com/v1/btc/main")
BLOCKCYPHER_TOKEN = os.getenv("BLOCKCYPHER_TOKEN", "")

# HD extended private key of the funding wallet. If unset, payouts are
# disabled and approvals will not attempt an on-chain send.
BTC_PAYOUT_XPRV = os.getenv("BTC_PAYOUT_XPRV", "")

# Receive addresses: m/0'/0/N  |  Change addresses: m/0'/1/N
DEFAULT_FEE_SAT_PER_BYTE = int(os.getenv("BTC_PAYOUT_FEE_SAT_PER_BYTE", "3"))

_HTTP_TIMEOUT = httpx.Timeout(20.0)


class PayoutError(Exception):
    """Raised when a payout cannot be prepared or broadcast."""


def has_custody_credentials() -> bool:
    """True if a funding key is configured so we can actually sign+send."""
    return bool(BTC_PAYOUT_XPRV)


def _base_url() -> str:
    return BLOCKCYPHER_BASE.rstrip("/")


def _root() -> Bip32Secp256k1:
    if not BTC_PAYOUT_XPRV:
        raise PayoutError("Payout wallet not configured (BTC_PAYOUT_XPRV missing)")
    return Bip32Secp256k1.FromExtendedKey(BTC_PAYOUT_XPRV.strip())


def _child(root: Bip32Secp256k1, branch: int, index: int):
    """Derive node m/0'/<branch>/<index>."""
    return root.DerivePath("m/0'").DerivePath(str(branch)).DerivePath(str(index))


def _signing_key(branch: int, index: int) -> BitPrivateKey:
    node = _child(_root(), branch, index)
    priv_int = node.PrivateKey().Raw().ToInt()
    return BitPrivateKey.from_int(priv_int)


def funding_address(index: int = 0) -> str:
    """Return the funding receive address at m/0'/0/index (P2PKH)."""
    return _signing_key(0, index).address


def change_address(index: int = 0) -> str:
    """Return the change address at m/0'/1/index (P2PKH)."""
    return _signing_key(1, index).address


async def get_funding_balance(index: int = 0) -> Tuple[int, List[Unspent]]:
    """Return (confirmed_satoshis, unspents) for a funding receive key."""
    key = _signing_key(0, index)
    unspents = await _fetch_unspents(key.address, key)
    total = sum(u.amount for u in unspents)
    return total, unspents


async def _fetch_unspents(address: str, key: BitPrivateKey) -> List[Unspent]:
    """Fetch confirmed, unspent outputs for an address from BlockCypher."""
    url = f"{_base_url()}/addrs/{address}"
    params = {"unspentOnly": "true", "token": BLOCKCYPHER_TOKEN}
    script_pubkey = key.scriptcode.hex()
    unspents: List[Unspent] = []
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            raise PayoutError(f"BlockCypher UTXO lookup failed ({resp.status_code})")
        data = resp.json()
        for txref in data.get("txrefs", []):
            if txref.get("spent"):
                continue
            unspents.append(
                Unspent(
                    amount=txref.get("value") or 0,
                    confirmations=txref.get("confirmations", 0),
                    script=script_pubkey,
                    txid=txref.get("tx_hash", ""),
                    txindex=txref.get("tx_output_n", 0),
                )
            )
    return [u for u in unspents if u.confirmations >= 1 and u.amount > 0]


async def send_btc(
    to_address: str,
    amount_sat: int,
    fee_sat_per_byte: int = DEFAULT_FEE_SAT_PER_BYTE,
) -> Tuple[bool, str, Optional[str]]:
    """Send `amount_sat` satoshis from the funding wallet to `to_address`.

    Returns (success, message, tx_hash). msg is machine-checkable for tests.
    """
    if not has_custody_credentials():
        return False, "payout_wallet_not_configured", None
    if amount_sat <= 0:
        return False, "invalid_amount_sat", None
    if not to_address or to_address[0] not in ("1", "3", "bc1"):
        return False, "invalid_btc_address", None

    # 1. Gather UTXOs across receive indexes until we cover the amount.
    all_unspents: List[Unspent] = []
    total_available = 0
    for idx in range(20):
        try:
            key = _signing_key(0, idx)
            unspents = await _fetch_unspents(key.address, key)
        except PayoutError as e:
            return False, f"utxo_lookup_error_{e}", None
        all_unspents.extend(unspents)
        total_available += sum(u.amount for u in unspents)
        if total_available >= amount_sat:
            break
        if not unspents:
            break

    if total_available < amount_sat:
        return False, f"insufficient_funding_{total_available}", None

    change_addr = change_address(0)

    # 2. Fee estimate: ~148 vB/input, ~34 vB/output, ~10 vB overhead.
    num_inputs = len(all_unspents)
    est_change_outs = 1
    est_vsize = 10 + num_inputs * 148 + (est_change_outs + 1) * 34
    fee_sat = max(est_vsize * fee_sat_per_byte, 1500)

    # If change would be below dust, sweep the entire remainder (minus fee)
    # to the recipient so we don't create an unspendable dust UTXO.
    change_sat = total_available - amount_sat - fee_sat
    if change_sat <= 546:
        est_vsize = 10 + num_inputs * 148 + 34
        fee_sat = max(est_vsize * fee_sat_per_byte, 1500)
        pay_sat = total_available - fee_sat
        leftover = to_address
    else:
        pay_sat = amount_sat
        leftover = change_addr

    if pay_sat <= 0:
        return False, "payout_nonpositive_after_fee", None

    # 3. Sign with funding key index 0.
    try:
        key = _signing_key(0, 0)
    except Exception as e:
        return False, f"signing_key_error_{e}", None

    try:
        tx_hex = key.create_transaction(
            unspents=all_unspents,
            outputs=[(to_address, pay_sat, "satoshi")],
            absolute_fee=True,
            fee=fee_sat,
            leftover=leftover,
        )
    except Exception as e:
        logger.error("Transaction build failed", exc_info=True)
        return False, f"tx_build_error_{e}", None

    if not tx_hex:
        return False, "tx_build_empty", None

    # 5. Broadcast via BlockCypher.
    return await _broadcast(tx_hex)


async def _broadcast(tx_hex: str) -> Tuple[bool, str, Optional[str]]:
    url = f"{_base_url()}/txs/push"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                url, params={"token": BLOCKCYPHER_TOKEN}, json={"tx": tx_hex}
            )
            data = resp.json()
        if resp.status_code in (200, 201):
            tx_hash = (
                data.get("hash")
                or (data.get("tx") or {}).get("hash")
                or data.get("tx_hash")
            )
            return True, "broadcast_ok", tx_hash
        err = data.get("error") or (len(data.get("errors", [])) and data["errors"][0]) or f"http_{resp.status_code}"
        logger.warning("Broadcast rejected: %s", err)
        return False, f"broadcast_rejected_{err}", None
    except Exception as e:
        logger.error("Broadcast error", exc_info=True)
        return False, f"broadcast_error_{e}", None


def usd_to_satoshis(amount_usd: float, usd_per_btc: float) -> int:
    if amount_usd <= 0 or usd_per_btc <= 0:
        return 0
    return int(round(amount_usd / usd_per_btc * 1e8))
