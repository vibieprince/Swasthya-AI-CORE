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

**Live API Base URL:** [https://swasthya-ai-core.onrender.com](https://swasthya-ai-core.onrender.com)

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
---

# ⚙️ End-to-End Request Lifecycle

Every request entering **SWASTHYA AI CORE** follows a deterministic, production-grade orchestration pipeline designed for low latency, resilience, and conversational continuity.

```text
                        User Query
                            │
                            ▼
               Context Intelligence API
        (Language + Intent Classification)
                            │
                            ▼
               Clinical Entity Extraction
      (Symptoms • Urgency • Location • Specialty)
                            │
                            ▼
              Deterministic Context Validation
                            │
          ┌─────────────────┴─────────────────┐
          │                                   │
          ▼                                   ▼
 Missing Information                    Context Complete
          │                                   │
          ▼                                   ▼
 AI Follow-up Question              Discovery API Triggered
          │                                   │
          ▼                                   ▼
 Redis Conversation Session         Async Discovery Executor
          │                                   │
          └─────────────────┬─────────────────┘
                            ▼
                Multi-source Research Pipeline
                            │
      ┌──────────────┬───────────────┬───────────────┐
      │              │               │               │
      ▼              ▼               ▼               ▼
 Google Maps     Tavily Search   Playwright      Metadata
                                  Scraping     Normalization
                            │
                            ▼
                 Hospital Ranking Engine
                            │
                            ▼
                 AI Recommendation Generator
                            │
                            ▼
                  Redis Progress Tracking
                            │
                            ▼
                 Client Progress Polling
                            │
                            ▼
              Ranked Hospital Recommendations
```

---

# 🧠 Multi-Stage AI Pipeline

Instead of relying on a single LLM call, SWASTHYA AI CORE decomposes reasoning into specialized AI stages.

| Pipeline | Responsibility |
|-----------|----------------|
| **Pass 1** | Language detection, greeting recognition and healthcare intent classification |
| **Pass 2** | Clinical entity extraction (symptoms, urgency, location, demographics, specialty) |
| **Pass 3** | Natural-language follow-up generation for missing mandatory information |
| **Discovery** | Hospital research, evidence aggregation and data normalization |
| **Ranking** | Multi-factor deterministic hospital scoring |
| **Explainer** | Human-friendly recommendation summaries and reasoning |

This modular design significantly improves accuracy while reducing hallucinations, latency and token consumption.

---

# 💬 Multi-turn Conversation Intelligence

Unlike traditional stateless REST APIs, SWASTHYA AI CORE maintains conversational continuity using lightweight Redis-backed session memory.

### Supported Conversation Flow

```text
User:
Hello

↓

Assistant:
How can I help you today regarding your health?

↓

User:
I have severe chest pain.

↓

Assistant:
May I know your current location?

↓

User:
Sector 18 Noida

↓

Assistant:
Context complete.

↓

Discovery Pipeline Starts
```

### Features

- Context accumulation across multiple turns
- Session versioning
- Deterministic context validation
- Automatic follow-up generation
- Sliding Redis session expiration
- Zero persistent storage of patient conversations

---

# ⚡ Performance Optimizations

The backend was engineered to reduce latency, infrastructure cost and LLM usage without sacrificing accuracy.

## Intelligent Pipeline Short-Circuiting

- Greeting requests bypass unnecessary clinical extraction.
- Complete contexts skip follow-up generation.
- Deterministic validation avoids redundant LLM calls.

---

## Prompt Compression

Prompt templates were redesigned to minimize input and output tokens.

Benefits include:

- Faster Time-To-First-Token (TTFT)
- Reduced inference cost
- Lower response latency
- Smaller context windows

---

## Delta Context Extraction

Instead of repeatedly sending the complete clinical JSON to the LLM, continuation turns extract only newly mentioned information.

Example:

Initial Context

```text
Symptoms:
• Severe Chest Pain
```

Follow-up Message

```text
Sector 18 Noida
```

LLM extracts only

```json
{
    "patient_location": {
        "raw_location": "Sector 18 Noida"
    }
}
```

Python then deterministically merges this delta into the existing context.

Benefits:

- Smaller prompts
- Lower token consumption
- No accidental loss of previously confirmed information

---

## Browser Pooling

Hospital discovery uses Playwright browser pooling instead of launching Chromium for every request.

Benefits:

- Faster scraping
- Lower memory usage
- Improved throughput
- Reduced cold-start latency

---

# 🛡 Reliability & Fault Tolerance

Healthcare applications require graceful degradation rather than complete failure.

SWASTHYA AI CORE incorporates several resilience mechanisms.

## LLM Failover

```text
            Gemini Flash
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
    Successful       Failure / Rate Limit
        │                 │
        ▼                 ▼
    Response       Circuit Breaker Opens
                          │
                          ▼
                 Automatic Mistral Fallback
```

Implemented safeguards include:

- Automatic retries
- Exponential backoff
- Circuit breaker pattern
- Provider failover
- Structured telemetry logging

---

## Background Execution

Hospital discovery executes independently from incoming HTTP requests.

Advantages:

- Immediate API response
- Non-blocking architecture
- Concurrent request processing
- Safe failure isolation
- Automatic Redis progress updates

---

## Deterministic Validation

Critical business decisions are intentionally **not delegated entirely to an LLM.**

Python performs deterministic validation for:

- Mandatory symptoms
- Required location
- Context sufficiency
- Session lifecycle
- Conversation state transitions

LLMs are reserved only for natural language understanding.

---

# 🚧 Engineering Challenges Solved

During development, several production-scale engineering challenges were addressed.

- Multi-turn conversational state management
- Redis-backed session persistence
- Asynchronous discovery orchestration
- LLM provider failover
- Real-time progress tracking
- Browser pooling for Playwright
- Dynamic hospital research and normalization
- Token optimization through prompt engineering
- Deterministic validation alongside probabilistic AI
- Stateless cloud deployment on a single container
- Graceful degradation during external API failures

---

# 📊 System Characteristics

| Property | Implementation |
|-----------|----------------|
| **Architecture** | Layered Clean Architecture |
| **API Style** | REST |
| **Concurrency** | AsyncIO |
| **Background Processing** | Internal Async Job Executor |
| **Conversation Memory** | Redis |
| **Progress Tracking** | Redis |
| **LLM Providers** | Gemini + Mistral |
| **Search Engine** | Google Maps + Tavily |
| **Scraping Engine** | Playwright + BeautifulSoup |
| **Fallback Strategy** | Circuit Breaker + Provider Failover |
| **Deployment** | Docker + Render |
| **Observability** | Structured Logging & Telemetry |

---

# 💡 Why SWASTHYA AI CORE?

SWASTHYA AI CORE is not simply a chatbot or CRUD backend.

It is a production-oriented AI orchestration platform that combines:

- 🧠 Conversational AI
- 🏥 Healthcare Intelligence
- ⚡ Asynchronous Background Processing
- 🌐 Deep Web Research & Scraping
- 📊 Explainable Hospital Ranking
- 🔄 Multi-turn Context Management
- 🛡 Fault-Tolerant AI Pipelines
- 🚀 Cloud-Native Deployment

The result is a modular, scalable and production-ready intelligence layer capable of powering healthcare applications requiring reliable clinical context understanding and intelligent hospital discovery.
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

*(Refer to the [docs.html](https://swasthya-ai-core.onrender.com/docs.html) file in the repository root for the full Client API Handbook and interaction diagrams).*

---

## 🔒 Design Philosophy
* **Statelessness:** Absolutely no user chat history or business data is persisted on disk or Postgres. Redis is utilized entirely as a short-term pipeline transit store (TTL 6 Hours).
* **Fault-Tolerant:** Automatic LLM timeouts, safe exception catching in async backgrounds, and direct degradation handling.
* **Scale-Ready:** Easily extract the `JobExecutor` abstraction to external brokers like RabbitMQ or Celery when scaling beyond a single instance is required.
