"""
APPARATUS: Profiling tools used to log transaction durations and capture system bottlenecks.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any
import time

logger = logging.getLogger(__name__)

class Profiler:
    def __init__(self):
        self.start_time = time.time()

    def log_duration(self, operation_name: str) -> None:
        duration = time.time() - self.start_time
        logger.info(f"Operation {operation_name} took {duration:.2f}s")
