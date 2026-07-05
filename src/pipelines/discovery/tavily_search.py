"""
SWASTHYA AI CORE — Tavily Search Integration.

Executes multi-query hospital discovery via the Tavily REST API.
No Tavily SDK — direct HTTPX calls only.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from src.common.exceptions import TavilySearchError
from src.common.logging import get_logger
from src.config.settings import get_settings
from src.domain.discovery.models import HospitalCandidate, SearchStrategy
from src.infrastructure.http.client import get_http_client

logger = get_logger(__name__)

_TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_MAX_CONCURRENT_QUERIES = 3


class TavilySearcher:
    """
    Executes hospital discovery searches via the Tavily API.

    Runs multiple queries concurrently, deduplicated by URL.
    Each result is normalised into a HospitalCandidate.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def search(
        self,
        strategy: SearchStrategy,
        task_id: str,
    ) -> list[HospitalCandidate]:
        """
        Execute all strategy queries against Tavily.

        Args:
            strategy: The generated search strategy.
            task_id: Task ID for logging.

        Returns:
            List of raw HospitalCandidate objects discovered from Tavily.
        """
        queries = strategy.primary_search_queries[:_MAX_CONCURRENT_QUERIES]
        if not queries:
            return []

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_QUERIES)

        async def _query_one(query: str) -> list[HospitalCandidate]:
            async with semaphore:
                return await self._execute_query(query, task_id)

        results = await asyncio.gather(*[_query_one(q) for q in queries], return_exceptions=True)

        candidates: list[HospitalCandidate] = []
        seen_urls: set[str] = set()

        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "Tavily query failed",
                    extra={"task_id": task_id, "error": str(result)},
                )
                continue
            for candidate in result:
                url = candidate.source_url or ""
                if url and url in seen_urls:
                    continue
                seen_urls.add(url)
                candidates.append(candidate)

        logger.info(
            "Tavily search completed",
            extra={"task_id": task_id, "candidate_count": len(candidates)},
        )
        return candidates

    async def _execute_query(self, query: str, task_id: str) -> list[HospitalCandidate]:
        """Execute a single Tavily search query."""
        client = get_http_client()
        payload: dict[str, Any] = {
            "api_key": self._settings.tavily_api_key,
            "query": query,
            "search_depth": "advanced",
            "include_domains": [],
            "exclude_domains": ["reddit.com", "quora.com"],
            "max_results": 8,
            "include_answer": False,
            "include_raw_content": False,
        }

        try:
            response = await client.post(_TAVILY_SEARCH_URL, json=payload, timeout=30.0)
            if response.status_code != 200:
                raise TavilySearchError(
                    f"Tavily returned HTTP {response.status_code}",
                    status_code=response.status_code,
                )
            body = response.json()
        except TavilySearchError:
            raise
        except Exception as exc:
            raise TavilySearchError(f"Tavily request failed: {exc}") from exc

        candidates: list[HospitalCandidate] = []
        for result in body.get("results", []):
            name = self._extract_hospital_name(result.get("title", ""), result.get("url", ""))
            if not name:
                continue
            candidates.append(
                HospitalCandidate(
                    candidate_id=str(uuid.uuid4()),
                    hospital_name=name,
                    raw_address=None,
                    source="tavily",
                    source_url=result.get("url"),
                    raw_scrape_data=result.get("content", "")[:2000],
                    data_quality_score=0.5,
                )
            )

        return candidates

    def _extract_hospital_name(self, title: str, url: str) -> str:
        """
        Heuristically extract a hospital name from a Tavily search result title.

        Filters out non-hospital results (news articles, directories, etc.)
        """
        hospital_indicators = [
            "hospital", "clinic", "medical centre", "medical center",
            "healthcare", "health care", "nursing home", "infirmary",
            "medicare", "medicity", "medicover", "apollo", "fortis",
            "max hospital", "aiims", "nimhans", "narayana",
        ]
        title_lower = title.lower()
        if any(kw in title_lower for kw in hospital_indicators):
            # Clean up common suffixes
            name = title.split("|")[0].split("-")[0].strip()
            return name[:150]
        return ""
