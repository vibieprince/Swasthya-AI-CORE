"""
ASSETS: Contains system instructions for intent parsing, language locking, and follow-up generation.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any

logger = logging.getLogger(__name__)

CONTEXT_PROMPT_TEMPLATE = "Parse the user's medical query."
