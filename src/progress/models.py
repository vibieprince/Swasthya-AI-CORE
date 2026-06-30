"""
TELEMETRY CONTRACTS: Defines the exact structure and schemas for status payloads sent to the client.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class ProgressStatus(BaseModel):
    event: str
    percentage: int
    message: str
