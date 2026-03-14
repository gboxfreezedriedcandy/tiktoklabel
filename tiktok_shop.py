import json
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page
from playwright_stealth import stealth_async

COOKIES_FILE = Path("cookies.json")
TIKTOK_SHOP_URL = "https://seller.tiktok.com"


async def save_cookies(context: BrowserContext) -> None:
    cookies = await context.cookies()
    COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
    print(f"Saved {len(cookies)} cookies to {COOKIES_FILE}")


async def load_cookies(context: BrowserContext) -> bool:
    """Load cookies from file into context. Returns True if cookies were loaded."""
    if not COOKIES_FILE.exists():
        return False
    cookies = json.loads(COOKIES_FILE.read_text())
    await context.add_cookies(cookies)
    print(f"Loaded {len(cookies)} cookies from {COOKIES_FILE}")
    return True


async def login(playwright) -> BrowserContext:
    """Open browser for manual login, then save session cookies."""
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()
    await stealth_async(page)

    print("Opening TikTok Shop Seller Center...")
    await page.goto(TIKTOK_SHOP_URL)

    print("Please log in manually in the browser window.")
    print("Waiting for you to reach the seller dashboard...")

    # Wait until the URL changes away from the login page
    await page.wait_for_url(
        lambda url: "login" not in url and "passport" not in url,
        timeout=120_000,
    )
    # Give the page a moment to fully settle after redirect
    await page.wait_for_load_state("networkidle")

    await save_cookies(context)
    print("Login complete. Cookies saved.")
    return context


async def get_authenticated_context(playwright) -> tuple[object, BrowserContext, Page]:
    """
    Return (browser, context, page) with an authenticated session.
    Reuses saved cookies if available, otherwise triggers manual login.
    """
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()
    await stealth_async(page)

    has_cookies = await load_cookies(context)

    if has_cookies:
        print("Resuming session with saved cookies...")
        await page.goto(TIKTOK_SHOP_URL)
        await page.wait_for_load_state("networkidle")

        # Check whether cookies are still valid
        if "login" in page.url or "passport" in page.url:
            print("Saved cookies expired. Triggering fresh login...")
            await browser.close()
            async with async_playwright() as pw:
                ctx = await login(pw)
                # Re-open after login so caller gets a usable context
                browser2 = await pw.chromium.launch(headless=False)
                context2 = await browser2.new_context()
                await load_cookies(context2)
                page2 = await context2.new_page()
                await stealth_async(page2)
                await page2.goto(TIKTOK_SHOP_URL)
                await page2.wait_for_load_state("networkidle")
                return browser2, context2, page2
    else:
        print("No saved cookies found. Starting fresh login...")
        await browser.close()
        async with async_playwright() as pw:
            await login(pw)
        # Re-launch and load the newly saved cookies
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await stealth_async(page)
        await load_cookies(context)
        await page.goto(TIKTOK_SHOP_URL)
        await page.wait_for_load_state("networkidle")

    return browser, context, page


async def main():
    async with async_playwright() as playwright:
        browser, context, page = await get_authenticated_context(playwright)
        print(f"Current URL: {page.url}")
        print("Session ready. Add your label download logic here.")
        # Keep the browser open so you can inspect the page
        input("Press Enter to close the browser...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
