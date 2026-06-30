"""
DATA HARVESTER: Directs scraper tasks to run heavy, headless browser crawls out-of-band.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any

logger = logging.getLogger(__name__)

def run_scraping_task() -> None:
    logger.info("Running scraping task.")
    pass
