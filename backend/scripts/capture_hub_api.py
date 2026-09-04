#!/usr/bin/env python3
"""
Standalone Hub API capture script.

Discovers the live login/transfer/register endpoint paths and field names
on a distributor hub (e.g. sugarsweeps.com) so you can paste them into
``backend/services/hub_registry.py`` and go live.

No backend dependencies required — just ``httpx`` (for --http-only) or
``playwright`` (for browser capture). Never prints credentials, tokens,
or secrets.

THREE MODES
-----------
1. --http-only   (recommended first step — no browser needed)
   Just verifies the HTTP login and detects the token response key.
   Requires: pip install httpx

2. --browse      (headed browser — drive login + transfer by hand)
   Opens a visible browser. You log in and do the transfer manually.
   The script captures every API call in the background and prints
   the endpoint/field names at the end.
   Requires: pip install playwright && playwright install chromium

3. (default)     (headless browser — automates login + transfer)
   Attempts to auto-fill the login form and drive the transfer via
   CSS selectors from hub_registry.py. Falls back to manual browse
   if selectors don't match.
   Requires: pip install playwright && playwright install chromium

USAGE
-----
    # Step 1: verify login works and find the token key
    export HUB_USERNAME="your@email.com"
    export HUB_PASSWORD="yourpassword"
    python scripts/capture_hub_api.py --http-only

    # Step 2: capture the transfer + register endpoints
    export HUB_RECIPIENT="testplayer"   # a real test recipient
    export HUB_AMOUNT=1                 # small real amount
    python scripts/capture_hub_api.py --browse

    # Or try headless auto-drive:
    python scripts/capture_hub_api.py

OUTPUT
------
Prints a complete, copy-paste-ready snippet for hub_registry.py.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# ── Constants ────────────────────────────────────────────────────────────
HUB_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "services" / "hub_registry.py"

TOKEN_CANDIDATES = (
    "token", "accessToken", "access_token", "jwt", "Token",
    "AccessToken", "accessJwt", "id_token", "idToken",
)

# Fields that commonly identify a transfer request body.
TRANSFER_BODY_HINTS = ("recipient", "username", "player", "to", "send_to", "account")
AMOUNT_BODY_HINTS = ("amount", "credits", "value", "balance", "quantity")
PLATFORM_BODY_HINTS = ("platform", "game", "gameId", "game_id", "type")

# Hub defaults — standalone, no backend imports.
HUB_DEFAULTS = {
    "sugar_sweeps": {
        "label": "Sugar Sweeps",
        "base_url": "https://sugarsweeps.com",
        "api_base_url": "https://sugarsweeps.com/api/proxy",
        "login_path": "/",
        "api_fields": {"username": "email", "password": "password"},
        "pre_login_click": ['button:has-text("Login"):visible'],
        "selectors": {
            "email": ['[role="dialog"] input[type="email"]', 'input[type="email"]'],
            "password": ['[role="dialog"] input[type="password"]:not([placeholder*="Confirm" i])'],
            "submit": ['[role="dialog"] button:has-text("Login"):visible', 'form button[type="submit"]'],
            "transfer_nav": ['a[href*="transfer"]', 'button:has-text("Transfer")'],
            "recipient": ['input[name="recipient"]', 'input[name="username"]', 'input[placeholder*="username" i]'],
            "amount": ['input[name="amount"]', 'input[type="number"]'],
            "confirm": ['button[type="submit"]', 'button:has-text("Transfer")', 'button:has-text("Send")'],
        },
    },
}


# ── Helpers ──────────────────────────────────────────────────────────────
def _redact(value: str) -> str:
    """Redact anything that looks like a credential or token."""
    if not value:
        return value
    if len(value) >= 20:
        return f"<REDACTED {len(value)} chars>"
    lower = value.lower()
    if any(k in lower for k in ("bearer", "token", "password", "apikey", "api_key", "authorization")):
        return "<REDACTED>"
    return value


def _guess_token_field(data: dict) -> str:
    """Best-guess the token key from a login response JSON."""
    if not isinstance(data, dict):
        return "<not a dict>"
    # Check top-level keys.
    for k in data:
        if k in TOKEN_CANDIDATES:
            return k
    # Check one level deep (.data, .result, .payload).
    for wrapper in ("data", "result", "payload", "user"):
        nested = data.get(wrapper)
        if isinstance(nested, dict):
            for k in nested:
                if k in TOKEN_CANDIDATES:
                    return f"{wrapper}.{k}"
    return f"<not found — keys: {list(data.keys())[:10]}>"


def _guess_transfer_fields(data: dict) -> dict:
    """Best-guess the transfer request body field names."""
    if not isinstance(data, dict):
        return {}
    result = {}
    for k, hints in [
        ("recipient", TRANSFER_BODY_HINTS),
        ("amount", AMOUNT_BODY_HINTS),
        ("platform", PLATFORM_BODY_HINTS),
    ]:
        found = next((h for h in hints if h in data), None)
        if found:
            result[k] = found
    return result


def _dump_capture(captured: list, api_hosts: set, login_responses: list,
                  transfer_candidates: list, register_candidates: list):
    """Print the captured data in a structured, readable way."""
    print(f"\n{'='*70}")
    print("CAPTURE COMPLETE — here's what was found:")
    print(f"{'='*70}")

    # ── [1] Login / Token ──
    print("\n[1] LOGIN — set api_fields.token to the key holding the JWT:\n")
    if login_responses:
        for resp in login_responses[:3]:
            url = urlparse(resp["url"])
            print(f"  {resp.get('method', 'POST')} {resp['url']}")
            print(f"  status={resp['status']}")
            if resp.get("body"):
                try:
                    j = json.loads(resp["body"])
                    print(f"  JSON keys: {list(j.keys()) if isinstance(j, dict) else type(j).__name__}")
                    token_field = _guess_token_field(j)
                    print(f"  → token key: \"{token_field}\"")
                except Exception:
                    print(f"  body (redacted): {_redact(resp['body'][:200])}")
            print()
    else:
        print("  No login response captured.\n")

    # ── [2] Transfer ──
    print("[2] TRANSFER — set api_paths.transfer + api_fields.*:\n")
    if transfer_candidates:
        for req in transfer_candidates[:5]:
            url = urlparse(req["url"])
            print(f"  {req['method']} {req['url']}")
            print(f"  → api_paths.transfer = \"{url.path}\"")
            auth = req.get("headers", {}).get("authorization", "")
            print(f"  Authorization header: {'Bearer <token>' if 'bearer' in auth.lower() else 'present' if auth else 'none'}")
            body_preview = _redact(req.get("body") or "")
            print(f"  Body (redacted): {body_preview[:300]}")
            # Try to guess field names from the body.
            try:
                body_data = json.loads(req.get("body") or "{}")
                fields = _guess_transfer_fields(body_data)
                if fields:
                    print(f"  → field guesses: {json.dumps(fields)}")
            except Exception:
                pass
            print()
    else:
        print("  No transfer request auto-detected.\n")
        # Dump all POST/PUT/PATCH API calls so the user can pick manually.
        print("  All API POST/PUT/PATCH calls (pick the transfer one):\n")
        seen = set()
        for entry in captured:
            if (entry["kind"] == "request"
                    and entry.get("method") in ("POST", "PUT", "PATCH")):
                url = urlparse(entry["url"])
                if url.netloc in api_hosts and url.path not in seen:
                    seen.add(url.path)
                    body_preview = _redact(entry.get("body") or "")
                    print(f"    {entry['method']} {url.path}  →  {body_preview[:120]}")
        print()

    # ── [3] Register ──
    print("[3] REGISTER — set api_paths.register + api_fields.username/password:\n")
    if register_candidates:
        for req in register_candidates[:5]:
            url = urlparse(req["url"])
            print(f"  {req['method']} {req['url']}")
            print(f"  → api_paths.register = \"{url.path}\"")
            body_preview = _redact(req.get("body") or "")
            print(f"  Body (redacted): {body_preview[:300]}")
            print()
    else:
        print("  No register request auto-detected.\n")
        print("  All API POST/PUT/PATCH calls NOT matching login/transfer:\n")
        seen_login = {
            urlparse(r["url"]).path.lower()
            for r in login_responses
        }
        seen_transfer = {
            urlparse(r["url"]).path.lower()
            for r in transfer_candidates
        }
        seen = set()
        for entry in captured:
            if (entry["kind"] == "request"
                    and entry.get("method") in ("POST", "PUT", "PATCH")):
                url = urlparse(entry["url"])
                low = url.path.lower()
                if (url.netloc in api_hosts
                        and low not in seen
                        and low not in seen_login
                        and low not in seen_transfer):
                    seen.add(low)
                    body_preview = _redact(entry.get("body") or "")
                    print(f"    {entry['method']} {url.path}  →  {body_preview[:120]}")
        print()

    # ── [4] Summary / copy-paste snippet ──
    print(f"{'='*70}")
    print("COPY-PASTE SNIPPET for hub_registry.py:")
    print(f"{'='*70}\n")

    # Build the snippet from what we found.
    login_key = ""
    transfer_path = ""
    register_path = ""
    field_guesses = {}

    if login_responses:
        for resp in login_responses[:1]:
            try:
                j = json.loads(resp.get("body") or "{}")
                login_key = _guess_token_field(j)
            except Exception:
                pass

    if transfer_candidates:
        url = urlparse(transfer_candidates[0]["url"])
        transfer_path = url.path
        try:
            body_data = json.loads(transfer_candidates[0].get("body") or "{}")
            field_guesses = _guess_transfer_fields(body_data)
        except Exception:
            pass

    if register_candidates:
        url = urlparse(register_candidates[0]["url"])
        register_path = url.path

    snippet_lines = [
        '# ─── PASTE BELOW into HUB_CONFIGS["sugar_sweeps"] ───────────────',
        '"api_paths": {',
        '    "login": "/api/Auth/login",',
    ]
    if transfer_path:
        snippet_lines.append(f'    "transfer": "{transfer_path}",')
    else:
        snippet_lines.append('    # "transfer": "<paste transfer path>",')
    if register_path:
        snippet_lines.append(f'    "register": "{register_path}",')
    else:
        snippet_lines.append('    # "register": "<paste register path — or omit if none>",')
    snippet_lines.append('},')
    snippet_lines.append('"api_fields": {')
    snippet_lines.append('    "username": "email",')
    snippet_lines.append('    "password": "password",')
    if login_key and "<not found" not in login_key:
        snippet_lines.append(f'    "token": "{login_key}",')
    else:
        snippet_lines.append('    # "token": "<paste token field name>",')
    rec = field_guesses.get("recipient")
    if rec:
        snippet_lines.append(f'    "recipient": "{rec}",')
    else:
        snippet_lines.append('    # "recipient": "<paste recipient field name>",')
    snippet_lines.append(f'    "amount": "{field_guesses.get("amount", "amount")}",')
    plat = field_guesses.get("platform")
    if plat:
        snippet_lines.append(f'    "platform": "{plat}",')
    else:
        snippet_lines.append('    # "platform": "<paste platform field name — or omit>",')
    snippet_lines.append('},')
    snippet_lines.append('# ─── END PASTE ──────────────────────────────────────────────────────')

    print("\n".join(snippet_lines))
    print()
    print("No credentials, tokens, or secrets were printed.")
    print("Paste the snippet above into backend/services/hub_registry.py.")


# ── Mode 1: HTTP-only login verification ─────────────────────────────────
async def http_only_login(hub_type: str, username: str, password: str):
    """Verify login via HTTP and detect the token field name."""
    import httpx

    hub = HUB_DEFAULTS.get(hub_type, HUB_DEFAULTS["sugar_sweeps"])
    api_base = hub.get("api_base_url", "").rstrip("/")
    if not api_base:
        print("ERROR: No api_base_url in hub config. Cannot do HTTP-only login.")
        return False

    user_field = hub.get("api_fields", {}).get("username", "email")
    pass_field = hub.get("api_fields", {}).get("password", "password")
    body = {user_field: username, pass_field: password}
    url = api_base + "/api/Auth/login"

    print(f"\nHTTP-only login: POST {url}")
    print(f"  body fields: {list(body.keys())}")
    print(f"  (credentials redacted)\n")

    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/131.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Origin": hub["base_url"].rstrip("/"),
                "Referer": hub["base_url"].rstrip("/") + "/",
            },
        ) as client:
            resp = await client.post(url, json=body)
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

    print(f"  status: {resp.status_code}")

    if resp.status_code >= 400:
        print(f"  body (redacted): {_redact(resp.text[:200])}")
        print(f"\n  Login failed. Check credentials and try again.")
        return False

    try:
        data = resp.json()
    except Exception:
        print(f"  response is not JSON: {_redact(resp.text[:200])}")
        return False

    print(f"  response keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
    token_field = _guess_token_field(data)
    print(f"  → token key: \"{token_field}\"")
    print()

    # Also check if any nested object has register-like fields.
    if isinstance(data, dict):
        for wrapper in ("data", "result", "payload"):
            nested = data.get(wrapper)
            if isinstance(nested, dict):
                print(f"  {wrapper} keys: {list(nested.keys())[:15]}")

    print(f"\n{'='*70}")
    print("COPY-PASTE for hub_registry.py api_fields.token:")
    print(f"{'='*70}")
    if "<not found" in token_field:
        print(f'    # "token": "{token_field}"')
        print(f"    # ↑ needs manual inspection of the response above")
    else:
        print(f'    "token": "{token_field}",')
    print()
    return True


# ── Mode 2/3: Playwright browser capture ─────────────────────────────────
def _capture_install(page) -> list:
    """Install request/response listeners on the page."""
    captured = []

    def on_request(request):
        url = request.url
        if not url.startswith("http"):
            return
        body = None
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = request.post_data
            except Exception:
                pass
        headers = dict(request.headers)
        captured.append({
            "kind": "request",
            "method": request.method,
            "url": url,
            "host": urlparse(url).netloc,
            "headers": headers,
            "body": body,
            "ts": time.time(),
        })

    async def on_response(response):
        url = response.url
        if not url.startswith("http"):
            return
        ctype = response.headers.get("content-type", "")
        body = None
        if "json" in ctype or "text" in ctype:
            try:
                body = await response.text()
            except Exception:
                pass
        captured.append({
            "kind": "response",
            "status": response.status,
            "url": url,
            "host": urlparse(url).netloc,
            "content_type": ctype,
            "body": body,
            "ts": time.time(),
        })

    page.on("request", on_request)
    page.on("response", on_response)
    return captured


async def _stealth_context(playwright, headed: bool = False):
    """Launch a stealth Chromium context."""
    browser = await playwright.chromium.launch(
        headless=not headed,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = await browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/Chicago",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {}, app: {} };
    """)
    return browser, context


