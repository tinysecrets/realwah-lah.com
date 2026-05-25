import os
import logging
from typing import Optional, Dict, Any, Tuple
from playwright.async_api import async_playwright, Browser, Page
from .session_manager import SessionManager

logger = logging.getLogger(__name__)

class BackendBridge:
    """
    Automates interactions with game platform agent panels.
    Primary: Uses API via SessionManager
    Fallback: Uses Playwright headless browser for platforms without API
    """
    
    def __init__(self, platform_config: Dict[str, Any]):
        self.platform_id = platform_config["id"]
        self.platform_name = platform_config["name"]
        self.config = platform_config
        self.use_headless = platform_config.get("use_headless", False)
        
        # API-based session manager
        self.session_manager = SessionManager(platform_config)
        
        # Playwright for headless automation
        self.browser: Optional[Browser] = None
        self.playwright = None
        
        logger.info(f"BackendBridge initialized for {self.platform_name} (headless={self.use_headless})")
    
    async def initialize(self) -> Tuple[bool, str]:
        """Initialize connection to platform"""
        if self.use_headless:
            return await self._init_headless()
        else:
            return self._init_api()
    
    def _init_api(self) -> Tuple[bool, str]:
        """Initialize API-based connection"""
        success, msg = self.session_manager.login()
        return success, msg
    
    async def _init_headless(self) -> Tuple[bool, str]:
        """Initialize headless browser"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            # Login
            page = await self.browser.new_page()
            success = await self._headless_login(page)
            
            if success:
                logger.info(f"✅ Headless login successful for {self.platform_name}")
                return True, "Headless login successful"
            else:
                return False, "Headless login failed"
        
        except Exception as e:
            logger.error(f"Headless init error: {str(e)}")
            return False, f"Headless init error: {str(e)}"
    
    async def _headless_login(self, page: Page) -> bool:
        """Perform login via headless browser."""
        try:
            username = os.environ.get(self.config["credentials"]["username_env"], "")
            password = os.environ.get(self.config["credentials"]["password_env"], "")
            
            if not username or not password:
                logger.error("Missing credentials for headless login")
                return False
            
            await page.goto(f"{self.config['agent_url']}/login", wait_until="networkidle")
            
            await self._fill_first_matching(page, [
                'input[name="username"]', 'input[name="email"]',
                'input[type="text"]', '#username', '#email'
            ], username)
            
            await self._fill_first_matching(page, [
                'input[name="password"]', 'input[type="password"]', '#password'
            ], password)
            
            await self._click_first_matching(page, [
                'button[type="submit"]', 'input[type="submit"]',
                'button:has-text("Login")', 'button:has-text("Sign In")'
            ])
            
            await page.wait_for_load_state("networkidle", timeout=15000)
            
            return await self._check_for_element(page, [
                'text="Dashboard"', 'text="Logout"',
                'button:has-text("Logout")', '.dashboard', '#dashboard'
            ])
        
        except Exception as e:
            logger.error(f"Headless login error: {str(e)}")
            return False
    
    async def _fill_first_matching(self, page: Page, selectors: list, value: str):
        """Fill the first matching form field from a list of selectors."""
        for selector in selectors:
            try:
                await page.fill(selector, value, timeout=5000)
                return True
            except Exception:
                continue
        return False
    
    async def _click_first_matching(self, page: Page, selectors: list):
        """Click the first matching element from a list of selectors."""
        for selector in selectors:
            try:
                await page.click(selector, timeout=5000)
                return True
            except Exception:
                continue
        return False
    
    async def _check_for_element(self, page: Page, selectors: list) -> bool:
        """Check if any of the given selectors exist on the page."""
        for selector in selectors:
            try:
                await page.wait_for_selector(selector, timeout=3000)
                return True
            except Exception:
                continue
        return False
    
    async def recharge_user(self, player_id: str, amount: float, game_id: str) -> Tuple[bool, str, Optional[str]]:
        """
        Add credits to a player's account.
        Returns: (success: bool, message: str, transaction_id: Optional[str])
        """
        if self.use_headless:
            return await self._headless_recharge(player_id, amount)
        else:
            return await self._api_recharge(player_id, amount, game_id)
    
    async def _api_recharge(self, player_id: str, amount: float, game_id: str) -> Tuple[bool, str, Optional[str]]:
        """Recharge via API"""
        try:
            endpoint = self.config["recharge_endpoint"]
            
            # Common API payload structures
            payload_variants = [
                {
                    "player_id": player_id,
                    "amount": amount,
                    "game_id": game_id
                },
                {
                    "playerId": player_id,
                    "credits": amount,
                    "gameId": game_id
                },
                {
                    "user_id": player_id,
                    "credit_amount": amount,
                    "game": game_id
                }
            ]
            
            for payload in payload_variants:
                success, response = self.session_manager.make_request(
                    "POST",
                    endpoint,
                    data=payload
                )
                
                if success:
                    # Extract transaction ID from response
                    tx_id = None
                    if isinstance(response, dict):
                        tx_id = response.get("transaction_id") or \
                               response.get("transactionId") or \
                               response.get("id") or \
                               response.get("txId")
                    
                    logger.info(f"✅ Recharge successful: {player_id} +{amount} credits")
                    return True, "Recharge successful", tx_id
            
            return False, "Recharge API call failed with all payload variants", None
        
        except Exception as e:
            logger.error(f"API recharge error: {str(e)}")
            return False, f"Recharge error: {str(e)}", None
    
    async def _headless_recharge(self, player_id: str, amount: float) -> Tuple[bool, str, Optional[str]]:
        """Recharge via headless browser automation."""
        try:
            if not self.browser:
                return False, "Headless browser not initialized", None
            
            page = await self.browser.new_page()
            
            # Navigate to recharge page
            navigated = await self._navigate_to_first(page, [
                f"{self.config['agent_url']}/agent/recharge",
                f"{self.config['agent_url']}/recharge",
                f"{self.config['agent_url']}/credits/add"
            ])
            
            if not navigated:
                await page.close()
                return False, "Could not navigate to recharge page", None
            
            # Fill form fields
            await self._fill_first_matching(page, [
                'input[name="player_id"]', 'input[name="playerId"]',
                'input[name="user_id"]', '#player_id', '#playerId'
            ], player_id)
            
            await self._fill_first_matching(page, [
                'input[name="amount"]', 'input[name="credits"]',
                '#amount', '#credits'
            ], str(amount))
            
            # Submit
            await self._click_first_matching(page, [
                'button[type="submit"]', 'button:has-text("Submit")',
                'button:has-text("Recharge")', 'button:has-text("Add Credits")'
            ])
            
            await page.wait_for_load_state("networkidle", timeout=10000)
            
            # Check success
            success = await self._check_for_element(page, [
                'text="Success"', 'text="successful"',
                '.success', '.alert-success'
            ])
            
            await page.close()
            
            if success:
                return True, "Recharge successful (headless)", None
            return False, "Recharge confirmation not found", None
        
        except Exception as e:
            logger.error(f"Headless recharge error: {str(e)}")
            return False, f"Headless recharge error: {str(e)}", None
    
    async def _navigate_to_first(self, page: Page, urls: list) -> bool:
        """Navigate to the first URL that loads successfully."""
        for url in urls:
            try:
                await page.goto(url, wait_until="networkidle", timeout=10000)
                return True
            except Exception:
                continue
        return False
    
    async def get_player_balance(self, player_id: str, game_id: str) -> Tuple[bool, Optional[float]]:
        """Get current balance for a player"""
        if self.use_headless:
            return await self._headless_get_balance(player_id)
        else:
            return await self._api_get_balance(player_id, game_id)
    
    async def _api_get_balance(self, player_id: str, game_id: str) -> Tuple[bool, Optional[float]]:
        """Get balance via API"""
        try:
            endpoint = self.config["balance_endpoint"]
            
            success, response = self.session_manager.make_request(
                "GET",
                endpoint,
                params={"player_id": player_id, "game_id": game_id}
            )
            
            if success and isinstance(response, dict):
                balance = response.get("balance") or \
                         response.get("credits") or \
                         response.get("amount") or \
                         response.get("credit_balance")
                
                if balance is not None:
                    return True, float(balance)
            
            return False, None
        
        except Exception as e:
            logger.error(f"API get balance error: {str(e)}")
            return False, None
    
    async def _headless_get_balance(self, player_id: str) -> Tuple[bool, Optional[float]]:
        """Get balance via headless browser"""
        # Implementation would navigate to player info page and scrape balance
        # Simplified for now
        return False, None
    
    async def deduct_credits(self, player_id: str, amount: float, game_id: str) -> Tuple[bool, str, Optional[str]]:
        """
        Deduct credits from a player's account (for withdrawals).
        Returns: (success: bool, message: str, transaction_id: Optional[str])
        """
        if self.use_headless:
            return await self._headless_deduct(player_id, amount)
        else:
            return await self._api_deduct(player_id, amount, game_id)
    
    async def _api_deduct(self, player_id: str, amount: float, game_id: str) -> Tuple[bool, str, Optional[str]]:
        """Deduct credits via API"""
        try:
            endpoint = self.config["deduct_endpoint"]
            
            payload = {
                "player_id": player_id,
                "amount": amount,
                "game_id": game_id
            }
            
            success, response = self.session_manager.make_request(
                "POST",
                endpoint,
                data=payload
            )
            
            if success:
                tx_id = None
                if isinstance(response, dict):
                    tx_id = response.get("transaction_id") or response.get("id")
                
                logger.info(f"✅ Deduction successful: {player_id} -{amount} credits")
                return True, "Deduction successful", tx_id
            else:
                return False, "Deduction API call failed", None
        
        except Exception as e:
            logger.error(f"API deduct error: {str(e)}")
            return False, f"Deduct error: {str(e)}", None
    
    async def _headless_deduct(self, player_id: str, amount: float) -> Tuple[bool, str, Optional[str]]:
        """Deduct credits via headless browser"""
        # Similar to headless recharge but for deduction
        return False, "Headless deduction not implemented", None
    
    async def close(self):
        """Cleanup resources"""
        self.session_manager.logout()
        
        if self.browser:
            await self.browser.close()
        
        if self.playwright:
            await self.playwright.stop()
        
        logger.info(f"BackendBridge closed for {self.platform_name}")
