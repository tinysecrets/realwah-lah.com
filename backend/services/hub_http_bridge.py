"""HTTP-only distributor hub bridge — bypasses Playwright + Vercel WAF.

When a hub config in ``services/hub_registry.HUB_CONFIGS`` declares
``api_base_url`` the system can talk straight to the distributor's REST
backend (e.g. ``https://api.sugarsweeps.com``) instead of scraping the
Vercel-hosted HTML, which is hard-blocked by Vercel's bot challenge for
datacenter IPs (Fly.io, AWS, etc.).

The class exposes the same public surface as ``GenericHubBridge``
(``ping`` / ``transfer`` / ``close`` returning ``(ok, msg, diagnostic)``)
so existing call sites in ``routes/distributor_pool.py`` are agnostic to
which bridge they got from the factory.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from services.hub_registry import get_hub

logger = logging.getLogger(__name__)


def _dig(data: Any, keys) -> Optional[Any]:
    """Pluck the first matching key out of a possibly-nested JSON response."""
    if not isinstance(data, dict):
        return None
    for k in keys:
        if k in data and data[k] is not None:
            return data[k]
    # one-level deep into common wrappers (.data / .result / .payload)
    for wrapper in ("data", "result", "payload"):
        nested = data.get(wrapper)
        if isinstance(nested, dict):
            for k in keys:
                if k in nested and nested[k] is not None:
                    return nested[k]
    return None


class HttpHubBridge:
    def __init__(
        self,
        hub_type: str,
        username: str,
        password: str,
        base_url: Optional[str] = None,
    ):
        self.hub_type = hub_type
        self.hub = get_hub(hub_type)
        self.username = username
        self.password = password
        # ``base_url`` from the proxy doc (HTML site) is kept for diagnostic
        # only — actual calls hit ``api_base_url`` from the hub config.
        self.html_base = base_url or self.hub["base_url"]
        self.api_base: str = self.hub["api_base_url"].rstrip("/")
        self.api_paths: Dict[str, str] = self.hub.get("api_paths", {})
        self.api_fields: Dict[str, str] = self.hub.get("api_fields", {})
        self.token: Optional[str] = None
        self._client = None
        self.diagnostic: Dict[str, Any] = {
            "hub_type": hub_type,
            "mode": "http",
            "html_base": self.html_base,
            "api_base": self.api_base,
            "steps": [],
        }

    # --- helpers ---
    def _step(self, name: str, **data):
        self.diagnostic["steps"].append({"step": name, **data})

    async def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Origin": self.html_base.rstrip("/"),
                    "Referer": self.html_base.rstrip("/") + "/",
                },
            )
        return self._client

    # --- ping (login probe) ---
    async def ping(self) -> Tuple[bool, str, Dict[str, Any]]:
        login_path = self.api_paths.get("login", "/api/Auth/login")
        user_field = self.api_fields.get("username", "email")
        pass_field = self.api_fields.get("password", "password")

        body = {user_field: self.username, pass_field: self.password}
        url = self.api_base + login_path
        client = await self._get_client()

        try:
            resp = await client.post(url, json=body)
        except Exception as e:
            self._step("login_post_error", url=url, error=str(e))
            return False, f"Network error reaching {url}: {e}", self.diagnostic

        body_preview = (resp.text or "")[:400]
        self._step(
            "login_post",
            url=url,
            status=resp.status_code,
            field_user=user_field,
            field_pass=pass_field,
            body_preview=body_preview,
        )

        if resp.status_code == 401:
            return False, "Auth rejected (401) — bad credentials or wrong api_fields", self.diagnostic
        if resp.status_code == 400:
            return False, f"Bad request (400) — server says: {body_preview[:180]}", self.diagnostic
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code} on login: {body_preview[:200]}", self.diagnostic

        try:
            data = resp.json()
        except Exception:
            return False, f"Login {resp.status_code} but body wasn't JSON", self.diagnostic

        token_field = self.api_fields.get("token")
        token_keys = [token_field] if token_field else [
            "token", "accessToken", "access_token", "jwt", "Token", "AccessToken",
        ]
        self.token = _dig(data, token_keys)

        if not self.token:
            self._step("login_token_missing", keys_searched=token_keys, response_keys=list(data.keys()) if isinstance(data, dict) else None)
            return False, (
                f"Login OK ({resp.status_code}) but no token in response — "
                f"set api_fields.token in hub_registry. Saw keys: "
                f"{list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
            ), self.diagnostic

        self._step("login_ok", token_len=len(str(self.token)))
        return True, f"Login OK via {self.api_base} (HTTP fast-path, no Playwright)", self.diagnostic

    # --- transfer ---
    async def transfer(
        self, recipient: str, amount: float, platform: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        ok, msg, _ = await self.ping()
        if not ok:
            return False, msg, self.diagnostic

        transfer_path = self.api_paths.get("transfer")
        if not transfer_path:
            return False, (
                "Transfer endpoint not configured — add api_paths.transfer in "
                "hub_registry.py for this hub. (Login + token retrieval works.)"
            ), self.diagnostic

        recipient_field = self.api_fields.get("recipient", "username")
        amount_field = self.api_fields.get("amount", "amount")
        platform_field = self.api_fields.get("platform", "platform")

        body = {
            recipient_field: recipient,
            amount_field: int(amount),
            platform_field: platform,
        }
        url = self.api_base + transfer_path
        client = await self._get_client()

        try:
            resp = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {self.token}"},
            )
        except Exception as e:
            self._step("transfer_post_error", url=url, error=str(e))
            return False, f"Network error on transfer: {e}", self.diagnostic

        preview = (resp.text or "")[:400]
        self._step("transfer_post", url=url, status=resp.status_code, body_preview=preview)

        if 200 <= resp.status_code < 300:
            return True, f"Transfer OK (HTTP {resp.status_code})", self.diagnostic
        return False, f"Transfer failed HTTP {resp.status_code}: {preview[:200]}", self.diagnostic

    async def close(self):
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # pragma: no cover — defensive
                pass
            self._client = None