def _classify_requests(captured: list, api_hosts: set,
                       recipient: str = "", amount: str = ""):
    """Categorize captured requests into login, transfer, register, other."""
    login_responses = []
    transfer_candidates = []
    register_candidates = []
    other_api_posts = []

    for entry in captured:
        if entry["kind"] == "response":
            url = urlparse(entry["url"])
            if url.netloc in api_hosts and "login" in url.path.lower():
                login_responses.append(entry)
        elif entry["kind"] == "request" and entry["method"] in ("POST", "PUT", "PATCH"):
            url = urlparse(entry["url"])
            if url.netloc not in api_hosts:
                continue
            low = url.path.lower()
            body = (entry.get("body") or "").lower()

            if "login" in low or "auth" in low:
                login_responses.append(entry)
            elif ("transfer" in low or "p2p" in low
                  or (recipient and recipient.lower() in body)
                  or (amount and amount in body)):
                transfer_candidates.append(entry)
            elif "register" in low or "signup" in low or "sign-up" in low:
                register_candidates.append(entry)
            else:
                other_api_posts.append(entry)

    return login_responses, transfer_candidates, register_candidates, other_api_posts


async def browser_capture(hub_type: str, username: str, password: str,
                          recipient: str = "", amount: int = 1,
                          headed: bool = False):
    """Open a browser, capture all API calls, and print findings."""
    from playwright.async_api import async_playwright

    hub = HUB_DEFAULTS.get(hub_type, HUB_DEFAULTS["sugar_sweeps"])
    base = hub["base_url"].rstrip("/")
    login_url = base + hub.get("login_path", "/")
    api_host = urlparse(hub.get("api_base_url", base)).netloc or urlparse(base).netloc
    api_hosts = {api_host, urlparse(base).netloc}

    print(f"\n{'='*70}")
    print(f"CAPTURING {hub['label']} ({base})")
    print(f"Mode: {'HEADED (drive by hand)' if headed else 'HEADLESS (auto-drive)'}")
    if recipient:
        print(f"Recipient: {recipient}  Amount: {amount}")
    print(f"{'='*70}\n")

    async with async_playwright() as pw:
        browser, context = await _stealth_context(pw, headed=headed)
        page = await context.new_page()
        captured = _capture_install(page)

        # Navigate.
        try:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"Navigation failed: {e}")
            await browser.close()
            return

        if headed:
            print("Browser opened. Log in and do the transfer by hand.")
            print("When done, close this terminal or press Ctrl+C.\n")
            try:
                # Keep capturing until the user closes the browser or Ctrl+C.
                while True:
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
        else:
            # Auto-drive login.
            sel = hub.get("selectors", {})
            pre_clicks = hub.get("pre_login_click", []) or []

            for pre in pre_clicks:
                try:
                    el = await page.query_selector(pre)
                    if el and await el.is_visible():
                        await el.click()
                        await asyncio.sleep(0.8)
                        break
                except Exception:
                    continue

            email_el = pw_el = sub_el = None
            for s in sel.get("email", []):
                el = await page.query_selector(s)
                if el and await el.is_visible():
                    email_el = el
                    break
            for s in sel.get("password", []):
                el = await page.query_selector(s)
                if el and await el.is_visible():
                    pw_el = el
                    break
            for s in sel.get("submit", []):
                el = await page.query_selector(s)
                if el and await el.is_visible():
                    sub_el = el
                    break

            if email_el and pw_el:
                user_field = hub.get("api_fields", {}).get("username", "email")
                pass_field = hub.get("api_fields", {}).get("password", "password")
                await email_el.fill(username)
                await pw_el.fill(password)
                await asyncio.sleep(0.5)
                if sub_el:
                    await sub_el.click()
                else:
                    await page.keyboard.press("Enter")
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(2)
                print("Login submitted.")
            else:
                print("Could not find login fields. Switching to manual mode.")
                print("Log in by hand in the browser.\n")
                headed = True
                try:
                    while True:
                        await asyncio.sleep(1)
                except (KeyboardInterrupt, asyncio.CancelledError):
                    pass

            # Auto-drive transfer (only if not headed).
            if not headed and recipient:
                nav_el = None
                for s in sel.get("transfer_nav", []):
                    el = await page.query_selector(s)
                    if el and await el.is_visible():
                        nav_el = el
                        break
                if nav_el:
                    await nav_el.click()
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    await asyncio.sleep(1)

                rec_el = amt_el = confirm_el = None
                for s in sel.get("recipient", []):
                    el = await page.query_selector(s)
                    if el and await el.is_visible():
                        rec_el = el
                        break
                for s in sel.get("amount", []):
                    el = await page.query_selector(s)
                    if el and await el.is_visible():
                        amt_el = el
                        break
                for s in sel.get("confirm", []):
                    el = await page.query_selector(s)
                    if el and await el.is_visible():
                        confirm_el = el
                        break

                if rec_el and amt_el:
                    await rec_el.fill(recipient)
                    await amt_el.fill(str(amount))
                    await asyncio.sleep(0.8)
                    if confirm_el:
                        await confirm_el.click()
                    else:
                        await page.keyboard.press("Enter")
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    await asyncio.sleep(2)
                    print("Transfer submitted.")
                else:
                    print("Transfer form not found. Drive it manually in the browser.")
                    try:
                        while True:
                            await asyncio.sleep(1)
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        pass

        await browser.close()

    # Classify and print results.
    login_resp, transfer_cands, register_cands, other_posts = \
        _classify_requests(captured, api_hosts, recipient, str(amount))

    _dump_capture(captured, api_hosts, login_resp, transfer_cands, register_cands)

    # Also dump all captured API calls to a JSON file for manual inspection.
    dump_path = Path(__file__).resolve().parent / "capture_dump.json"
    api_entries = [
        e for e in captured
        if urlparse(e.get("url", "")).netloc in api_hosts
    ]
    dump_path.write_text(json.dumps(api_entries, indent=2, default=str))
    print(f"\nFull capture ({len(api_entries)} API entries) saved to: {dump_path}")


