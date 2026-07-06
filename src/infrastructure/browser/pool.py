"""
SWASTHYA AI CORE — Playwright Browser Pool.

Maintains a single long-lived Chromium instance across the worker lifecycle
to drastically reduce overhead (Issue 2).
"""

from __future__ import annotations

import asyncio
from typing import Optional

from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext
from src.common.logging import get_logger

logger = get_logger(__name__)

_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_lock = asyncio.Lock()


async def initialize_browser() -> None:
    """Launch the shared browser instance."""
    global _playwright, _browser
    async with _lock:
        if _browser is not None:
            return
            
        logger.info("Initializing shared Playwright browser...")
        try:
            _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch(
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
            logger.info("Shared browser initialized.")
        except Exception as exc:
            logger.error("Failed to initialize browser", extra={"error": str(exc)})
            raise


async def get_browser_context() -> BrowserContext:
    """Get a new isolated context from the shared browser."""
    global _browser
    if _browser is None:
        await initialize_browser()
        
    if _browser is None:
        raise RuntimeError("Browser not initialized.")
        
    return await _browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        java_script_enabled=True,
        bypass_csp=True,
    )


async def close_browser() -> None:
    """Shutdown the shared browser gracefully."""
    global _playwright, _browser
    async with _lock:
        if _browser:
            await _browser.close()
            _browser = None
        if _playwright:
            await _playwright.stop()
            _playwright = None
        logger.info("Shared browser closed.")
