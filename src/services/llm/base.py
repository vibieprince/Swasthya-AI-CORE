"""
PROTOCOL STRATEGY: Defines an abstract Python interface for reliable, multi-vendor inference.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any

logger = logging.getLogger(__name__)

class LLMProviderProtocol(Protocol):
    def generate(self, prompt: str) -> str: ...
