"""Distributor Hub Registry.

Each entry defines how the generic Playwright bridge should drive a specific
distributor portal. Adding a new hub = add a dict here + pilot-test via the
admin `ping` endpoint. No new Python class required.

Supported hubs
--------------
- sugar_sweeps   → https://sugarsweeps.com  (legacy; uses SugarSweepsBridge directly)
- bitbetwin      → https://bitbetwin.cc
- bitplay        → https://bitplay.ag
- bitspinwin     → https://bitspinwin.co
- bitofgold      → https://bitofgold.cc
- win777         → https://win777.us

Selector notes
--------------
Sites share a very common dashboard layout (platform list → transfer modal per
tile). Selectors below are *best-effort starting points* derived from public
homepages. Each admin operator can refine them per-hub in `HUB_CONFIGS` without
code changes to the bridge.
"""
from __future__ import annotations

from typing import Dict, List

HUB_CONFIGS: Dict[str, dict] = {
    "sugar_sweeps": {
        "label": "Sugar Sweeps",
        "base_url": "https://sugarsweeps.com",
        # HTTP fast-path: bypass Vercel WAF by talking to the .NET backend
        # directly. Discovered 2026-04-27 via console-log network capture —
        # api.sugarsweeps.com is Cloudflare-fronted but does NOT issue a bot
        # challenge (CORS preflight returns 204 with full headers, login POST
        # returns 401 on bad creds / 200 on success). When ``api_base_url`` is
        # present the bridge factory routes to ``HttpHubBridge`` instead of
        # spinning up Playwright.
        "api_base_url": "https://api.sugarsweeps.com",
        "api_paths": {
            "login": "/api/Auth/login",
            # transfer/balance paths still TBD — set after first live login
            # capture exposes the actual endpoints used by sugarsweeps.com.
        },
        "api_fields": {
            "username": "email",
            "password": "password",
            # "token": "accessToken",  # uncomment+adjust once live login response is captured
        },
        "login_path": "/",
        "dashboard_path": "/user/dashboard",
        "pre_login_click": [
            'button:has-text("Login"):visible',  # Opens the login modal (Radix dialog)
        ],
        "selectors": {
            # Scope all inputs to the modal (role="dialog") — the page has
            # both a Register form and a Login modal and we need the modal one.
            "email":     ['[role="dialog"] input[type="email"]', 'input[type="email"][placeholder*="email" i]', 'input[type="email"]'],
            "password":  ['[role="dialog"] input[type="password"]:not([placeholder*="Confirm" i])', 'input[type="password"]:not([placeholder*="Confirm" i])'],
            "submit":    ['[role="dialog"] button:has-text("Login"):visible', '[role="dialog"] button[type="submit"]', 'form button[type="submit"]'],
            "transfer_nav": ['a[href*="transfer"]', 'a[href*="user/dashboard"]', 'button:has-text("Transfer")'],
            "platform_dropdown": ['select[name="platform"]', '[role="combobox"]', 'button:has-text("Select a platform")'],
            "recipient": ['input[name="recipient"]', 'input[name="username"]', 'input[name="player"]'],
            "amount":    ['input[name="amount"]', 'input[type="number"]'],
            "confirm":   ['button[type="submit"]', 'button:has-text("Transfer")', 'button:has-text("Send")'],
            "balance":   ['.balance', '#balance', '[data-balance]', 'span:has-text("Balance")'],
        },
        "supported_platforms": [
            "fire_kirin", "orion_stars", "ultra_panda", "juwa", "juwa2",
            "panda_master", "game_vault", "vblink", "milky_way", "noble",
            "vegas_x", "river_sweeps",
        ],
    },
    "bitbetwin": {
        "label": "BitBetWin",
        "base_url": "https://bitbetwin.cc",
        "login_path": "/login",
        "dashboard_path": "/platforms",
        "selectors": {
            "email":     ['input[type="email"]', 'input[name="email"]', 'input[name="username"]'],
            "password":  ['input[type="password"]'],
            "submit":    ['button[type="submit"]', 'button:has-text("Login")', 'button:has-text("Sign In")'],
            "transfer_nav": ['a[href*="transfer"]', 'a[href*="platforms"]', 'button:has-text("Recharge")'],
            "platform_dropdown": ['select[name="platform"]', '[role="combobox"]', 'button:has-text("Select")'],
            "recipient": ['input[name="username"]', 'input[name="recipient"]', 'input[placeholder*="username" i]'],
            "amount":    ['input[name="amount"]', 'input[type="number"]'],
            "confirm":   ['button[type="submit"]', 'button:has-text("Recharge")', 'button:has-text("Transfer")'],
            "balance":   ['.balance', '[data-balance]', 'span:has-text("Balance")'],
        },
        "supported_platforms": [
            "fire_kirin", "orion_stars", "ultra_panda", "juwa", "panda_master",
            "game_vault", "vblink", "milky_way",
        ],
    },
    "bitplay": {
        "label": "BitPlay",
        "base_url": "https://bitplay.ag",
        "login_path": "/login",
        "dashboard_path": "/user/dashboard",
        "selectors": {
            "email":     ['input[name="email"]', 'input[name="username"]', 'input[type="email"]'],
            "password":  ['input[type="password"]'],
            "submit":    ['button[type="submit"]', 'button:has-text("Login")'],
            "transfer_nav": ['a[href*="platforms"]', 'a[href*="transfer"]'],
            "platform_dropdown": ['select', '[role="combobox"]'],
            "recipient": ['input[name="username"]', 'input[name="player"]'],
            "amount":    ['input[name="amount"]', 'input[type="number"]'],
            "confirm":   ['button[type="submit"]', 'button:has-text("Submit")', 'button:has-text("Transfer")'],
            "balance":   ['.balance', '[data-balance]'],
        },
        "supported_platforms": [
            "fire_kirin", "orion_stars", "ultra_panda", "juwa", "panda_master", "game_vault",
        ],
    },
    "bitspinwin": {
        "label": "BitSpinWin",
        "base_url": "https://bitspinwin.co",
        "login_path": "/login",
        "dashboard_path": "/user/dashboard",
        "selectors": {
            "email":     ['input[name="email"]', 'input[type="email"]'],
            "password":  ['input[type="password"]'],
            "submit":    ['button[type="submit"]', 'button:has-text("Login")'],
            "transfer_nav": ['a[href*="platforms"]', 'a[href*="dashboard"]'],
            "platform_dropdown": ['select', '[role="combobox"]'],
            "recipient": ['input[name="username"]', 'input[name="player"]'],
            "amount":    ['input[name="amount"]', 'input[type="number"]'],
            "confirm":   ['button[type="submit"]', 'button:has-text("Transfer")'],
            "balance":   ['.balance', '[data-balance]'],
        },
        "supported_platforms": [
            "fire_kirin", "orion_stars", "ultra_panda", "juwa", "panda_master", "game_vault",
        ],
    },
    "bitofgold": {
        "label": "BitOfGold",
        "base_url": "https://bitofgold.cc",
        "login_path": "/login",
        "dashboard_path": "/user/platforms",
        "selectors": {
            "email":     ['input[name="email"]', 'input[type="email"]', 'input[name="username"]'],
            "password":  ['input[type="password"]'],
            "submit":    ['button[type="submit"]', 'button:has-text("Login")'],
            "transfer_nav": ['a[href*="platforms"]', 'a[href*="transfer"]'],
            "platform_dropdown": ['select', '[role="combobox"]'],
            "recipient": ['input[name="username"]', 'input[name="player"]'],
            "amount":    ['input[name="amount"]', 'input[type="number"]'],
            "confirm":   ['button[type="submit"]', 'button:has-text("Transfer")'],
            "balance":   ['.balance', '[data-balance]'],
        },
        "supported_platforms": [
            "fire_kirin", "orion_stars", "ultra_panda", "juwa", "panda_master", "game_vault",
        ],
    },
    "win777": {
        "label": "Win777",
        "base_url": "https://win777.us",
        "login_path": "/login",
        "dashboard_path": "/user/platforms",
        "selectors": {
            "email":     ['input[name="email"]', 'input[type="email"]', 'input[name="username"]'],
            "password":  ['input[type="password"]'],
            "submit":    ['button[type="submit"]', 'button:has-text("Login")'],
            "transfer_nav": ['a[href*="platforms"]', 'a[href*="transfer"]'],
            "platform_dropdown": ['select', '[role="combobox"]'],
            "recipient": ['input[name="username"]', 'input[name="player"]'],
            "amount":    ['input[name="amount"]', 'input[type="number"]'],
            "confirm":   ['button[type="submit"]', 'button:has-text("Transfer")'],
            "balance":   ['.balance', '[data-balance]'],
        },
        "supported_platforms": [
            "fire_kirin", "orion_stars", "ultra_panda", "juwa", "panda_master", "game_vault",
        ],
    },
}


def list_hubs() -> List[dict]:
    return [
        {
            "hub_type": k,
            "label": v["label"],
            "base_url": v["base_url"],
            "supported_platforms": v.get("supported_platforms", []),
        }
        for k, v in HUB_CONFIGS.items()
    ]


def get_hub(hub_type: str) -> dict:
    return HUB_CONFIGS.get(hub_type, HUB_CONFIGS["sugar_sweeps"])
