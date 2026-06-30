"""
DATA MODEL: Shared basic type models used throughout different system entities.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class PaginationInfo(BaseModel):
    page: int
    size: int
