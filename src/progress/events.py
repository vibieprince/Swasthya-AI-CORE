"""
TELEMETRY TYPES: Enumerates system-wide milestone constants for consistent execution tracking.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any

logger = logging.getLogger(__name__)

class SystemEvents:
    PIPELINE_STARTED = "pipeline_started"
    DATA_FETCHED = "data_fetched"
    PIPELINE_COMPLETED = "pipeline_completed"
