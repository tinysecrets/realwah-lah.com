"""
Sugar Sweeps Page Inspector

Opens sugarsweeps.com and takes screenshots to help debug selectors
"""

import asyncio
from playwright.async_api import async_playwright
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def inspect_sugar_sweeps():
    """Open Sugar Sweeps and take screenshots"""
    
    playwright = await async_playwright().start()
    
    browser = await playwright.chromium.launch(
        headless=False,  # Show browser for debugging
        args=['--disable-blink-features=AutomationControlled']
    )
    
    context = await browser.new_context(
        viewport={'width': 414, 'height': 896},  # iPhone size
        user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'
    )
    
    page = await context.new_page()
    
    try:
        logger.info("🌐 Navigating to sugarsweeps.com...")
        await page.goto("https://sugarsweeps.com", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        
        # Screenshot 1: Initial page
        await page.screenshot(path="/tmp/sugar_sweeps_home.png", full_page=True)
        logger.info("📸 Screenshot saved: /tmp/sugar_sweeps_home.png")
        
        # Look for login button/link
        login_selectors = [
            'a:has-text("Login")',
            'a:has-text("Sign In")',
            'button:has-text("Login")',
            '[href*="login"]',
            '.login-btn',
            '#login'
        ]
        
        for selector in login_selectors:
            element = await page.query_selector(selector)
            if element:
                logger.info(f"✅ Found login element: {selector}")
                await element.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                break
        
        # Screenshot 2: Login page
        await page.screenshot(path="/tmp/sugar_sweeps_login.png", full_page=True)
        logger.info("📸 Screenshot saved: /tmp/sugar_sweeps_login.png")
        
        # Print page HTML (first 2000 chars)
        html = await page.content()
        logger.info(f"\n📄 Page HTML (first 2000 chars):\n{html[:2000]}")
        
        # List all input fields
        inputs = await page.query_selector_all('input')
        logger.info(f"\n🔍 Found {len(inputs)} input fields:")
        for i, inp in enumerate(inputs):
            attrs = await inp.evaluate('el => ({ type: el.type, name: el.name, id: el.id, placeholder: el.placeholder, class: el.className })')
            logger.info(f"   Input {i+1}: {attrs}")
        
        # Wait for user to inspect
        logger.info("\n⏸️  Browser will stay open for 60 seconds for inspection...")
        await asyncio.sleep(60)
    
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        await browser.close()
        await playwright.stop()

if __name__ == "__main__":
    asyncio.run(inspect_sugar_sweeps())
