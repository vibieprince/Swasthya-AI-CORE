<div align="center">
  <h1>🏥 SWASTHYA AI CORE</h1>
  <p><strong>A Production-Grade Healthcare Intelligence Engine for MedPath</strong></p>
  <p>
    <a href="https://swasthya-ai-core.onrender.com/health">
      <img src="https://img.shields.io/badge/Status-Healthy-brightgreen.svg" alt="Status">
    </a>
    <img src="https://img.shields.io/badge/Version-v1.0.2-blue.svg" alt="Version">
    <img src="https://img.shields.io/badge/Python-3.10+-yellow.svg" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-Production-009688.svg" alt="FastAPI">
  </p>
</div>

<hr>

## 🚀 Overview

**SWASTHYA AI CORE** is the high-performance, asynchronous orchestration backend powering the [MedPath application](https://github.com/Amankumar140/MedPath). Designed for scale and precision, it abstracts complex healthcare intelligence and dynamic hospital discovery workflows into reliable REST APIs. 

Deployed seamlessly on Render, SWASTHYA AI CORE utilizes a pure **In-Memory Asynchronous Job Scheduler**, meaning it runs perfectly as a single, unified web service container without requiring separate worker nodes or external message brokers like RabbitMQ.

**Live API Base URL:** `https://swasthya-ai-core.onrender.com`

---

## 🏗 Core Capabilities

1. **Context Intelligence Pipeline (`POST /api/context/analyze`)**
   - Natural language understanding for clinical intents.
   - Multi-turn conversational parsing and context extraction.
   - Intelligent follow-up generation for incomplete medical context.
   
2. **Discovery Intelligence Pipeline (`POST /api/discovery/search`)**
   - Immediate asynchronous task queuing (under 200ms response).
   - Real-time deep web scraping using optimized **Playwright Browser Pooling**.
   - Geographic boundary resolution (Google Maps integration).
   - Medical specialty parsing.

3. **Ranking & Explanation Engine**
   - Deterministic and multi-criteria explainable recommendations.
   - Automated quality scoring (NABH accreditation, ratings).
   - LLM-powered context summaries (Gemini Primary, Mistral Failover).

4. **Progress Polling (`GET /api/tasks/{task_id}/progress`)**
   - Real-time Redis-backed pipeline progress (Queued → Planning → Searching → Research → Ranking → Explanation → Completed).

---

## 🛠 Technology Stack

- **Framework:** FastAPI & Pydantic V2
- **Language:** Python 3.10+
- **Task Execution:** `asyncio` (Internal AsyncIOJobExecutor)
- **State Management:** Redis (Transient task tracking)
- **Scraping Engine:** Playwright (Chromium) & BeautifulSoup4
- **LLM Integrations:** Direct HTTPX integrations (No bloated SDKs)

---

## 🚦 Getting Started (Local Development)

The backend is built for minimal configuration and immediate deployment.

### 1. Environment Configuration

Clone the repository and set up the environment variables.

```bash
cp .env.example .env
```
*Note: The application uses strict Pydantic Settings and will **REFUSE TO START** if required keys (Gemini, Google Maps, Redis) are missing or set to placeholders.*

### 2. Run Locally via Docker Compose

```bash
docker-compose up -d --build
```
This commands boots:
1. **The Core API** (`http://localhost:8000`)
2. **Redis** (`redis://localhost:6379/0`)

### 3. Local Manual Installation

If you prefer running without Docker:

```bash
python -m venv venv
source venv/bin/activate  # Or .\venv\Scripts\activate on Windows
pip install --upgrade pip
pip install .
playwright install chromium --with-deps
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

---

## 🌐 Deployment (Render)

This repository is optimized for **Render Free** deployment as a single Web Service. 

1. **Dockerized Environment:** The unified `Dockerfile` automatically builds the FastAPI environment alongside Chromium.
2. **Health Checks:** Native `/health` endpoint configured for Render deployment probes.
3. **Port Binding:** Automatically respects Render's dynamically injected `$PORT` variable via shell execution wrapper.
4. **Build System:** Relies on modern `setuptools.build_meta` standard compliant packaging.

**Render Service Settings:**
- **Environment:** Docker
- **Build Command:** *(None needed, Render detects Dockerfile)*
- **Start Command:** *(None needed, defined in Dockerfile)*
- **Environment Variables:** Provide API keys and external Redis URL.

---

## 📚 API Endpoints Summary

### Context API
* **`POST /api/context/analyze`**
  Analyzes user input and clinical history to determine if actionable discovery can begin, or if the system requires a follow-up interaction.

### Discovery API
* **`POST /api/discovery/search`**
  Initiates the heavy async hospital discovery pipeline. Returns a `task_id` instantaneously.
  
### Task Progress API
* **`GET /api/tasks/{task_id}/progress`**
  Poll the Redis state store using the `task_id`. Returns the current pipeline stage and percentage until the payload delivers `status: "completed"`.

### System
* **`GET /health`**
  Liveness probe for monitoring platforms.

*(Refer to the `docs.html` file in the repository root for the full Client API Handbook and interaction diagrams).*

---

## 🔒 Design Philosophy
* **Statelessness:** Absolutely no user chat history or business data is persisted on disk or Postgres. Redis is utilized entirely as a short-term pipeline transit store (TTL 6 Hours).
* **Fault-Tolerant:** Automatic LLM timeouts, safe exception catching in async backgrounds, and direct degradation handling.
* **Scale-Ready:** Easily extract the `JobExecutor` abstraction to external brokers like RabbitMQ or Celery when scaling beyond a single instance is required.
