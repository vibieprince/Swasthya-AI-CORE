"""
SWASTHYA AI CORE — Hospital Website Scraper.

Bandwidth-optimized, resilient multi-engine scraper.

Scraping hierarchy (Issue 4 — HTTPX first, browser only as last resort):
    1. HTTPX + BeautifulSoup (pure HTTP — zero browser overhead)
    2. Playwright with resource blocking (Issue 5 — blocks images/fonts/media/ads)
    3. Selenium with minimal options (last resort)

Early-exit optimization (Issue 4):
    After HTTPX parsing, check if enough clinical data was extracted.
    If yes, skip browser entirely.

Playwright optimization (Issue 5):
    Blocks: images, fonts, media, stylesheets, analytics, ad networks.
    Downloads: HTML + essential XHR only (~95% bandwidth reduction).

Timeouts (Issue 9):
    HTTPX: 10s
    Playwright: 15s
    Selenium: 15s
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional

from bs4 import BeautifulSoup

from src.common.logging import get_logger
from src.config.settings import get_settings

logger = get_logger(__name__)

# Resources to block in Playwright (Issue 5)
_PLAYWRIGHT_BLOCKED_TYPES = {
    "image", "stylesheet", "font", "media",
    "websocket", "manifest", "other",
}

# Ad/analytics domains to block in Playwright (Issue 5)
_BLOCKED_URL_PATTERNS = (
    "google-analytics.com", "googletagmanager.com",
    "facebook.net", "doubleclick.net", "googlesyndication.com",
    "hotjar.com", "clarity.ms", "amazon-adsystem.com",
    "adsense", "adsbygoogle", "analytics",
)

# Minimum clinical signal keywords — if HTTPX content contains these,
# skip browser automation entirely (Issue 4)
_CLINICAL_SIGNAL_KEYWORDS = {
    "emergency", "casualty", "icu", "intensive care",
    "specialist", "department", "cardiology", "neurology",
    "orthopaedic", "orthopedic", "gynecology", "gynaecology",
    "paediatric", "pediatric", "contact", "phone", "appointment",
    "nabh", "accredited", "bed", "facility",
}
_CLINICAL_SIGNAL_THRESHOLD = 4  # 4+ keywords → sufficient content found


class HospitalScraper:
    """
    Multi-engine hospital website scraper with aggressive bandwidth optimisation.

    Engine order: HTTPX+BS4 → Playwright → Selenium
    Upgrades to browser only when HTML content is insufficient.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def scrape(self, url: str, task_id: str) -> Optional[str]:
        """
        Scrape a hospital website and return extracted clinical text.

        Returns extracted text (max 5000 chars) or None if all engines failed.
        """
        if not url or not url.startswith(("http://", "https://")):
            return None

        # ── Engine 1: HTTPX + BeautifulSoup (no browser, fastest) ─────────────
        content = await self._scrape_httpx(url, task_id)
        if content and self._has_sufficient_clinical_content(content):
            logger.debug(
                "HTTPX scrape sufficient — skipping browser",
                extra={"url": url, "task_id": task_id},
            )
            return content

        # ── Engine 2: Playwright with resource blocking ────────────────────────
        playwright_content = await self._scrape_playwright(url, task_id)
        if playwright_content:
            return playwright_content

        # ── Engine 3: Selenium (last resort) ──────────────────────────────────
        selenium_content = await self._scrape_selenium(url, task_id)
        if selenium_content:
            return selenium_content

        # Return partial HTTPX content if we have it, rather than nothing
        return content

    def _has_sufficient_clinical_content(self, text: str) -> bool:
        """
        Check whether extracted text contains enough clinical signals.

        Used to decide whether to upgrade to browser automation.
        """
        text_lower = text.lower()
        found = sum(1 for kw in _CLINICAL_SIGNAL_KEYWORDS if kw in text_lower)
        return found >= _CLINICAL_SIGNAL_THRESHOLD

    async def _scrape_httpx(self, url: str, task_id: str) -> Optional[str]:
        """Pure HTTP scrape using HTTPX + BeautifulSoup. Timeout: 10s (Issue 9)."""
        from src.infrastructure.http.client import get_http_client

        client = get_http_client()
        try:
            response = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
                },
                timeout=10.0,  # Issue 9
                follow_redirects=True,
            )
            if response.status_code == 200:
                return self._extract_text(response.text)[:5000]
            logger.debug(
                "HTTPX returned non-200",
                extra={"url": url, "status": response.status_code, "task_id": task_id},
            )
        except Exception as exc:
            logger.debug(
                "HTTPX scraping failed",
                extra={"url": url, "task_id": task_id, "error": str(exc)[:150]},
            )
        return None

    async def _scrape_playwright(self, url: str, task_id: str) -> Optional[str]:
        """
        Playwright scrape with aggressive resource blocking.

        Blocks all non-essential resources to cut bandwidth by ~95% (Issue 5).
        Timeout: 15s per operation (Issue 9).
        """
        try:
            from playwright.async_api import async_playwright, Route

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-background-networking",
                        "--disable-default-apps",
                        "--disable-extensions",
                        "--disable-sync",
                        "--no-first-run",
                    ],
                )
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    java_script_enabled=True,
                    bypass_csp=True,
                )

                page = await context.new_page()

                # Block non-essential resources (Issue 5)
                async def _block_resources(route: Route) -> None:
                    resource_type = route.request.resource_type
                    request_url = route.request.url

                    # Block by resource type
                    if resource_type in _PLAYWRIGHT_BLOCKED_TYPES:
                        await route.abort()
                        return

                    # Block analytics/ad domains
                    if any(pattern in request_url for pattern in _BLOCKED_URL_PATTERNS):
                        await route.abort()
                        return

                    await route.continue_()

                await page.route("**/*", _block_resources)

                try:
                    await asyncio.wait_for(
                        page.goto(url, wait_until="domcontentloaded"),
                        timeout=15.0,  # Issue 9
                    )
                    # Brief pause for essential XHR to complete
                    await asyncio.sleep(1)
                    html = await page.content()
                    return self._extract_text(html)[:5000]
                finally:
                    await page.close()
                    await context.close()
                    await browser.close()

        except asyncio.TimeoutError:
            logger.debug("Playwright timed out", extra={"url": url, "task_id": task_id})
        except Exception as exc:
            logger.debug(
                "Playwright scraping failed",
                extra={"url": url, "task_id": task_id, "error": str(exc)[:150]},
            )
        return None

    async def _scrape_selenium(self, url: str, task_id: str) -> Optional[str]:
        """Selenium scrape running in a thread executor. Timeout: 15s (Issue 9)."""
        try:
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._selenium_sync, url),
                timeout=15.0,  # Issue 9
            )
        except asyncio.TimeoutError:
            logger.debug("Selenium timed out", extra={"url": url, "task_id": task_id})
        except Exception as exc:
            logger.debug(
                "Selenium scraping failed",
                extra={"url": url, "task_id": task_id, "error": str(exc)[:150]},
            )
        return None

    def _selenium_sync(self, url: str) -> Optional[str]:
        """Synchronous Selenium scraping (runs in executor thread)."""
        driver = None
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options

            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1280,720")
            # Disable images and CSS to reduce bandwidth (Issue 4)
            prefs = {
                "profile.managed_default_content_settings.images": 2,
                "profile.default_content_setting_values.notifications": 2,
                "profile.managed_default_content_settings.stylesheets": 2,
            }
            options.add_experimental_option("prefs", prefs)

            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(15)  # Issue 9
            driver.get(url)
            html = driver.page_source
            return self._extract_text(html)[:5000]
        except Exception:
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    @staticmethod
    def _extract_text(html: str) -> str:
        """Parse HTML and extract meaningful clinical text using BeautifulSoup."""
        soup = BeautifulSoup(html, "lxml")

        # Remove all noise elements
        for tag in soup([
            "script", "style", "nav", "footer", "header",
            "noscript", "meta", "link", "iframe", "svg",
            "button", "form", "input", "select", "textarea",
        ]):
            tag.decompose()

        # Prefer semantic content areas
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find(id="content")
            or soup.find(id="main-content")
            or soup.find(class_=re.compile(r"content|main", re.I))
        )
        target = main if main else soup

        text = target.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        return text
