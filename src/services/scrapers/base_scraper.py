"""
PROTOCOL STRATEGY: Base abstraction layer establishing error handling and retry behaviors for web scrapers.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any

logger = logging.getLogger(__name__)

class ScraperProtocol(Protocol):
    def scrape(self, url: str) -> str: ...
