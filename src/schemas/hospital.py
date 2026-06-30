"""
DATA MODEL: Defines the exact structure for hospital records, including vector embedding configurations.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class HospitalRecord(BaseModel):
    id: str
    name: str
    vector: Optional[List[float]] = None