# ── CLI entrypoint ───────────────────────────────────────────────────────
def main():
    hub_type = os.environ.get("HUB_TYPE", "sugar_sweeps")
    username = os.environ.get("HUB_USERNAME", "")
    password = os.environ.get("HUB_PASSWORD", "")
    recipient = os.environ.get("HUB_RECIPIENT", "")
    amount = int(os.environ.get("HUB_AMOUNT", "1"))

    http_only = "--http-only" in sys.argv
    headed = "--browse" in sys.argv or "--headed" in sys.argv
    show_help = "--help" in sys.argv or "-h" in sys.argv

    if show_help:
        print(__doc__)
        return

    if not username or not password:
        print("ERROR: Set HUB_USERNAME and HUB_PASSWORD environment variables.")
        print()
        print("  export HUB_USERNAME='your@email.com'")
        print("  export HUB_PASSWORD='yourpassword'")
        sys.exit(1)

    if http_only:
        asyncio.run(http_only_login(hub_type, username, password))
    else:
        if not recipient:
            print("ERROR: Set HUB_RECIPIENT to a test-platform account you control.")
            print()
            print("  export HUB_RECIPIENT='testplayer'")
            print("  export HUB_AMOUNT=1")
            sys.exit(2)
        asyncio.run(browser_capture(
            hub_type, username, password, recipient, amount, headed,
        ))


if __name__ == "__main__":
    main()
