"""
DATA MODEL: System contracts used to validate and stream real-time progress status models.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class ProgressUpdate(BaseModel):
    status: str
    details: str
