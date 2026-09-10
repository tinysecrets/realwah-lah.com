"""Unit tests for the Bitcoin payment/money-path logic.

These cover deterministic, network-free functions: the USD<->satoshi pricing
and webhook signature verification. They do NOT require credentials or a live
backend. Deposit/credit-flow integration is exercised via the live HTTP test
suite when a deployment is available.
"""
from __future__ import annotations

import pytest

from services.btc_processor import (
    usd_to_satoshis,
    verify_webhook_signature,
)


class TestUsdToSatoshis:
    def test_known_rates(self):
        assert usd_to_satoshis(25, 60000) == 41667  # 25 / 60000 * 1e8
        assert usd_to_satoshis(100, 60000) == 166667
        assert usd_to_satoshis(1, 60000) == 1667

    def test_zero_and_negative(self):
        assert usd_to_satoshis(0, 60000) == 0
        assert usd_to_satoshis(-5, 60000) == 0
        assert usd_to_satoshis(10, 0) == 0

    def test_small_amount_rounding(self):
        # $25.50 at $62,000
        assert usd_to_satoshis(25.50, 62000) == 41129


class TestWebhookSignature:
    def test_valid_signature(self):
        body = b'{"event":"tx-confirmation","address":"1abc"}'
        import hashlib, hmac

        token = "secret"
        digest = hmac.new(token.encode(), body, hashlib.sha256).hexdigest()
        assert verify_webhook_signature(body, digest, token=token) is True

    def test_invalid_signature(self):
        body = b'{"event":"tx-confirmation"}'
        assert verify_webhook_signature(body, "not-a-valid-digest") is False

    def test_empty_body_rejected(self):
        assert verify_webhook_signature(b"", "any") is False

    def test_secondary_token(self):
        body = b'{"a":1}'
        import hashlib, hmac

        token = "secret"
        digest = hmac.new(token.encode(), body, hashlib.sha256).hexdigest()
        assert verify_webhook_signature(body, "primary", secondary_token=digest, token=token) is True
