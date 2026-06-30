"""
ENDPOINT: Receives raw multi-turn user messages and returns structured patient profiles.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

class ContextRequest(BaseModel):
    message: str

class ContextResponse(BaseModel):
    patient_profile: Dict[str, Any]

@router.post("/", response_model=ContextResponse)
async def process_context(request: ContextRequest) -> ContextResponse:
    logger.info("Processing context.")
    return ContextResponse(patient_profile={})
