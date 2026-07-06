# SWASTHYA AI CORE - Single Container Dockerfile
# Includes FastAPI and Playwright browser binaries for internal background discovery

FROM python:3.10-slim-bookworm

# Prevent Python from writing pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install system dependencies required for Playwright and lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition
COPY requirements.txt .

# Install all dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binaries (chromium only)
RUN playwright install chromium --with-deps && \
    rm -rf /var/lib/apt/lists/*

# Copy application source
COPY pyproject.toml .
COPY src/ ./src/

# Install the package without reinstalling dependencies
RUN pip install . --no-deps

# Create a non-root user for security
RUN useradd -m appuser && chown -R appuser /app /ms-playwright
USER appuser

# Expose API port (Render overrides this with PORT env var, but 8000 is default)
EXPOSE 8000

# Health check using Python's built-in urllib
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", 8000)}/health')" || exit 1

# Start Uvicorn via shell to properly expand PORT variable
CMD ["sh", "-c", "python -m uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
