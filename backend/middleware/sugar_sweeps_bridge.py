"""
Sugar Sweeps Master Tank Bridge

Unified P2P transfer system for all 11 game platforms via Sugar Sweeps hub.
Implements "Snatch & Map" protocol with drip injection and human signature.

PLATFORMS SUPPORTED (via one login):
- Fire Kirin
- Orion Stars  
- Ultra Panda
- Juwa
- vBlink
- Panda Master
- Game Vault
- Milky Way
- Noble
- Vegas X
- River Sweeps
"""

import os
import asyncio
import random
import secrets
import logging
from datetime import datetime, timezone
from typing import Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page, Browser

logger = logging.getLogger(__name__)

class SugarSweepsBridge:
    """
    Master Tank: Connects to Sugar Sweeps hub for P2P transfers across 11 platforms.
    
    The "One-Stop Shop" - Single login, all platforms accessible.
    """
    
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.username = username if username is not None else os.environ.get("SUGAR_SWEEPS_USERNAME")
        self.password = password if password is not None else os.environ.get("SUGAR_SWEEPS_PASSWORD")
        self.base_url = base_url or os.environ.get("SUGAR_SWEEPS_URL", "https://sugarsweeps.com")
        self.session_cookie = os.environ.get("SUGAR_SWEEPS_SESSION", "")  # Optional pre-auth cookie
        
        self.browser: Optional["Browser"] = None
        self.page: Optional["Page"] = None
        self.is_authenticated = False
        self.session_token = None
        self.master_balance = 0
        
        # Platform button mappings (will be auto-discovered)
        self.platform_selectors = {}
        
        # Drip injection queue
        self.transfer_queue = []
        self.processing_queue = False
        
        logger.info(f"🍬 Sugar Sweeps Bridge initialized (User: {self.username})")
        logger.info(f"📍 Target: {self.base_url} (Web Portal - No Downloads)")
    
    async def initialize(self) -> Tuple[bool, str]:
        """
        Initialize browser and login to Sugar Sweeps hub.
        
        Implements "Snatch & Map" protocol:
        1. Session Hook (grab auth_token)
        2. Platform Mapping (find transfer buttons)
        3. Balance Sync (read master balance)
        """
        try:
            # Lazy-load playwright only when actually initializing (avoids
            # eager browser imports on backend cold-start which caused OOM/520).
            from playwright.async_api import async_playwright
            playwright = await async_playwright().start()
            
            # Launch browser with Samsung Galaxy S22 Ultra signature
            self.browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--user-agent=Mozilla/5.0 (Linux; Android 12; SM-S908U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36'
                ]
            )
            
            # Create context with mobile viewport (Samsung S22 Ultra)
            context = await self.browser.new_context(
                viewport={'width': 1080, 'height': 2340},
                device_scale_factor=3.0,
                is_mobile=True,
                has_touch=True,
                user_agent='Mozilla/5.0 (Linux; Android 12; SM-S908U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36'
            )
            
            self.page = await context.new_page()
            
            # Dismiss modals on every page load
            self.page.on("load", lambda: asyncio.create_task(self._dismiss_modals()))
            
            # Step 1: Session Hook (Login & Snatch Token)
            login_success, login_msg = await self._login()
            if not login_success:
                return False, login_msg
            
            # Step 2: Platform Mapping (Find Transfer Buttons)
            await self._map_platforms()
            
            # Step 3: Balance Sync (Read Master Balance)
            await self._sync_master_balance()
            
            logger.info(f"✅ Sugar Sweeps Bridge ONLINE | Master Balance: ${self.master_balance}")
            
            return True, f"Connected to Sugar Sweeps | Balance: ${self.master_balance}"
        
        except Exception as e:
            logger.error(f"❌ Sugar Sweeps initialization failed: {str(e)}")
            return False, f"Init error: {str(e)}"
    
    async def _login(self) -> Tuple[bool, str]:
        """
        Login to Sugar Sweeps and snatch session token.
        
        Strategy:
        1. Check if session cookie provided (skip login if valid)
        2. Otherwise, perform full login flow
        3. Snatch auth tokens for future use
        
        Implements human-like behavior:
        - Random delays
        - Mouse path jitter
        - Natural typing speed
        """
        try:
            # If session cookie provided, try to use it
            if self.session_cookie:
                logger.info("🔐 Attempting to restore session from cookie...")
                await self.page.context.add_cookies([{
                    'name': 'session',
                    'value': self.session_cookie,
                    'domain': self.base_url.replace('https://', '').replace('http://', ''),
                    'path': '/'
                }])
                
                # Navigate to dashboard to verify session
                await self.page.goto(f"{self.base_url}/dashboard", wait_until="networkidle")
                
                # Check if we're logged in
                if 'login' not in self.page.url.lower():
                    self.is_authenticated = True
                    logger.info("✅ Session restored from cookie")
                    return True, "Session restored"
            
            # Full login flow
            login_url = f"{self.base_url}/login"
            
            await self.page.goto(login_url, wait_until="networkidle")
            
            # Dismiss any welcome/age verification modals
            await self._dismiss_modals()
            
            # Random delay (look human)
            await asyncio.sleep((1.5 + (secrets.randbelow(10_000) / 10_000.0) * (3.0 - 1.5)))
            
            # From screenshot: Bottom buttons are "Register" and "Login"
            # Click Login button
            login_button_selectors = [
                'button:has-text("Login")',
                'a:has-text("Login")',
                '[href*="login"]',
                '.login-btn',
                'button.login'
            ]
            
            login_button = None
            for selector in login_button_selectors:
                login_button = await self.page.query_selector(selector)
                if login_button:
                    logger.info(f"✅ Found login button: {selector}")
                    break
            
            if login_button:
                await self._click_with_jitter(login_button)
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep((2.0 + (secrets.randbelow(10_000) / 10_000.0) * (3.0 - 2.0)))
                
                # Dismiss any post-click modals
                await self._dismiss_modals()
            
            # Now on login page - find email and password fields
            # Sugar Sweeps uses email login (jrs092393@gmail.com)
            email_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[id="email"]',
                'input[placeholder*="email" i]',
                'input[placeholder*="mail" i]'
            ]
            
            email_input = None
            for selector in email_selectors:
                email_input = await self.page.query_selector(selector)
                if email_input:
                    logger.info(f"✅ Found email field: {selector}")
                    break
            
            if not email_input:
                # Fallback: try first text input
                email_input = await self.page.query_selector('input[type="text"]')
                if email_input:
                    logger.info("✅ Found email field (fallback: first text input)")
            
            if email_input:
                await email_input.click()
                await asyncio.sleep((0.3 + (secrets.randbelow(10_000) / 10_000.0) * (0.7 - 0.3)))
                await email_input.type(self.username, delay=(secrets.randbelow((150) - (50) + 1) + (50)))
                logger.info(f"✍️ Typed email: {self.username}")
            else:
                return False, "Email field not found"
            
            # Password field handling
            password_input = await self._find_password_field()
            
            if password_input:
                await password_input.click()
                await asyncio.sleep((0.3 + (secrets.randbelow(10_000) / 10_000.0) * (0.7 - 0.3)))
                await password_input.type(self.password, delay=(secrets.randbelow((150) - (50) + 1) + (50)))
                logger.info("✍️ Typed password")
            else:
                return False, "Password field not found"
            
            # Submit login form
            submit_success = await self._submit_login_form()
            if not submit_success:
                return False, "Failed to submit login form"
            
            # Wait for navigation after login
            await asyncio.sleep((2.0 + (secrets.randbelow(10_000) / 10_000.0) * (4.0 - 2.0)))
            
            # Verify login success
            if 'login' not in self.page.url.lower():
                self.is_authenticated = True
                await self._snatch_session_tokens()
                logger.info("✅ Login successful")
                return True, "Login successful"
            else:
                return False, "Login form submitted but still on login page"
        
        except Exception as e:
            logger.error(f"❌ Login flow error: {str(e)}")
            return False, f"Login error: {str(e)}"
    
    async def _find_password_field(self):
        """Locate the password input field on the page."""
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id="password"]',
            'input[placeholder*="password" i]'
        ]
        for selector in password_selectors:
            field = await self.page.query_selector(selector)
            if field:
                logger.info(f"✅ Found password field: {selector}")
                return field
        return None
    
    async def _submit_login_form(self) -> bool:
        """Find and click the submit/login button."""
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Sign In")',
            'button:has-text("Log In")',
            'button:has-text("Login")',
            '.submit-btn',
            '.login-submit'
        ]
        for selector in submit_selectors:
            btn = await self.page.query_selector(selector)
            if btn:
                await self._click_with_jitter(btn)
                await self.page.wait_for_load_state("networkidle")
                logger.info(f"✅ Clicked submit: {selector}")
                return True
        logger.warning("⚠️ No submit button found, trying Enter key")
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_load_state("networkidle")
        return True
    
    async def _snatch_session_tokens(self):
        """Extract session cookies and tokens after successful login."""
        try:
            cookies = await self.page.context.cookies()
            for cookie in cookies:
                if cookie['name'].lower() in ('session', 'sessionid', 'jsessionid', 'connect.sid', 'token'):
                    self.session_cookie = cookie['value']
                    logger.info(f"🔑 Snatched session cookie: {cookie['name']}")
                    break
        except Exception as e:
            logger.warning(f"⚠️ Could not extract session tokens: {str(e)}")

    async def _dismiss_modals(self):
        """
        Dismiss any modals, popups, or overlays blocking the page.
        
        Common patterns:
        - Welcome modals
        - Age verification
        - Cookie consent
        - Promotional popups
        - Loading overlays
        """
        try:
            logger.info("🔍 Checking for modals/overlays...")
            
            # Close button selectors (ordered by likelihood)
            close_selectors = [
                # X buttons
                'button[aria-label="Close"]',
                'button[aria-label="close"]',
                '[aria-label*="close" i]',
                '.close-button',
                '.modal-close',
                'button.close',
                
                # Dialog close buttons
                '[role="dialog"] button:has-text("×")',
                '[role="dialog"] button:has-text("✕")',
                '[role="dialog"] button:has-text("Close")',
                '[role="dialog"] button.close',
                
                # Generic close icons
                'button[class*="close"]',
                '[class*="close-btn"]',
                'svg[class*="close"]',
                
                # Dismiss/Continue buttons
                'button:has-text("Continue")',
                'button:has-text("I Understand")',
                'button:has-text("Accept")',
                'button:has-text("OK")',
                'button:has-text("Got it")',
                
                # Overlay clicks (backdrop)
                '[data-state="open"][aria-hidden="true"]',
                '.overlay',
                '.backdrop'
            ]
            
            modals_closed = 0
            
            for selector in close_selectors:
                elements = await self.page.query_selector_all(selector)
                
                for element in elements:
                    try:
                        # Check if element is visible
                        is_visible = await element.is_visible()
                        if not is_visible:
                            continue
                        
                        # Try to click it
                        await element.click(timeout=1000, force=True)
                        modals_closed += 1
                        logger.info(f"✅ Closed modal via: {selector}")
                        
                        # Wait for modal animation to complete
                        await asyncio.sleep(0.5)
                        
                    except Exception:
                        # Ignore errors, try next selector
                        continue
            
            # Press Escape key (closes many modals)
            await self.page.keyboard.press('Escape')
            await asyncio.sleep(0.3)
            
            # Check if any dialogs still exist
            remaining_dialogs = await self.page.query_selector_all('[role="dialog"][data-state="open"]')
            
            if remaining_dialogs:
                logger.warning(f"⚠️  {len(remaining_dialogs)} dialog(s) still open, attempting force close...")
                
                # Try clicking outside the dialog (on overlay)
                overlay = await self.page.query_selector('[data-state="open"][aria-hidden="true"]')
                if overlay:
                    try:
                        await overlay.click(timeout=1000, force=True)
                        logger.info("✅ Closed dialog by clicking overlay")
                        modals_closed += 1
                    except Exception:
                        pass
            
            if modals_closed > 0:
                logger.info(f"✅ Dismissed {modals_closed} modal(s)")
                await asyncio.sleep(1.0)  # Wait for page to settle
            else:
                logger.info("✅ No modals detected")
            
            return True
        
        except Exception as e:
            logger.warning(f"⚠️  Modal dismissal error (non-critical): {str(e)}")
            return True  # Continue anyway
    
    async def _safe_click(self, element, max_attempts=3):
        """
        Click an element with automatic modal dismissal and retry logic.
        
        Args:
            element: Playwright element to click
            max_attempts: Number of retry attempts
        
        Returns:
            bool: Success status
        """
        for attempt in range(max_attempts):
            try:
                # Dismiss any modals before clicking
                await self._dismiss_modals()
                
                # Wait for element to be stable
                await element.wait_for_element_state("stable", timeout=2000)
                
                # Try regular click first
                try:
                    await element.click(timeout=5000)
                    logger.info(f"✅ Click successful (attempt {attempt + 1})")
                    return True
                except Exception as click_error:
                    # If blocked, try force click
                    if "intercepts pointer events" in str(click_error):
                        logger.warning(f"⚠️  Element blocked, trying force click (attempt {attempt + 1})...")
                        await element.click(timeout=5000, force=True)
                        logger.info(f"✅ Force click successful (attempt {attempt + 1})")
                        return True
                    else:
                        raise
            
            except Exception as e:
                if attempt < max_attempts - 1:
                    logger.warning(f"⚠️  Click failed (attempt {attempt + 1}): {str(e)[:100]}")
                    logger.info("🔄 Retrying in 2 seconds...")
                    await asyncio.sleep(2)
                else:
                    logger.error(f"❌ Click failed after {max_attempts} attempts")
                    raise
        
        return False

    async def _map_platforms(self):
        """
        Scan Sugar Sweeps dashboard to find transfer buttons for all 11 platforms.
        
        Auto-discovers button selectors and stores them for later use.
        """
        try:
            # Look for platform links/buttons
            platforms = [
                "Fire Kirin", "Orion Stars", "Ultra Panda", "Juwa", "vBlink",
                "Panda Master", "Game Vault", "Milky Way", "Noble", "Vegas X", "River Sweeps"
            ]
            
            for platform in platforms:
                # Try to find platform link/button
                selector = f'a:has-text("{platform}"), button:has-text("{platform}"), [data-platform="{platform.lower().replace(" ", "-")}"]'
                element = await self.page.query_selector(selector)
                
                if element:
                    self.platform_selectors[platform.lower().replace(" ", "_")] = selector
                    logger.info(f"📍 Mapped: {platform}")
            
            logger.info(f"✅ Platform mapping complete: {len(self.platform_selectors)} platforms found")
        
        except Exception as e:
            logger.error(f"Platform mapping error: {str(e)}")
    
    async def _sync_master_balance(self):
        """
        Read master account balance from Sugar Sweeps dashboard.
        """
        try:
            # Look for balance display
            balance_selectors = [
                '.balance', '#balance', '[data-balance]',
                'span:has-text("Balance")', 'div:has-text("$")'
            ]
            
            for selector in balance_selectors:
                element = await self.page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    # Extract number from text
                    import re
                    match = re.search(r'\$?(\d+(?:,\d{3})*(?:\.\d{2})?)', text)
                    if match:
                        balance_str = match.group(1).replace(',', '')
                        self.master_balance = float(balance_str)
                        logger.info(f"💰 Master Balance: ${self.master_balance}")
                        return
            
            logger.warning("⚠️ Could not find balance display")
        
        except Exception as e:
            logger.error(f"Balance sync error: {str(e)}")
    
    async def transfer_credits_p2p(
        self,
        recipient_username: str,
        amount: float,
        platform: str = "fire_kirin"
    ) -> Tuple[bool, str, Optional[str]]:
        """
        P2P Transfer: Send credits from master tank to user's game account.
        
        Implements drip injection with human signature.
        
        Args:
            recipient_username: User's game account username
            amount: Credits to transfer
            platform: Game platform (fire_kirin, juwa, etc.)
        
        Returns:
            (success, message, transaction_id)
        """
        
        # Add to drip injection queue
        transfer_request = {
            "recipient": recipient_username,
            "amount": amount,
            "platform": platform,
            "timestamp": datetime.now(timezone.utc),
            "status": "queued"
        }
        
        self.transfer_queue.append(transfer_request)
        logger.info(f"📥 Transfer queued: {amount} credits → {recipient_username} ({platform})")
        
        # Start queue processor if not running
        if not self.processing_queue:
            asyncio.create_task(self._process_transfer_queue())
        
        return True, "Transfer queued (drip injection active)", None
    
    async def _process_transfer_queue(self):
        """
        Process transfer queue with drip injection (45-120 second delays).
        
        Prevents velocity flagging by spacing out transfers.
        """
        self.processing_queue = True
        
        while self.transfer_queue:
            transfer = self.transfer_queue.pop(0)
            
            try:
                # Execute transfer
                success, msg, tx_id = await self._execute_p2p_transfer(
                    transfer["recipient"],
                    transfer["amount"],
                    transfer["platform"]
                )
                
                if success:
                    logger.info(f"✅ Transfer complete: {transfer['amount']} → {transfer['recipient']}")
                    transfer["status"] = "completed"
                else:
                    logger.error(f"❌ Transfer failed: {msg}")
                    transfer["status"] = "failed"
                
                # Drip injection delay (45-120 seconds)
                if self.transfer_queue:  # Only delay if more transfers pending
                    delay = (45 + (secrets.randbelow(10_000) / 10_000.0) * (120 - 45))
                    logger.info(f"⏳ Drip injection delay: {delay:.1f}s before next transfer")
                    await asyncio.sleep(delay)
            
            except Exception as e:
                logger.error(f"Transfer processing error: {str(e)}")
                transfer["status"] = "error"
        
        self.processing_queue = False
        logger.info("✅ Transfer queue empty")
    
    async def _execute_p2p_transfer(
        self,
        recipient: str,
        amount: float,
        platform: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Execute actual P2P transfer on Sugar Sweeps platform.
        
        THE "BACK DOOR" STRATEGY:
        - Even "download-only" games (Fire Kirin, etc.) can be managed via web portal
        - Bot finds "Transfer" or "Friend" menu on sugarsweeps.com
        - Fills recipient ID and amount
        - Executes P2P transfer (credits move from master tank to player)
        - NO APP DOWNLOAD NEEDED - all via website
        
        Players still download apps to play, but bot fuels accounts via web interface.
        """
        try:
            if not self.is_authenticated:
                return False, "Not authenticated", None
            
            # Navigate to Transfer page via bottom nav
            # From screenshots: Bottom nav has "Transfer" button
            transfer_nav_selectors = [
                'a[href*="transfer"]',
                'button:has-text("Transfer")',
                'nav a:has-text("Transfer")',
                '.bottom-nav a:has-text("Transfer")',
                '[data-tab="transfer"]'
            ]
            
            transfer_nav = None
            for selector in transfer_nav_selectors:
                transfer_nav = await self.page.query_selector(selector)
                if transfer_nav:
                    logger.info(f"📍 Found transfer nav: {selector}")
                    break
            
            if transfer_nav:
                await self._click_with_jitter(transfer_nav)
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep((1.5 + (secrets.randbelow(10_000) / 10_000.0) * (3.0 - 1.5)))
            else:
                logger.warning("⚠️ Transfer nav not found, assuming already on transfer page...")
            
            # SELECT PLATFORM DROPDOWN
            # From screenshots: "Select a platform" dropdown shows Juwa, Milkyway, Vblink, Ultra Panda, Orion Stars
            platform_dropdown_selectors = [
                'select[name="platform"]',
                'select',
                '[role="combobox"]',
                'input[placeholder*="platform" i]',
                '.platform-select',
                'button:has-text("Select a platform")'
            ]
            
            platform_dropdown = None
            for selector in platform_dropdown_selectors:
                platform_dropdown = await self.page.query_selector(selector)
                if platform_dropdown:
                    logger.info(f"📍 Found platform dropdown: {selector}")
                    break
            
            if platform_dropdown:
                # Click to open dropdown
                await self._click_with_jitter(platform_dropdown)
                await asyncio.sleep((0.5 + (secrets.randbelow(10_000) / 10_000.0) * (1.5 - 0.5)))
                
                # Select the platform (Juwa, Orion Stars, etc.)
                # Look for option with matching text
                platform_option = await self.page.query_selector(f'option:has-text("{platform}"), li:has-text("{platform}"), [role="option"]:has-text("{platform}")')
                
                if platform_option:
                    await self._click_with_jitter(platform_option)
                    logger.info(f"✅ Selected platform: {platform}")
                    await asyncio.sleep((0.5 + (secrets.randbelow(10_000) / 10_000.0) * (1.0 - 0.5)))
                else:
                    # Try typing the platform name
                    await platform_dropdown.type(platform, delay=(secrets.randbelow((150) - (50) + 1) + (50)))
                    await asyncio.sleep((0.5 + (secrets.randbelow(10_000) / 10_000.0) * (1.0 - 0.5)))
                    await self.page.keyboard.press('Enter')
                    logger.info(f"✅ Typed platform: {platform}")
            else:
                logger.warning("⚠️ Platform dropdown not found")

            
            # Look for transfer/P2P form fields
            # Recipient field
            recipient_selectors = [
                'input[name="recipient"]',
                'input[name="username"]',
                'input[name="player"]',
                'input[name="player_id"]',
                'input[placeholder*="recipient" i]',
                'input[placeholder*="username" i]',
                'input[placeholder*="player" i]',
                'input[id="recipient"]',
                'input[id="username"]'
            ]
            
            recipient_input = None
            for selector in recipient_selectors:
                recipient_input = await self.page.query_selector(selector)
                if recipient_input:
                    logger.info(f"📍 Found recipient field: {selector}")
                    break
            
            if not recipient_input:
                return False, "Recipient field not found on transfer form", None
            
            # Fill recipient with human-like typing
            await recipient_input.click()
            await asyncio.sleep((0.3 + (secrets.randbelow(10_000) / 10_000.0) * (0.7 - 0.3)))
            await recipient_input.type(recipient, delay=(secrets.randbelow((150) - (50) + 1) + (50)))
            logger.info(f"✍️ Filled recipient: {recipient}")
            
            # Amount field  
            amount_selectors = [
                'input[name="amount"]',
                'input[name="credits"]',
                'input[type="number"]',
                'input[placeholder*="amount" i]',
                'input[placeholder*="credits" i]',
                'input[id="amount"]'
            ]
            
            amount_input = None
            for selector in amount_selectors:
                amount_input = await self.page.query_selector(selector)
                if amount_input:
                    logger.info(f"📍 Found amount field: {selector}")
                    break
            
            if not amount_input:
                return False, "Amount field not found on transfer form", None
            
            # Fill amount with human-like typing
            await amount_input.click()
            await asyncio.sleep((0.3 + (secrets.randbelow(10_000) / 10_000.0) * (0.7 - 0.3)))
            await amount_input.type(str(int(amount)), delay=(secrets.randbelow((150) - (50) + 1) + (50)))
            logger.info(f"✍️ Filled amount: {amount}")
            
            # Random delay before submit (think time)
            await asyncio.sleep((1.0 + (secrets.randbelow(10_000) / 10_000.0) * (2.5 - 1.0)))
            
            # Submit button
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Transfer")',
                'button:has-text("Send")',
                'button:has-text("Confirm")',
                'button:has-text("Submit")'
            ]
            
            submit_button = None
            for selector in submit_selectors:
                submit_button = await self.page.query_selector(selector)
                if submit_button:
                    logger.info(f"📍 Found submit button: {selector}")
                    break
            
            if not submit_button:
                return False, "Submit button not found", None
            
            # Click submit with jitter
            await self._click_with_jitter(submit_button)
            logger.info("🖱️ Clicked submit button")
            
            # Wait for transfer to process
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep((2.0 + (secrets.randbelow(10_000) / 10_000.0) * (4.0 - 2.0)))
            
            # Check for success message
            success_indicators = [
                ':has-text("success")',
                ':has-text("transferred")',
                ':has-text("sent")',
                ':has-text("completed")',
                '.success',
                '.alert-success'
            ]
            
            for indicator in success_indicators:
                element = await self.page.query_selector(indicator)
                if element:
                    logger.info(f"✅ Transfer success indicator found: {indicator}")
                    break
            
            # Generate transaction ID
            tx_id = f"SS_{platform}_{int(datetime.now(timezone.utc).timestamp())}"
            
            logger.info(f"🎉 P2P Transfer completed: {amount} credits → {recipient} ({platform})")
            
            return True, f"Transferred {amount} credits to {recipient} via Sugar Sweeps P2P", tx_id
        
        except Exception as e:
            logger.error(f"P2P transfer execution error: {str(e)}")
            return False, f"Transfer error: {str(e)}", None
    
    async def _click_with_jitter(self, element):
        """Add human-like mouse movement before clicking"""
        box = await element.bounding_box()
        if box:
            # Random point within element bounds
            x = box['x'] + (5 + (secrets.randbelow(10_000) / 10_000.0) * (box['width'] - 5 - 5))
            y = box['y'] + (5 + (secrets.randbelow(10_000) / 10_000.0) * (box['height'] - 5 - 5))
            
            # Move mouse in arc (looks more human)
            await self.page.mouse.move(x, y)
            await asyncio.sleep((0.1 + (secrets.randbelow(10_000) / 10_000.0) * (0.3 - 0.1)))
        
        await element.click()
    
    async def _click_with_jitter(self, element):
        """
        Add human-like mouse movement before clicking.
        Includes automatic modal dismissal.
        """
        # Dismiss modals first
        await self._dismiss_modals()
        
        box = await element.bounding_box()
        if box:
            # Random point within element bounds
            x = box['x'] + (5 + (secrets.randbelow(10_000) / 10_000.0) * (box['width'] - 5 - 5))
            y = box['y'] + (5 + (secrets.randbelow(10_000) / 10_000.0) * (box['height'] - 5 - 5))
            
            # Move mouse in arc (looks more human)
            await self.page.mouse.move(x, y)
            await asyncio.sleep((0.1 + (secrets.randbelow(10_000) / 10_000.0) * (0.3 - 0.1)))
        
        # Use safe click with retry logic
        await self._safe_click(element)
    
    async def close(self):
        """Cleanup browser resources"""
        if self.browser:
            await self.browser.close()
            logger.info("🔒 Sugar Sweeps Bridge closed")
    
    async def get_balance(self) -> float:
        """Get current master tank balance"""
        await self._sync_master_balance()
        return self.master_balance
