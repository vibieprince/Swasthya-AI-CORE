"""
SWASTHYA AI CORE — Dependency Injection.

Provides FastAPI dependencies for all services and infrastructure components.
"""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends

from src.infrastructure.llm.gateway import LLMGateway
from src.pipelines.context.orchestrator import ContextOrchestrator
from src.services.context_service import ContextService
from src.services.discovery_service import DiscoveryService
from src.services.task_service import TaskService


# ── Infrastructure ─────────────────────────────────────────────────────────────

async def get_llm_gateway() -> AsyncGenerator[LLMGateway, None]:
    """Provide the multi-provider LLM gateway."""
    # Instantiated once per request
    yield LLMGateway()


# ── Orchestrators ──────────────────────────────────────────────────────────────

async def get_context_orchestrator(
    gateway: LLMGateway = Depends(get_llm_gateway),
) -> AsyncGenerator[ContextOrchestrator, None]:
    """Provide the Context pipeline orchestrator."""
    yield ContextOrchestrator(gateway)


# ── Services ───────────────────────────────────────────────────────────────────

async def get_context_service(
    orchestrator: ContextOrchestrator = Depends(get_context_orchestrator),
) -> AsyncGenerator[ContextService, None]:
    """Provide the Context Application Service."""
    yield ContextService(orchestrator)


async def get_discovery_service() -> AsyncGenerator[DiscoveryService, None]:
    """Provide the Discovery Application Service."""
    yield DiscoveryService()


async def get_task_service() -> AsyncGenerator[TaskService, None]:
    """Provide the Task Progress Service."""
    yield TaskService()
