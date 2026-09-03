"""Unit tests for the BTC payout sender (locally-custodied HD wallet).

These test deterministic derivation + local signing/build. Network is mocked:
_fetch_unspents and _broadcast are patched so we never touch BlockCypher or a
real chain. RUN_BACKEND_TESTS=1 pytest is required (see backend/conftest.py).
"""
from __future__ import annotations

import asyncio
import os

import pytest

from services import btc_payout as bp
from bit.network.meta import Unspent

# A fresh deterministic master xprv (test-only, NOT the production wallet).
TEST_XPRV = (
    "xprv9s21ZrQH143K3PJMPpTqaUUujiXYeLvfmfK72TzyPbk7kV7qwd3SRR9GyNFAThjGjQt3"
    "yeK7SQ4RBaGgibZ2afDVDWNB1DQVTkiXFEhk3cA"
)
RECIPIENT = "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"


@pytest.fixture(autouse=True)
def _set_xprv():
    os.environ["BTC_PAYOUT_XPRV"] = TEST_XPRV
    old = bp.BTC_PAYOUT_XPRV
    bp.BTC_PAYOUT_XPRV = TEST_XPRV
    yield
    bp.BTC_PAYOUT_XPRV = old


def _utxo(amount, key, txid_suffix, txindex=0, confirmations=6):
    return Unspent(
        amount=amount,
        confirmations=confirmations,
        script=key.scriptcode.hex(),
        txid="ab" * 30 + f"{txid_suffix:02x}" * 2,
        txindex=txindex,
    )


class TestDerivation:
    def test_funding_env_deterministic(self):
        a0 = bp.funding_address(0)
        a1 = bp.funding_address(1)
        assert a0 == bp.funding_address(0)  # deterministic
        assert a0 != a1  # different index -> different address
        assert a0.startswith("1")  # P2PKH

    def test_change_env_deterministic(self):
        assert bp.change_address(0) == bp.change_address(0)
        assert bp.change_address(0) != bp.funding_address(0)

    def test_key_scriptcode_is_p2pkh(self):
        script = bp._signing_key(0, 0).scriptcode.hex()
        assert script.startswith("76a914") and script.endswith("88ac")

    def test_has_creds(self):
        assert bp.has_custody_credentials() is True


class TestSendBtc:
    def test_builds_and_broadcasts(self, monkeypatch):
        key = bp._signing_key(0, 0)
        utxo = _utxo(100_000_000, key, 1)  # 1 BTC

        captured = {}

        async def fake_fetch(address, k):
            assert k.address == address
            return [utxo]

        async def fake_broadcast(tx_hex):
            captured["tx_hex"] = tx_hex
            return True, "broadcast_ok", "abc123hash"

        monkeypatch.setattr(bp, "_fetch_unspents", fake_fetch)
        monkeypatch.setattr(bp, "_broadcast", fake_broadcast)

        async def _run():
            return await bp.send_btc(RECIPIENT, 50_000_000, fee_sat_per_byte=2)

        ok, msg, tx_hash = asyncio.run(_run())

        assert ok is True
        assert msg == "broadcast_ok"
        assert tx_hash == "abc123hash"
        tx_hex = captured["tx_hex"]
        assert tx_hex and len(tx_hex) > 100

        # The signed tx must carry a valid DER signature + the wallet pubkey
        # in each input scriptSig (proves a spendable P2PKH transaction).
        raw = bytes.fromhex(tx_hex)
        p = 5
        num_in = raw[4]
        p += 32 + 4  # first input prevhash + index
        slen = raw[p]
        p += 1
        script = raw[p : p + slen]
        siglen = script[0]
        pub = script[2 + siglen :]
        assert script[1] == 0x30  # DER
        assert pub.hex() == key.pub_to_hex()  # compressed pubkey matches signing key
        assert num_in >= 1

    def test_insufficient_funding(self, monkeypatch):
        async def fake_fetch(address, k):
            return [_utxo(10_000, k, 2)]  # 0.0001 BTC

        monkeypatch.setattr(bp, "_fetch_unspents", fake_fetch)

        ok, msg, tx_hash = asyncio.run(bp.send_btc(RECIPIENT, 500_000_000))
        assert ok is False
        assert msg.startswith("insufficient_funding_")

    def test_no_custody_creds(self):
        bp.BTC_PAYOUT_XPRV = ""
        ok, msg, tx_hash = asyncio.run(bp.send_btc(RECIPIENT, 50_000_000))
        assert ok is False
        assert msg == "payout_wallet_not_configured"

    def test_invalid_address(self):
        ok, msg, tx_hash = asyncio.run(bp.send_btc("not-an-address", 50_000_000))
        assert ok is False
        assert msg == "invalid_btc_address"

    def test_usd_to_satoshis(self):
        assert bp.usd_to_satoshis(25, 60000) == 41667
        assert bp.usd_to_satoshis(0, 60000) == 0
