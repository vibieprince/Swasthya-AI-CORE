# SWASTHYA AI CORE

A Production-Grade Healthcare Intelligence Engine for the Indian market.

SWASTHYA AI CORE is an independent, stateless microservice that provides:
1. **Context Intelligence**: Natural language understanding, intent classification, and clinical extraction.
2. **Discovery Intelligence**: Multi-source hospital discovery and geographic resolution.
3. **Ranking Intelligence**: Explainable multi-criteria recommendations.

## Core Principles
- **Stateless**: No user, chat history, or business data is stored here. Redis is used strictly for transient task state with a TTL.
- **Async-First**: Heavy discovery tasks are offloaded to RabbitMQ workers.
- **Fail-Safe**: Direct HTTP integrations with LLM providers using strict Pydantic parsing and automatic provider failover (Gemini → Mistral).

## Architecture Stack
- Python 3.10+
- FastAPI & Pydantic V2
- HTTPX (Direct API calls, no SDKs)
- Redis asyncio
- aio-pika (RabbitMQ)
- Playwright & BeautifulSoup4

## Getting Started

1. **Environment Setup**
   ```bash
   cp .env.example .env
   # Edit .env with your actual API keys (Application will refuse to start if keys are missing)
   ```

2. **Run Services with Docker Compose**
   ```bash
   docker-compose up -d --build
   ```
   This will spin up:
   - FastAPI Server (`http://localhost:8000`)
   - 2x Worker Processes
   - Redis
   - RabbitMQ (`http://localhost:15672` for Management UI)

## API Endpoints

- `POST /api/context/analyze`: Extract structured context from a patient message.
- `POST /api/discovery/search`: Queue a background discovery task.
- `GET /api/tasks/{task_id}/progress`: Poll the progress of a discovery task.

## Development

Install locally:
```bash
python -m venv venv
source venv/bin/activate  # Or .\venv\Scripts\activate on Windows
pip install -e .
pip install -r requirements.txt
playwright install chromium
```
