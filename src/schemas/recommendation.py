"""
DATA MODEL: Structures the final recommendations, balancing confidence indices with clear reasoning descriptions.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class Recommendation(BaseModel):
    hospital_id: str
    confidence: float
    reasoning: str
