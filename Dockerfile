# SWASTHYA AI CORE Dockerfile
# Optimized for Playwright/Selenium Python environments

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
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binaries
RUN playwright install chromium --with-deps

# Copy application source
COPY pyproject.toml .
COPY src/ ./src/
RUN pip install -e .

# Create a non-root user for security
RUN useradd -m appuser && chown -R appuser /app /ms-playwright
USER appuser

# Expose API port
EXPOSE 8000

# Start Uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
