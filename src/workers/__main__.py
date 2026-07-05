"""
SWASTHYA AI CORE — Discovery Worker Module Entry Point.

Allows the worker to be launched as:

    python -m src.workers.discovery_worker

This is the recommended production invocation method because it:
1. Sets up the Python path correctly.
2. Works consistently on all platforms (Windows, Linux, macOS).
3. Avoids the -c "import asyncio; ..." one-liner which is fragile.
"""

import asyncio

from src.workers.discovery_worker import run_worker

asyncio.run(run_worker())
