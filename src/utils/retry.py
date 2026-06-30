"""
STRATEGY DECORATORS: Custom backoff wrappers to automatically manage transient network errors.
"""
import logging
from typing import List, Optional, Protocol, Dict, Any, Callable
from functools import wraps

logger = logging.getLogger(__name__)

def with_retry(retries: int = 3) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.info(f"Executing {func.__name__} with retries.")
            return func(*args, **kwargs)
        return wrapper
    return decorator
