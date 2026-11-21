# Summer-Rise

**AI-powered YouTube video summariser with multi-tier caching, interactive revision quizzes, and clickable timestamps.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-summer--rise.techwithap.site-2ea44f?style=flat-square)](https://summer-rise.techwithap.site)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-L2%20Persistence-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-L1%20Cache-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io/)
[![Gemini API](https://img.shields.io/badge/Google-Gemini%20API-8E75B2?style=flat-square&logo=googlegemini&logoColor=white)](https://ai.google.dev/)

---

## Overview

Summer-Rise converts long-form YouTube videos into structured study material in seconds. Built on a 3-tier backend architecture combining **FastAPI**, **Redis**, and **PostgreSQL**, it pairs the **Google Gemini API** with aggressive caching and atomic rate limiting to keep latency low and prevent redundant LLM calls on repeat requests.

**Live Application:** [summer-rise.techwithap.site](https://summer-rise.techwithap.site)

---

## Key Features

- **Structured LLM Summaries:** Distils video transcripts into organised, easy-to-scan notes using the Gemini API.
- **Transcript Windowing:** Splits long transcripts into manageable chunks so extended lectures and podcasts are processed cleanly without losing context.
- **Interactive Revision Quizzes:** Generates topic-focused quizzes from video content to reinforce active recall.
- **Clickable Video Timestamps:** Links key takeaways directly to their exact moments in the source YouTube video.
- **Multi-Tier Caching (L1 + L2):** Serves repeat lookups from Redis (L1) first, falls back to PostgreSQL (L2) for persistent history, and invokes the Gemini API only on a cache miss.
- **Atomic Rate Limiting:** Protects backend resources and LLM quota using `slowapi` backed by Redis.
- **Revision History:** Persists processed video summaries and revision metadata for quick retrieval.

---

## Architecture

Summer-Rise follows a 3-tier request lifecycle designed to minimise LLM API spend and response latency:

```text
Client (Static Frontend served by FastAPI)
   │
   ▼
FastAPI Backend + slowapi (Atomic Rate Limiting)
   │
   ├── 1. Check L1 Cache ────────► Redis (Sub-millisecond cache hit)
   │        │ (miss)
   ├── 2. Check L2 Storage ──────► PostgreSQL via SQLAlchemy (Persistent lookup)
   │        │ (miss)
   └── 3. Process Video ─────────► Transcript Windowing ──► Gemini API
                                                                │
                                        Populate L1 + L2 ◄──────┘
```

- **FastAPI** handles API routing, transcript windowing, Gemini orchestration, and static frontend asset delivery from a single service.
- **Redis** acts as both the high-speed L1 cache for hot video summaries and the state backend for atomic rate limiting.
- **PostgreSQL** (via SQLAlchemy) provides durable L2 storage for summaries, quiz payloads, and revision history.

---

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Backend Framework** | Python, FastAPI |
| **AI / LLM** | Google Gemini API |
| **L1 Caching** | Redis |
| **L2 Persistence & ORM** | PostgreSQL, SQLAlchemy |
| **Rate Limiting** | `slowapi` (Redis-backed) |
| **Frontend** | Static web assets served via FastAPI |
| **Deployment & Server** | Render, Gunicorn, Uvicorn workers |

---

## API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/summarize` | Accepts a YouTube video URL, checks L1/L2 caches, processes the windowed transcript via Gemini on a cache miss, and returns the structured summary, clickable timestamps, and revision quiz. |
| `GET` | `/api/history` | Returns previously generated summaries and revision metadata stored in PostgreSQL. |

Interactive OpenAPI documentation is available locally at `/docs` (Swagger UI) and `/redoc` when running the server.

---

## Local Setup

### Prerequisites

- Python 3.10+
- PostgreSQL instance (local or hosted)
- Redis instance (local or hosted)
- A Google Gemini API key

### 1. Clone the Repository

```bash
git clone [https://github.com/its-ap0503/YouTube-Video-Summariser.git](https://github.com/its-ap0503/YouTube-Video-Summariser.git)
cd YouTube-Video-Summariser
```

### 2. Create a Virtual Environment and Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root with your credentials:

```env
GEMINI_API_KEY=your_gemini_api_key
DATABASE_URL=postgresql://user:password@localhost:5432/summer_rise
REDIS_URL=redis://localhost:6379/0
```

### 4. Run the Application

**Development (with auto-reload):**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Production (Gunicorn + Uvicorn workers, matching Render setup):**

```bash
gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Open `http://localhost:8000` in your browser.

---

## Deployment

The production instance runs on **Render** behind Gunicorn with Uvicorn workers, serving both the FastAPI endpoints and the static frontend assets under the custom domain [summer-rise.techwithap.site](https://summer-rise.techwithap.site).

---

## Author

**Alok Pandey**  
GitHub: [@its-ap0503](https://github.com/its-ap0503)  
Live Project: [summer-rise.techwithap.site](https://summer-rise.techwithap.site)