"""
DATA MODEL: Structural contracts for patient profiles, condition records, and chat summaries.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class PatientProfile(BaseModel):
    id: str
    history: List[str]
