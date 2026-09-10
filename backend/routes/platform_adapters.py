"""
Real (HTTP) platform registration adapter for the JIT framework.

Framework (routes/platform_jit.py) exposes a plug-in seam:
    PlatformAdapter.register(username, password, context) -> (bool, platform_uid|err)
and a registry (`register_adapter(platform_id, adapter)`). Until now only the
dry-run stub was wired, so ``/ext/platform/register`` "succeeded" without ever
creating an account on the actual game.

This module provides a real HTTP adapter driven by the distributor-hub config in
``services/hub_registry.HUB_CONFIGS`` (same source the transfer bridge uses).

Behavior
--------
- If the hub config declares ``api_paths.register`` (paste it in once the live
  register call is captured — see scripts/capture_hub_api.py), this adapter makes
  a REAL POST to the distributor backend and returns the platform UID.
- Until then it degrades to the dry-run behavior (returns the master username as
  the UID) so the current flow keeps working while the endpoint is TBD. It logs a
  clear "dry-run (not real)" marker so nobody mistakes it for live registration.

Body / response shapes are configurable per-hub via ``api_fields`` so a pasted-in
endpoint works without code changes. No credentials or tokens are logged.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from routes.platform_jit import PlatformAdapter, register_adapter
from services.hub_registry import get_hub

logger = logging.getLogger(__name__)

# Preferred keys (in order) for the platform UID inside the register response.
_UID_KEYS = ("uid", "id", "userId", "user_id", "playerId", "player_id", "accountId",
             "username", "email")


def _extract_uid(data: Any, fallback: str) -> str:
    """Pull the platform UID out of a possibly-nested JSON response."""
    if isinstance(data, dict):
        for k in _UID_KEYS:
            if k in data and data[k]:
                return str(data[k])
        for wrapper in ("data", "result", "payload", "user"):
            nested = data.get(wrapper)
            if isinstance(nested, dict):
                for k in _UID_KEYS:
                    if k in nested and nested[k]:
                        return str(nested[k])
    return fallback


class HubRegisterAdapter(PlatformAdapter):
    """Real HTTP registration adapter for a distributor hub / game platform.

    Fields (aligned with HUB_CONFIGS.api_fields / api_paths):

      platform_id       — the id this adapter is bound to (game.platform_id or
                          a game_id such as 'fire_kirin').
      hub_type          — which HUB_CONFIGS entry provides the base url + paths.
      username_field    — request body key for the master username (default 'username').
      password_field    — request body key for the master password (default 'password').
      uid_field         — response key/keys to treat as the platform UID.
    """

    platform_id: str = "default"
    label: str = "Hub HTTP Register"

    def __init__(
        self,
        platform_id: str,
        hub_type: str = "sugar_sweeps",
        username_field: str = "username",
        password_field: str = "password",
    ):
        self.platform_id = platform_id
        self.hub_type = hub_type
        self.username_field = username_field
        self.password_field = password_field

    async def register(
        self, username: str, password: str, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        if not username or not password:
            return False, "Missing master credentials"

        hub = get_hub(self.hub_type)
        api_base = (hub.get("api_base_url") or "").rstrip("/")
        register_path = (hub.get("api_paths") or {}).get("register")

        if not api_base or not register_path:
            # Endpoint not captured yet — keep current behavior but flag it so
            # this is never mistaken for a real registration.
            logger.warning(
                "hub=%s platform=%s register is in dry-run (api_paths.register TBD)",
                self.hub_type, self.platform_id,
            )
            return True, username

        # Prefer per-hub field names, else the adapter's configured names.
        fields: Dict[str, str] = hub.get("api_fields") or {}
        user_field = fields.get("username") or self.username_field
        pass_field = fields.get("password") or self.password_field

        url = api_base + register_path
        body = {user_field: username, pass_field: password}

        import httpx

        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json, text/plain, */*",
                    "Origin": hub.get("base_url", "").rstrip("/"),
                    "Referer": hub.get("base_url", "").rstrip("/") + "/",
                },
            ) as client:
                resp = await client.post(url, json=body)
        except Exception as e:
            logger.error("hub=%s platform=%s register network error: %s",
                         self.hub_type, self.platform_id, e)
            return False, f"Register network error: {e}"

        if not (200 <= resp.status_code < 300):
            preview = (resp.text or "")[:200]
            logger.warning("hub=%s platform=%s register HTTP %s",
                           self.hub_type, self.platform_id, resp.status_code)
            return False, f"Register failed HTTP {resp.status_code}: {preview}"

        try:
            data = resp.json()
        except Exception:
            data = None

        uid = _extract_uid(data, fallback=username)
        logger.info("hub=%s platform=%s registered uid=%s",
                    self.hub_type, self.platform_id, uid)
        return True, uid


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------
# Bind the real HTTP adapter to the distributor's supported player platforms so
# the JIT framework stops dry-running on real games. The master credentials are
# the user's auto-generated game_username/game_password (the account registered
# against the platform). Fall back to dry-run only when api_paths.register is
# still TBD in hub_registry.py.
def bind_hub_register_adapters(hub_type: str = "sugar_sweeps") -> None:
    """Register the HubRegisterAdapter for every supported platform of a hub."""
    hub = get_hub(hub_type)
    for platform_id in hub.get("supported_platforms", []):
        register_adapter(platform_id, HubRegisterAdapter(platform_id, hub_type=hub_type))
    logger.info("Bound HubRegisterAdapter for %d platforms of hub '%s'",
                len(hub.get("supported_platforms", [])), hub_type)