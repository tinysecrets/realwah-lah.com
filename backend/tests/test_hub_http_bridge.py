"""Regression tests for the HTTP fast-path hub bridge.

These verify two things without ever needing real distributor credentials:

1. The factory returns ``HttpHubBridge`` for hubs declaring ``api_base_url``
   (sugar_sweeps) and falls back to ``GenericHubBridge`` otherwise.
2. A live ``ping`` against ``https://api.sugarsweeps.com/api/Auth/login`` with
   bogus creds gets a clean 401 — proving the Vercel WAF bypass holds.

The second test hits a public endpoint over the internet; if outbound
networking is sandboxed it is skipped.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.hub_bridge import make_bridge  # noqa: E402
from services.hub_http_bridge import HttpHubBridge  # noqa: E402


def test_factory_routes_sugar_sweeps_to_http():
    b = make_bridge("sugar_sweeps", "u@x.com", "pw", base_url="https://sugarsweeps.com")
    assert isinstance(b, HttpHubBridge)
    assert b.api_base == "https://api.sugarsweeps.com"
    assert b.api_paths.get("login") == "/api/Auth/login"


def test_factory_falls_back_to_playwright_for_others():
    from services.hub_bridge import GenericHubBridge

    b = make_bridge("bitbetwin", "u", "p")
    assert isinstance(b, GenericHubBridge)
    assert not isinstance(b, HttpHubBridge)


@pytest.mark.skipif(os.environ.get("SKIP_NET_TESTS") == "1", reason="net disabled")
def test_live_ping_bad_creds_returns_clean_401():
    """Smoke test: confirms api.sugarsweeps.com reachable (no WAF challenge)."""
    async def _run():
        b = make_bridge("sugar_sweeps", "fake@example.com", "Wrong123!", base_url="https://sugarsweeps.com")
        try:
            ok, msg, diag = await b.ping()
        finally:
            await b.close()
        return ok, msg, diag

    ok, msg, diag = asyncio.run(_run())
    assert ok is False
    # The exact wording is in HttpHubBridge.ping() — this catches drift.
    assert "401" in msg, msg
    steps = diag.get("steps", [])
    assert steps and steps[0]["step"] == "login_post"
    assert steps[0]["status"] == 401
    assert steps[0]["url"] == "https://api.sugarsweeps.com/api/Auth/login"
