# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Layout

The main application lives under `car-recsys-system/`. The data crawler is a standalone Python package at `crawler/` (driven from `Carscrawling_raw.ipynb` for Colab). Datasets (CSV files) are in `datasets/`.

```
crawler/              # Optimized cars.com scraper (httpx + Selenium hybrid)
├── settings.py       # Selectors, URL templates, runtime config
├── parsers.py        # HTML → dict (lxml + shared helpers)
├── driver.py         # WebDriver + thread-safe DriverPool
├── fetcher.py        # httpx-first with Selenium fallback, retries, cache
├── pipeline.py       # discover_listing_urls / scrape_listings
└── __main__.py       # CLI: python -m crawler discover|scrape

car-recsys-system/
├── backend/          # FastAPI Python server
├── frontend/         # Vite + React (TypeScript)
├── etl/              # Loaders that move CSVs into PostgreSQL
├── database/init/    # SQL schema and seed scripts
├── docker-compose.yml
├── setup.sh          # Full environment bootstrap
└── load_complete_database.py
```

## Running the Stack

**First-time setup (starts all Docker services and loads data):**
```bash
cd car-recsys-system
chmod +x setup.sh && ./setup.sh
```

**Day-to-day: start infrastructure only:**
```bash
cd car-recsys-system
docker-compose up -d postgres postgrest bytebase qdrant redis
```

**Backend (dev, hot-reload):**
```bash
cd car-recsys-system/backend
uvicorn app.main:app --reload   # http://localhost:8000
# Swagger docs: http://localhost:8000/docs
```

**Frontend (dev, hot-reload):**
```bash
cd car-recsys-system/frontend
npm run dev                     # http://localhost:3000
```

**Populate vector embeddings (required for chatbot):**
```bash
cd car-recsys-system/backend
python scripts/ingest_chatbot_data.py --limit 100
```

**Reset database to clean state:**
```bash
cd car-recsys-system && ./reset_database.sh
```

**Crawl fresh data from cars.com (optimized pipeline):**
```bash
pip install -r crawler/requirements.txt
python -m crawler discover --from 1 --to 10
python -m crawler scrape   --from 1 --to 10 --http-workers 16
```
Output JSON lands in `raw_data/<page>/<idx>.json`. The pipeline is resumable —
re-running skips already-fetched HTML and already-written JSON. See
[crawler/README.md](crawler/README.md) for tuning.

**Check database health:**
```bash
cd car-recsys-system && python3 check_db_status.py
```

## Environment Variables

Create `car-recsys-system/backend/.env`:
```
OPENAI_API_KEY=...
DATABASE_URL=postgresql://admin:admin123@localhost:5432/car_recsys
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=car_chatbot_vectors
REDIS_URL=redis://localhost:6379
SECRET_KEY=your-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
```

Default DB credentials: `admin` / `admin123`, database `car_recsys`.

## Service Ports

| Service     | Port |
|-------------|------|
| Frontend    | 3000 |
| Backend API | 8000 |
| PostgreSQL  | 5432 |
| PostgREST   | 3001 |
| Bytebase    | 8080 |
| Qdrant      | 6333 |
| Redis       | 6379 |

## Architecture Overview

### Data Flow

Raw CSV data (7 files, ~720K rows) → `load_complete_database.py` → PostgreSQL 3-layer schema:
- **RAW** schema: verbatim loaded tables (used_vehicles, new_vehicles, sellers, reviews_ratings, vehicle_features, vehicle_images, seller_vehicle_relationships)
- **SILVER** schema: cleaned and normalized views/tables
- **GOLD** schema: application tables — users, interactions, favorites, searches, chat_conversations, chat_messages, plus materialized views `vehicles_with_ratings` and `popular_vehicles`

### Backend (FastAPI)

Entry: `backend/app/main.py`. Configuration: `app/core/config.py` (Pydantic settings). Database session: `app/core/database.py` (SQLAlchemy 2.0 async).

API routes under `app/api/v1/`:
- `auth` — JWT-based register/login (HS256, bcrypt passwords)
- `search` — vehicle search with filters
- `listings` — vehicle detail pages with images
- `reco` — recommendation engine results
- `chat` — AI chatbot endpoint
- `feedback` — favorites and ratings
- `reviews` — user-submitted reviews
- `interactions` — behavior tracking (view, click, compare, save, contact)

### Recommendation Engine

`app/services/recommendation_engine.py` implements a hybrid approach:
- **Authenticated users**: item-based collaborative filtering (cosine similarity on user-item matrix) blended with Qdrant vector similarity search
- **Guests**: popularity-based fallback (materialized view `popular_vehicles`)
- Interaction weights: view=1, click=2, compare=3, save/favorite=4, contact/inquiry=8; time-decayed with λ=0.1

