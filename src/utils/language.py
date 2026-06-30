"""
SANITIZATION: Utilities to process multi-language inputs and enforce text locks across turns.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any

logger = logging.getLogger(__name__)

def sanitize_language(text: str) -> str:
    logger.info("Sanitizing language input.")
    return text.strip()
