"""Generic distributor hub bridge driven by HUB_CONFIGS.

One bridge class works for all hubs because each hub's differences live in
`services/hub_registry.HUB_CONFIGS` as plain data (selectors + paths).

This is the bridge used by the admin Ping + Test-Transfer endpoints. It
returns rich diagnostic info so selector mismatches can be debugged without
re-deploying code.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from services.hub_registry import get_hub

logger = logging.getLogger(__name__)


def make_bridge(hub_type: str, username: str, password: str, base_url: Optional[str] = None):
    """Return the appropriate bridge for a hub.

    Picks the HTTP fast-path (``HttpHubBridge``) when the hub config declares
    an ``api_base_url`` — this avoids Playwright entirely and bypasses Vercel
    WAF challenges that block datacenter IPs. Falls back to the Playwright-
    driven ``GenericHubBridge`` for hubs that only expose an HTML form.
    """
    hub = get_hub(hub_type)
    if hub.get("api_base_url"):
        from services.hub_http_bridge import HttpHubBridge

        return HttpHubBridge(hub_type, username, password, base_url=base_url)
    return GenericHubBridge(hub_type, username, password, base_url=base_url)


class GenericHubBridge:
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
        self.base_url = base_url or self.hub["base_url"]
        self.browser = None
        self.context = None
        self.page = None
        self.diagnostic: Dict[str, Any] = {
            "hub_type": hub_type,
            "base_url": self.base_url,
            "steps": [],
        }

    # --- lifecycle ---
    async def _launch(self):
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
            ],
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/Chicago",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Upgrade-Insecure-Requests": "1",
            },
        )
        # Comprehensive stealth: defeat Vercel/Cloudflare/Akamai bot fingerprinting.
        # Patches the most common navigator/window leaks that signal headless Chromium.
        await self.context.add_init_script(
            """
            // 1. Hide webdriver flag (the dead giveaway)
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            // 2. Real plugins array (headless has empty plugins by default)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
                    { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer' },
                ],
            });
            // 3. Languages must be non-empty
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            // 4. window.chrome must exist on Chrome UAs
            window.chrome = { runtime: {}, app: {}, csi: () => {}, loadTimes: () => {} };
            // 5. Permissions API quirk (headless returns 'denied' for notifications)
            const origQuery = window.navigator.permissions && window.navigator.permissions.query;
            if (origQuery) {
                window.navigator.permissions.query = (params) =>
                    params.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : origQuery(params);
            }
            // 6. WebGL vendor/renderer (headless leaks 'Google Inc.'/'Google SwiftShader')
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function (parameter) {
                if (parameter === 37445) return 'Intel Inc.';           // UNMASKED_VENDOR_WEBGL
                if (parameter === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
                return getParameter.call(this, parameter);
            };
            // 7. Hardware concurrency must look real
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            // 8. deviceMemory must look real
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            """
        )
        self.page = await self.context.new_page()

    async def _find_login_page(self, login_url: str) -> str:
        """Ensure we end up on a page that actually has a login form.

        Tries: configured login path → common alternates → homepage + click a
        "Login" link. Returns the URL we settled on.
        """
        sel = self.hub["selectors"]
        # Hard cap on total time spent finding the login page to avoid runaway loops
        # when sites are behind a CDN that never clears (e.g. Vercel datacenter IP block).
        import time
        deadline_at = time.monotonic() + 45  # 45 seconds total budget
        challenge_seen = False

        async def has_form() -> bool:
            for s in sel["email"]:
                try:
                    el = await self.page.query_selector(s)
                    if el and await el.is_visible():
                        return True
                except Exception:
                    pass
            return False

        async def wait_through_challenge(max_wait_ms: int = 8000):
            nonlocal challenge_seen
            try:
                title = (await self.page.title() or "").lower()
            except Exception:
                title = ""
            challenge_keywords = ("checkpoint", "security check", "challenge", "just a moment", "cloudflare", "captcha", "vercel security")
            if not any(k in title for k in challenge_keywords):
                return
            challenge_seen = True
            self._step("bot_challenge_detected", title=title)
            try:
                deadline = max_wait_ms
                while deadline > 0:
                    await self.page.wait_for_timeout(1000)
                    deadline -= 1000
                    new_title = (await self.page.title() or "").lower()
                    if not any(k in new_title for k in challenge_keywords):
                        self._step("bot_challenge_cleared", title=new_title, waited_ms=max_wait_ms - deadline)
                        return
            except Exception:
                pass
            self._step("bot_challenge_timeout", waited_ms=max_wait_ms)

        try:
            await self.page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
            await wait_through_challenge()
        except Exception:
            pass
        if await has_form():
            return self.page.url

        # If we hit a CDN bot challenge once, ALL paths on this domain are gated by
        # the same WAF — bail out fast instead of grinding through fallbacks.
        if challenge_seen:
            self._step("abort_alternates", reason="cdn_waf_blocks_all_paths")
            return self.page.url

        # Try common alternates
        alternates = ["/login", "/signin", "/sign-in", "/account/login", "/user/sign-in", "/auth/login"]
        for alt in alternates:
            if time.monotonic() > deadline_at:
                self._step("abort_alternates", reason="time_budget_exceeded")
                break
            try:
                cand = self.base_url.rstrip("/") + alt
                if cand == login_url:
                    continue
                await self.page.goto(cand, wait_until="domcontentloaded", timeout=10000)
                await wait_through_challenge()
                if challenge_seen:
                    break
                if await has_form():
                    self._step("login_path_fallback", matched=alt)
                    return self.page.url
            except Exception:
                continue

        # Last resort: homepage, then click a "Login/Sign in" link
        if time.monotonic() < deadline_at and not challenge_seen:
            try:
                await self.page.goto(self.base_url, wait_until="domcontentloaded", timeout=10000)
                await wait_through_challenge()
                if not challenge_seen:
                    for link_sel in [
                        'a:has-text("Login")', 'a:has-text("Log in")', 'a:has-text("Sign in")',
                        'a:has-text("Sign In")', 'button:has-text("Login")', 'button:has-text("Sign in")',
                    ]:
                        try:
                            el = await self.page.query_selector(link_sel)
                            if el and await el.is_visible():
                                await el.click()
                                try:
                                    await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                                except Exception:
                                    pass
                                if await has_form():
                                    self._step("login_path_via_link", matched=link_sel)
                                    return self.page.url
                        except Exception:
                            continue
            except Exception:
                pass
        return self.page.url if self.page else login_url

    async def close(self):
        try:
            if self.browser:
                await self.browser.close()
        finally:
            try:
                await self._pw.stop()
            except Exception:
                pass

    # --- helpers ---
    async def _first_match(self, selectors: List[str]):
        for sel in selectors:
            try:
                el = await self.page.query_selector(sel)
                if el:
                    visible = await el.is_visible()
                    if visible:
                        return sel, el
            except Exception:
                continue
        return None, None

    def _step(self, name: str, **data):
        self.diagnostic["steps"].append({"step": name, **data})

    # --- ping (login probe) ---
    async def ping(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Try to log in. Return (ok, message, diagnostic).

        Diagnostic always filled with what was found at each step so admin
        can refine HUB_CONFIGS selectors.
        """
        try:
            await self._launch()
        except Exception as e:
            return False, f"Browser launch failed: {e}", self.diagnostic

        login_url = self.base_url.rstrip("/") + self.hub.get("login_path", "/login")
        sel = self.hub["selectors"]

        try:
            final_login_url = await self._find_login_page(login_url)
        except Exception as e:
            self._step("goto", url=login_url, error=str(e))
            return False, f"Navigation failed: {e}", self.diagnostic
        self._step(
            "goto",
            url=login_url,
            final_url=final_login_url,
            title=await self.page.title() if self.page else "",
        )

        await asyncio.sleep(random.uniform(0.8, 1.6))

        # Some hubs (e.g. Sugar Sweeps) show Register form by default; we need
        # to click a tab/button to reveal the login form first.
        for pre_sel in self.hub.get("pre_login_click", []) or []:
            try:
                el = await self.page.query_selector(pre_sel)
                if el and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(0.6)
                    self._step("pre_login_click", matched=pre_sel)
                    break
            except Exception as e:
                self._step("pre_login_click_error", selector=pre_sel, error=str(e))

        email_sel, email_el = await self._first_match(sel["email"])
        self._step("find_email", matched=email_sel)
        password_sel, password_el = await self._first_match(sel["password"])
        self._step("find_password", matched=password_sel)
        submit_sel, submit_el = await self._first_match(sel["submit"])
        self._step("find_submit", matched=submit_sel)

        if not email_el:
            return False, "Email field not found — selectors need updating", self.diagnostic
        if not password_el:
            return False, "Password field not found — selectors need updating", self.diagnostic

        try:
            await email_el.fill(self.username)
            await password_el.fill(self.password)
            self._step("fill", email_len=len(self.username), pw_len=len(self.password))
        except Exception as e:
            return False, f"Could not fill credentials: {e}", self.diagnostic

        try:
            if submit_el:
                await submit_el.click()
            else:
                await self.page.keyboard.press("Enter")
            self._step("submit", via="click" if submit_el else "enter")
        except Exception as e:
            return False, f"Submit failed: {e}", self.diagnostic

        try:
            await self.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        final_url = self.page.url
        self._step("post_submit", final_url=final_url, title=await self.page.title())

        login_ok = "login" not in final_url.lower() and "signin" not in final_url.lower()
        if login_ok:
            return True, f"Login OK — landed on {final_url}", self.diagnostic
        # Look for an error message on the page
        err_text = ""
        try:
            body_text = await self.page.inner_text("body")
            # Find a short snippet
            for line in body_text.splitlines():
                low = line.lower()
                if any(k in low for k in ("invalid", "incorrect", "wrong", "error", "failed")):
                    err_text = line.strip()[:180]
                    break
        except Exception:
            pass
        return False, f"Login submitted but still on {final_url}" + (f" ({err_text})" if err_text else ""), self.diagnostic

    # --- transfer ---
    async def transfer(
        self, recipient: str, amount: float, platform: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        ok, msg, _ = await self.ping()
        if not ok:
            return False, msg, self.diagnostic

        sel = self.hub["selectors"]
        # Navigate to dashboard / transfer page
        try:
            nav_sel, nav_el = await self._first_match(sel.get("transfer_nav", []))
            if nav_el:
                await nav_el.click()
                await self.page.wait_for_load_state("networkidle", timeout=10000)
                self._step("transfer_nav", matched=nav_sel, final_url=self.page.url)
        except Exception as e:
            self._step("transfer_nav", error=str(e))

        await asyncio.sleep(random.uniform(0.5, 1.2))

        recipient_sel, recipient_el = await self._first_match(sel.get("recipient", []))
        amount_sel, amount_el = await self._first_match(sel.get("amount", []))
        confirm_sel, confirm_el = await self._first_match(sel.get("confirm", []))
        self._step(
            "transfer_form",
            recipient_sel=recipient_sel,
            amount_sel=amount_sel,
            confirm_sel=confirm_sel,
        )
        if not recipient_el or not amount_el:
            return False, "Transfer form fields not found — check selectors", self.diagnostic

        try:
            await recipient_el.fill(recipient)
            await amount_el.fill(str(int(amount)))
            if confirm_el:
                await confirm_el.click()
            else:
                await self.page.keyboard.press("Enter")
            await self.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            return False, f"Transfer submit failed: {e}", self.diagnostic

        final_url = self.page.url
        self._step("transfer_submit", final_url=final_url)
        # Heuristic success detection
        try:
            body_text = (await self.page.inner_text("body")).lower()
        except Exception:
            body_text = ""
        if any(k in body_text for k in ("success", "transferred", "sent", "completed")):
            return True, f"Transfer confirmed on {final_url}", self.diagnostic
        return False, f"Submitted but no success indicator found ({final_url})", self.diagnostic
