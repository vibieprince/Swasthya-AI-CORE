"""
DISTRIBUTED CORE: Configures Celery app settings, links Redis, and registers tasks.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any

logger = logging.getLogger(__name__)

celery_app = None
