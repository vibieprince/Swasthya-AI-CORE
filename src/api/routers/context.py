"""
SWASTHYA AI CORE — Context API Router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.api.dependencies import get_context_service
from src.common.exceptions import ContextExpiredError
from src.dtos.context_dtos import ContextAnalyzeRequest, ContextAnalyzeResponse
from src.services.context_service import ContextService

router = APIRouter(prefix="/api/context", tags=["Context"])


@router.post("/analyze", response_model=ContextAnalyzeResponse)
async def analyze_context(
    request: ContextAnalyzeRequest,
    service: ContextService = Depends(get_context_service),
) -> ContextAnalyzeResponse | JSONResponse:
    """
    Runs complete Context Intelligence Pipeline.

    Supports multi-turn conversations via the optional `context_id` field.
    Returns structured Patient Context.
    If incomplete, returns a follow-up question AND the context_id the client
    must echo back in subsequent requests.

    Returns HTTP 410 Gone if a provided context_id has expired (15-min TTL).
    """
    try:
        return await service.analyze_context(request)
    except ContextExpiredError as exc:
        return JSONResponse(
            status_code=410,
            content={
                "code": exc.code,
                "message": exc.message,
                "detail": "Your conversation session has expired. Please start a new conversation by omitting context_id.",
            },
        )
