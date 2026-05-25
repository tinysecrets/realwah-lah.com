"""
Autonomous UI Adaptation System
Automatically detects and adapts to game panel UI changes

LEGAL USE: Maintains operational continuity when game providers update their interfaces
"""

import logging
from playwright.async_api import Page
from typing import Dict, Optional
import json

logger = logging.getLogger(__name__)

class UIAdaptationEngine:
    """
    Autonomously detects UI changes and updates selectors.
    When game panels update their layout, this finds new button locations.
    """
    
    def __init__(self, platform_id: str):
        self.platform_id = platform_id
        self.selector_memory = {}  # Stores successful selectors
        self.load_memory()
    
    def load_memory(self):
        """Load previously successful selectors from memory"""
        try:
            with open(f"/app/backend/middleware/ui_memory_{self.platform_id}.json", "r") as f:
                self.selector_memory = json.load(f)
            logger.info(f"Loaded UI memory for {self.platform_id}")
        except FileNotFoundError:
            logger.info(f"No UI memory found for {self.platform_id}, starting fresh")
    
    def save_memory(self):
        """Save successful selectors for future use"""
        try:
            with open(f"/app/backend/middleware/ui_memory_{self.platform_id}.json", "w") as f:
                json.dump(self.selector_memory, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save UI memory: {str(e)}")
    
    async def find_recharge_button(self, page: Page) -> Optional[str]:
        """
        Autonomously find the recharge/credit button even if UI changed.
        
        Strategy:
        1. Try known selectors first (from memory)
        2. If failed, search by common text patterns
        3. If failed, analyze page structure and find likely candidates
        4. Save successful selector to memory
        """
        
        # Step 1: Try known selectors
        if "recharge_button" in self.selector_memory:
            known_selectors = self.selector_memory["recharge_button"]
            for selector in known_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        logger.info(f"✅ Found recharge button using known selector: {selector}")
                        return selector
                except Exception:
                    continue
        
        # Step 2: Search by common text patterns
        text_patterns = [
            "Recharge",
            "Add Credits",
            "Add Coins",
            "Deposit",
            "Credit",
            "充值",  # Chinese
            "Reload",
            "Top Up"
        ]
        
        for pattern in text_patterns:
            try:
                # Try exact match
                selector = f'button:has-text("{pattern}")'
                if await page.locator(selector).count() > 0:
                    logger.info(f"✅ Found recharge button by text: {pattern}")
                    self._save_successful_selector("recharge_button", selector)
                    return selector
                
                # Try case-insensitive
                selector = f'button:text-is("{pattern}")'
                if await page.locator(selector).count() > 0:
                    logger.info(f"✅ Found recharge button by text (case-insensitive): {pattern}")
                    self._save_successful_selector("recharge_button", selector)
                    return selector
            except Exception:
                continue
        
        # Step 3: Analyze page structure
        logger.info("Known selectors failed, analyzing page structure...")
        
        # Look for buttons with common class patterns
        class_patterns = [
            "recharge",
            "credit",
            "deposit",
            "add-coin",
            "top-up"
        ]
        
        all_buttons = await page.locator("button").all()
        
        for button in all_buttons:
            try:
                # Check class names
                classes = await button.get_attribute("class") or ""
                for pattern in class_patterns:
                    if pattern in classes.lower():
                        selector = f'button.{classes.split()[0]}'
                        logger.info(f"✅ Found recharge button by class analysis: {selector}")
                        self._save_successful_selector("recharge_button", selector)
                        return selector
                
                # Check button text content
                text = await button.text_content() or ""
                if any(p.lower() in text.lower() for p in ["recharge", "credit", "add", "deposit"]):
                    # Generate unique selector using text
                    selector = f'button:has-text("{text.strip()}")'
                    logger.info(f"✅ Found recharge button by content analysis: {selector}")
                    self._save_successful_selector("recharge_button", selector)
                    return selector
            except Exception:
                continue
        
        logger.error(f"❌ Could not find recharge button for {self.platform_id}")
        return None
    
    async def find_input_field(self, page: Page, field_type: str) -> Optional[str]:
        """
        Find input fields (player_id, amount) even if selectors changed.
        
        Args:
            field_type: "player_id" or "amount"
        """
        
        # Common field identifiers
        identifiers = {
            "player_id": ["player", "user", "id", "username", "account"],
            "amount": ["amount", "credit", "coin", "value", "quantity"]
        }
        
        patterns = identifiers.get(field_type, [])
        
        # Try by name attribute
        for pattern in patterns:
            try:
                selector = f'input[name*="{pattern}"]'
                if await page.locator(selector).count() > 0:
                    logger.info(f"✅ Found {field_type} input by name: {selector}")
                    self._save_successful_selector(f"{field_type}_input", selector)
                    return selector
            except Exception:
                continue
        
        # Try by id attribute
        for pattern in patterns:
            try:
                selector = f'input[id*="{pattern}"]'
                if await page.locator(selector).count() > 0:
                    logger.info(f"✅ Found {field_type} input by id: {selector}")
                    self._save_successful_selector(f"{field_type}_input", selector)
                    return selector
            except Exception:
                continue
        
        # Try by placeholder
        for pattern in patterns:
            try:
                selector = f'input[placeholder*="{pattern}"]'
                if await page.locator(selector).count() > 0:
                    logger.info(f"✅ Found {field_type} input by placeholder: {selector}")
                    self._save_successful_selector(f"{field_type}_input", selector)
                    return selector
            except Exception:
                continue
        
        logger.error(f"❌ Could not find {field_type} input for {self.platform_id}")
        return None
    
    def _save_successful_selector(self, element_type: str, selector: str):
        """Save a successful selector to memory"""
        if element_type not in self.selector_memory:
            self.selector_memory[element_type] = []
        
        # Add to beginning (most recent first)
        if selector not in self.selector_memory[element_type]:
            self.selector_memory[element_type].insert(0, selector)
            # Keep only last 5 successful selectors
            self.selector_memory[element_type] = self.selector_memory[element_type][:5]
            
            self.save_memory()
    
    async def verify_page_structure(self, page: Page) -> Dict[str, bool]:
        """
        Verify all required elements are present.
        Returns dict of found elements.
        """
        recharge_btn = await self.find_recharge_button(page)
        player_input = await self.find_input_field(page, "player_id")
        amount_input = await self.find_input_field(page, "amount")
        
        return {
            "recharge_button": recharge_btn is not None,
            "player_id_input": player_input is not None,
            "amount_input": amount_input is not None,
            "all_found": all([recharge_btn, player_input, amount_input])
        }
