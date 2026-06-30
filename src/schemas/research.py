"""
DATA MODEL: Schema models handling raw web data extraction and structural analysis.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class RawWebData(BaseModel):
    url: str
    content: str