### Chatbot

LangChain + OpenAI `gpt-4o-mini` with RAG:
1. User message → `text-embedding-3-large` (3072D) embedding
2. Qdrant semantic search → relevant vehicle context
3. GPT-4o-mini generates response with inline vehicle card references
4. Conversation history persisted to PostgreSQL (`gold.chat_conversations`, `gold.chat_messages`)

Frontend exposes chat as a floating popup (`ChatPopup.tsx`, always visible) and a full-screen page at `/chat` (`ChatPage.tsx`).

### Frontend (Vite + React)

Migrated from Next.js App Router to **Vite + React Router v6**. State management via Zustand (with persistence). API calls via Axios wrapper in `src/lib/api.ts`. UI components from shadcn/ui (Radix UI primitives + Tailwind CSS).

Pages: Home, Search, Vehicle Details, Compare, Sell, Chat, Login, Favorites.

### Database Migrations

Use Bytebase UI at `localhost:8080` for schema migrations in development. Bytebase connects via the `bytebase_admin` / `bytebase123` credentials (not the `admin` app user). SQL init scripts in `database/init/` run in numeric order (01 → 04) during first-time setup.

## Useful Maintenance Commands

```bash
# View running containers
docker-compose ps

# Tail logs for a specific service
docker-compose logs -f backend
docker-compose logs -f postgres

# Direct psql access
docker-compose exec postgres psql -U admin -d car_recsys

# PostgREST quick queries (no SQL needed)
curl "http://localhost:3001/used_vehicles?brand=eq.Toyota&limit=5"
curl "http://localhost:3001/used_vehicles?select=vehicle_id,title,price&limit=5"

# Backup / restore
docker-compose exec postgres pg_dump -U admin car_recsys > backup.sql
docker-compose exec -T postgres psql -U admin -d car_recsys < backup.sql

# Disk usage of Docker volumes
docker system df -v
```

## Common Issues and Debugging

### Port 5432 already in use
Another local PostgreSQL instance is running. Either stop it (`sudo systemctl stop postgresql`) or remap the port in `docker-compose.yml` (`"5433:5432"`).

### "Connection refused" on backend start
PostgreSQL takes ~15–20 s to be ready. Confirm it is accepting connections before starting the backend:
```bash
docker-compose logs postgres | grep "ready to accept connections"
# If missing, restart: docker-compose restart postgres
```

### Chatbot returns no results / empty recommendations
1. Check Qdrant has vectors: `curl http://localhost:6333/collections/car_chatbot_vectors`
2. If `vectors_count` is 0, run the ingest script: `cd car-recsys-system/backend && python scripts/ingest_chatbot_data.py --limit 100`
3. Verify `OPENAI_API_KEY` is set in `.env` — the ingest and chat endpoints both fail silently without it.

### Chat endpoint 500 error
```bash
docker-compose logs backend | tail -50
```
Most common causes: missing `OPENAI_API_KEY`, Qdrant not running, or `langchain` version mismatch. Check `requirements.txt` versions match the installed environment.

### Recommendations always return popular vehicles (no personalization)
User must be authenticated (JWT token in `Authorization: Bearer <token>` header). Guest sessions always fall back to `popular_vehicles` materialized view by design.

### Materialized views stale (ratings/popularity out of date)
```sql
REFRESH MATERIALIZED VIEW gold.vehicles_with_ratings;
REFRESH MATERIALIZED VIEW gold.popular_vehicles;
```

### Frontend API calls failing (CORS / 404)
The Vite dev server proxies `/api` to `http://localhost:8000` (configured in `vite.config.ts`). If you change the backend port, update the proxy target there.

### Data load fails partway through
Run `./reset_database.sh` to wipe the RAW schema and reload from scratch. The loader is idempotent after a full reset.

### Out of disk space during setup
The 7 CSV files total ~500 MB; Docker volumes add another ~2–3 GB. Run `docker system prune -a --volumes` to reclaim space (destroys all stopped containers and unused volumes — use with care).

## Skills Reference

This project benefits from the following Claude Code skill areas:

| Area | Skill to invoke |
|------|----------------|
| Backend API (FastAPI/Python) | `superpowers:systematic-debugging` for tracing errors |
| Frontend (React/TypeScript) | `superpowers:test-driven-development` |
| Data pipeline / ETL | `data:authoring-dags`, `data:profiling-tables` |
| Data model design | `data:warehouse-init` |
| Crawling / ingestion | `data:creating-openlineage-extractors` |
| Code review | `superpowers:requesting-code-review` |
