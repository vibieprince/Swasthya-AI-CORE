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
            result_url = result.get("url")
            candidates.append(
                HospitalCandidate(
                    candidate_id=str(uuid.uuid4()),
                    hospital_name=name,
                    raw_address=None,
                    source="tavily",
                    source_url=result_url,
                    # Map the URL to website so the researcher can scrape it
                    # and dedup merge can propagate it to the Maps-anchored entity.
                    website=result_url,
                    raw_scrape_data=result.get("content", "")[:2000],
                    data_quality_score=0.5,
                )
            )

        return candidates

    def _extract_hospital_name(self, title: str, url: str) -> str:
        """
        Extract a canonical hospital name from a Tavily search result title.

        Strategy: classify by entity type, not by delimiter splitting.
        Step 1: Reject titles that describe content (pages/articles), not entities.
        Step 2: Extract name using delimiter-agnostic splitting.
        Step 3: Validate the extracted name resembles a healthcare facility.
        """
        import re

        if not title:
            return ""

        title_stripped = title.strip()
        title_lower = title_stripped.lower()

        # Step 1: Reject content-describing titles
        rejection_patterns = [
            r"\b(top|best|vs\.?|versus|difference between)\b",
            r"\b(how|why|what|when|where|does|can|should|is|are)\b",
            r"\b(\d+\s+hospitals?|\d+\s+clinics?|list of|directory|guide to)\b",
            r"\b(review|reviews|complaint|complaints|feedback)\b",
            r"\b(near me|cost|price|fee|charges?|appointment)\b",
            r"\b(our services?|services? offered|about us|contact us)\b",
            r"[\?\!]",
        ]
        for pattern in rejection_patterns:
            if re.search(pattern, title_lower):
                return ""

        # Step 2: Split on ALL separators including em-dash (U+2014), en-dash (U+2013), bullet
        parts = re.split(r"\s*[|\-\u2013\u2014:,\u2022]\s*", title_stripped)
        name = parts[0].strip()

        # Step 3: Validate extracted name is a healthcare facility
        if not name or len(name) < 4 or len(name) > 60:
            return ""

        name_lower = name.lower()
        facility_indicators = [
            "hospital", "clinic", "medical", "centre", "center", "institute",
            "healthcare", "health care", "nursing home", "infirmary",
            "medicare", "medicity", "medicover", "apollo", "fortis", "max",
            "aiims", "nimhans", "narayana", "care",
        ]
        if not any(kw in name_lower for kw in facility_indicators):
            return ""

        # Reject names that are still clearly descriptive after splitting
        if re.search(r"^(our|the best|leading|top)\b", name_lower):
            return ""

        return name
