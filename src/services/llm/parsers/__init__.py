"""
FORMAT ENFORCEMENT: Strips out non-JSON strings to safely parse responses into expected Pydantic models.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any

logger = logging.getLogger(__name__)
