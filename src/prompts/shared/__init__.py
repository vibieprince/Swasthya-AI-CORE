"""
ASSETS: Stores global safety guardrails and multi-language alignment guidelines.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any

logger = logging.getLogger(__name__)

SAFETY_GUARDRAILS = "Do not provide definitive medical diagnoses."
