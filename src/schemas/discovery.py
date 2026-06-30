"""
DATA MODEL: Validation contracts used to track and pass scraping search parameters.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class DiscoveryParams(BaseModel):
    query: str
    location: str
