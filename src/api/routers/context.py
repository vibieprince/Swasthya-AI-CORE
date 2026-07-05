"""
SWASTHYA AI CORE — Context API Router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_context_service
from src.dtos.context_dtos import ContextAnalyzeRequest, ContextAnalyzeResponse
from src.services.context_service import ContextService

router = APIRouter(prefix="/api/context", tags=["Context"])


@router.post("/analyze", response_model=ContextAnalyzeResponse)
async def analyze_context(
    request: ContextAnalyzeRequest,
    service: ContextService = Depends(get_context_service),
) -> ContextAnalyzeResponse:
    """
    Runs complete Context Intelligence Pipeline.
    Returns structured Patient Context.
    If incomplete, returns a follow-up question.
    """
    return await service.analyze_context(request)
