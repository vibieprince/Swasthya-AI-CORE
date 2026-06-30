"""
ASSETS: Houses query structures used to locate regional medical facilities.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any

logger = logging.getLogger(__name__)

DISCOVERY_PROMPT_TEMPLATE = "Find hospitals in the following region."
