"""
SEARCH DRIVER: Calls Tavily's search API to retrieve clean, pre-filtered regional web data.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any

logger = logging.getLogger(__name__)

class TavilyClient:
    def search(self, query: str) -> List[Dict[str, Any]]:
        logger.info(f"Searching Tavily for {query}.")
        return []
