# Chatbot v2 Sub-2 — Backend Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old hybrid-RAG chatbot with chatbot_2's agentic LangGraph at `POST /api/v1/chat` (in-memory sessions, Qdrant `car_vectorize` + AlloyDB gold.*), and add a weekly `embed_chatbot_vehicles` pipeline activity so the chatbot collection stays fresh.

**Architecture:** Move `generate_response.py` + `user_profile.py` into `backend/app/services/chatbot/` (deleting the 7 old files), convert profile persistence to an in-memory dict, rewrite `chat.py` to a single `{session_id,message}→{answer}` endpoint with global lazy-init + in-memory history, bump backend langchain 0.2→1.x, and add a parallel pipeline activity that re-ingests gold.vehicles→`car_vectorize`.

**Tech Stack:** FastAPI, LangChain 1.3.2 / langchain-core 1.4.0 / langgraph 1.2.2 / langchain-qdrant, OpenAI, Qdrant Cloud, AlloyDB (Postgres), Temporal (pipeline activity).

**Reference spec:** `docs/superpowers/specs/2026-06-07-chatbot-v2-sub2-backend-integration-design.md`

**Backend dir:** `/home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/backend`
**Crawler dir:** `/home/duc-nguyen16/car-recsys-consultant-chatbot/crawler`

**Verification reality:** This env can't `pip install`/run the backend or build images. Each code task is verified by `python -m py_compile` + grep here; the real `docker build`/deploy + live `POST /api/v1/chat` + pipeline run are USER-run (needs deps, Cloud Run, Qdrant/OpenAI keys, the VM). Verified facts:
- chatbot_2's `generate_response.py` already points at Qdrant `car_vectorize` (env `CHATBOT_QDRANT_COLLECTION`) + gold.* via `WAREHOUSE_DSN`/`DATABASE_URL` (Sub-1).
- `generate_response(llm, vector_store, history, user_input, session_id)` → `(answer, updated_history)`. `initialize_resources()` → `(llm, vector_store)`.
- `user_profile.py` persists via file JSON (`load_profile`/`save_profile`/`delete_profile`, `_path`, `PROFILE_DIR`). Graph calls those 3 functions; converting their bodies to a dict keeps the graph untouched.
- Backend: only the chatbot uses langchain (reco/search don't); `app/services/__init__.py` references chatbot in a docstring only. `chat.py` currently has `/message`, `/conversations`, `/conversation/{id}` GET+DELETE, `/health`, all on `gold.chat_*`.
- Pipeline: `MLWorkflow.run` runs `compute_item_similarity_activity` ∥ `embed_vehicles_activity` via `asyncio.gather`; `MLResult{similarity_items, similarity_pairs, embedded}`; `EmbedResult{embedded, skipped}`; worker registers activities in `pipeline_worker.py`; `Dockerfile.pipeline` installs `crawler/temporal_app/requirements.txt`; `pipeline/__init__.py` exports the pure fns.

---

## File Structure
**Backend (Cloud Run):**
- DELETE: `backend/app/services/chatbot/{core,retrieval,generation,memory,ingest,config}.py`
- Create: `backend/app/services/chatbot/generate_response.py` (from chatbot_2, unchanged)
- Create: `backend/app/services/chatbot/user_profile.py` (in-memory variant)
- Rewrite: `backend/app/services/chatbot/__init__.py` (export `initialize_resources`, `generate_response`)
- Rewrite: `backend/app/api/v1/chat.py` (single agentic endpoint)
- Modify: `backend/requirements.txt` (langchain bump + langgraph/langchain-qdrant)
- Modify: `backend/app/core/config.py` (add `CHATBOT_QDRANT_COLLECTION`)

**Pipeline (VM worker image):**
- Create: `crawler/temporal_app/pipeline/chatbot_embeddings.py` (shared ingest builder)
- Modify: `crawler/temporal_app/pipeline/__init__.py` (export it)
- Modify: `crawler/temporal_app/activities.py` (`embed_chatbot_vehicles_activity`)
- Modify: `crawler/temporal_app/workflows.py` (wire into `MLWorkflow`, extend `MLResult`)
- Modify: `crawler/temporal_app/pipeline_worker.py` (register the activity)
- Modify: `crawler/temporal_app/requirements.txt` (langchain-qdrant + text-splitters)

**Cleanup:** delete `chatbot_2/api_server.py`.

Order: backend first (Tasks 1–5), then pipeline (Tasks 6–9), then user deploy/verify (Task 10).

---

## Task 1: Move chatbot_2 graph files into the backend, delete old chatbot

**Files:** delete 6 old, copy 2 new.

- [ ] **Step 1: Delete the old chatbot modules**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git rm car-recsys-system/backend/app/services/chatbot/core.py \
       car-recsys-system/backend/app/services/chatbot/retrieval.py \
       car-recsys-system/backend/app/services/chatbot/generation.py \
       car-recsys-system/backend/app/services/chatbot/memory.py \
       car-recsys-system/backend/app/services/chatbot/ingest.py \
       car-recsys-system/backend/app/services/chatbot/config.py
```

- [ ] **Step 2: Copy the graph file in (unchanged — it's already Qdrant/gold-pointed)**
```bash
cp chatbot_2/generate_response.py car-recsys-system/backend/app/services/chatbot/generate_response.py
```

- [ ] **Step 3: Verify + commit**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
python -m py_compile car-recsys-system/backend/app/services/chatbot/generate_response.py && echo "graph OK"
ls car-recsys-system/backend/app/services/chatbot/
git add car-recsys-system/backend/app/services/chatbot/generate_response.py
git commit -m "feat(backend): drop old hybrid-RAG chatbot, add chatbot_2 agentic graph

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
Expected: `graph OK`; dir now has `generate_response.py` + `__init__.py` (old files gone).

---

## Task 2: In-memory user_profile

**Files:** Create `backend/app/services/chatbot/user_profile.py`

- [ ] **Step 1: Create the in-memory variant**

Copy chatbot_2's user_profile.py but replace the file-persistence section. Create
`backend/app/services/chatbot/user_profile.py` with the SAME models (`CoreSlots`,
`SoftPreferences`, `UserProfile`, `ProfileUpdate`, `merge_update`, `log_viewed`) and these
in-memory persist functions instead of the file ones:
```python
import threading
from typing import List, Optional

from pydantic import BaseModel, Field

# --- models (identical to chatbot_2) ---
class CoreSlots(BaseModel):
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    body_type: Optional[str] = None
    fuel_type: Optional[str] = None
    brand: Optional[str] = None
    condition: Optional[str] = None


class SoftPreferences(BaseModel):
    features: List[str] = Field(default_factory=list)
    vibe: Optional[str] = None


class UserProfile(BaseModel):
    core_slots: CoreSlots = Field(default_factory=CoreSlots)
    soft_preferences: SoftPreferences = Field(default_factory=SoftPreferences)
    viewed_models: List[str] = Field(default_factory=list)
    excluded_brands: List[str] = Field(default_factory=list)


class ProfileUpdate(BaseModel):
    budget_min: Optional[float] = Field(default=None, description="Minimum budget as a USD number.")
    budget_max: Optional[float] = Field(default=None, description="Maximum budget as a USD number.")
    body_type: Optional[str] = Field(default=None, description="Desired body or usage type, e.g. SUV, Sedan.")
    fuel_type: Optional[str] = Field(default=None, description="Desired fuel type, e.g. Gasoline, Hybrid, Electric.")
    brand: Optional[str] = Field(default=None, description="Preferred brand if any.")
    condition: Optional[str] = Field(default=None, description="New or Used.")
    add_features: List[str] = Field(default_factory=list, description="New desired features to remember.")
    vibe: Optional[str] = Field(default=None, description="Overall vibe the customer wants, e.g. luxurious, sporty.")
    exclude_brands: List[str] = Field(default_factory=list, description="Brands the customer wants to avoid.")
    interested_models: List[str] = Field(default_factory=list, description="Specific models the customer asks about.")


def merge_update(profile: UserProfile, update: ProfileUpdate) -> UserProfile:
    cs = profile.core_slots
    for field in ("budget_min", "budget_max", "body_type", "fuel_type", "brand", "condition"):
        value = getattr(update, field)
        if value is not None:
            setattr(cs, field, value)
    sp = profile.soft_preferences
    for feature in update.add_features:
        if feature and feature not in sp.features:
            sp.features.append(feature)
    if update.vibe:
        sp.vibe = update.vibe
    for brand in update.exclude_brands:
        if brand and brand not in profile.excluded_brands:
            profile.excluded_brands.append(brand)
    for model in update.interested_models:
        if model and model not in profile.viewed_models:
            profile.viewed_models.append(model)
    return profile


def log_viewed(profile: UserProfile, titles: List[str]) -> UserProfile:
    for title in titles:
        if title and title not in profile.viewed_models:
            profile.viewed_models.append(title)
    return profile


# --- in-memory persistence (was file JSON; Cloud Run fs is ephemeral) ---
_PROFILES: dict[str, UserProfile] = {}
_LOCK = threading.Lock()


def load_profile(session_id: str) -> UserProfile:
    with _LOCK:
        return _PROFILES.get(session_id) or UserProfile()


def save_profile(session_id: str, profile: UserProfile) -> None:
    with _LOCK:
        _PROFILES[session_id] = profile


def delete_profile(session_id: str) -> None:
    with _LOCK:
        _PROFILES.pop(session_id, None)
```

- [ ] **Step 2: Verify generate_response imports from this module (same-package)**

`generate_response.py` imports profile functions. Confirm the import path resolves within the
package. Run:
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
grep -nE "from .* import (load_profile|save_profile|delete_profile|UserProfile|ProfileUpdate|merge_update|log_viewed)|import user_profile|from user_profile|from chatbot_2.user_profile|from .user_profile" car-recsys-system/backend/app/services/chatbot/generate_response.py
```
If it imports `from chatbot_2.user_profile import ...` or `from user_profile import ...`, change those to `from .user_profile import ...` (relative, same package). Apply the fix if needed, then:
```bash
python -m py_compile car-recsys-system/backend/app/services/chatbot/user_profile.py && echo "profile OK"
```
Expected: `profile OK`; the graph imports profile symbols via `.user_profile`.

- [ ] **Step 3: Commit**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/backend/app/services/chatbot/user_profile.py car-recsys-system/backend/app/services/chatbot/generate_response.py
git commit -m "feat(backend): in-memory user_profile for the agentic chatbot (Cloud Run ephemeral fs)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: chatbot package `__init__.py`

**Files:** Rewrite `backend/app/services/chatbot/__init__.py`

- [ ] **Step 1: Replace __init__.py**

Replace `backend/app/services/chatbot/__init__.py` with a thin re-export (no eager heavy import at package import time — import lazily inside functions in chat.py; here just expose names):
```python
"""Agentic car-shopping chatbot (chatbot_2 LangGraph), integrated into the backend.

Exposes:
    initialize_resources() -> (llm, vector_store)   # build once, cache in the route
    generate_response(llm, vector_store, history, user_input, session_id)
        -> (answer, updated_history)

Vector store: Qdrant `car_vectorize` (env CHATBOT_QDRANT_COLLECTION).
SQL: gold.* on AlloyDB (env WAREHOUSE_DSN / DATABASE_URL).
"""
from .generate_response import generate_response, initialize_resources

__all__ = ["generate_response", "initialize_resources"]
```

- [ ] **Step 2: Verify + commit**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
python -m py_compile car-recsys-system/backend/app/services/chatbot/__init__.py && echo "init OK"
git add car-recsys-system/backend/app/services/chatbot/__init__.py
git commit -m "feat(backend): chatbot package exposes initialize_resources + generate_response

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
Expected: `init OK`.

---

## Task 4: Rewrite chat.py to the single agentic endpoint

**Files:** Rewrite `backend/app/api/v1/chat.py`

- [ ] **Step 1: Replace the whole file**

Replace ALL of `backend/app/api/v1/chat.py` with:
```python
"""Chat API — agentic car-shopping assistant (chatbot_2 LangGraph).

POST /api/v1/chat  {session_id?, message, reset?} -> {session_id, answer}
In-memory per-session history + profile (Cloud Run runs max-instances=1, so a
session stays on one instance). The old gold.chat_* conversation endpoints are
removed — the agentic graph owns session state in memory.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Optional

import anyio
from fastapi import APIRouter, HTTPException, status
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

# Global resources (LLM + Qdrant vector store), built once on first use.
_llm = None
_vector_store = None
_init_lock = threading.Lock()

# In-memory chat history per session_id.
_histories: dict[str, list[BaseMessage]] = {}
_hist_lock = threading.Lock()


def _resources():
    global _llm, _vector_store
    if _llm is None or _vector_store is None:
        with _init_lock:
            if _llm is None or _vector_store is None:
                from app.services.chatbot import initialize_resources
                _llm, _vector_store = initialize_resources()
    return _llm, _vector_store


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=5000)
    reset: bool = False


class ChatResponse(BaseModel):
    session_id: str
    answer: str


@router.post("", response_model=ChatResponse)
@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Run one consultation turn through the agentic graph."""
    try:
        llm, vector_store = _resources()
    except Exception as exc:  # noqa: BLE001 — missing OPENAI_API_KEY / Qdrant unreachable
        logger.error("chatbot init failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Chatbot unavailable: {exc}")

    session_id = req.session_id or str(uuid.uuid4())

    if req.reset:
        with _hist_lock:
            _histories.pop(session_id, None)
        from app.services.chatbot.user_profile import delete_profile
        delete_profile(session_id)

    with _hist_lock:
        history = list(_histories.get(session_id, []))

    try:
        from app.services.chatbot import generate_response
        answer, updated_history = await anyio.to_thread.run_sync(
            generate_response, llm, vector_store, history, req.message, session_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("chat generate_response failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to process message: {exc}")

    with _hist_lock:
        _histories[session_id] = updated_history

    return ChatResponse(session_id=session_id, answer=answer)


@router.get("/health")
async def chat_health():
    """Confirms the chatbot resources can initialize."""
    try:
        _resources()
        return {"status": "healthy", "chatbot": "initialized"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "error": str(exc)}
```
Note: the router is mounted at prefix `/api/v1/chat` (in main.py), so `@router.post("")` →
`POST /api/v1/chat`. The old `/message`, `/conversations`, `/conversation/{id}`, DELETE are
intentionally gone.

- [ ] **Step 2: Verify + commit**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/backend
python -m py_compile app/api/v1/chat.py && echo "chat OK"
grep -nE "POST|/conversations|/message|generate_response|_resources|ChatRequest|ChatResponse" app/api/v1/chat.py | head
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/backend/app/api/v1/chat.py
git commit -m "feat(backend): rewrite chat.py to single agentic POST /api/v1/chat (in-memory sessions)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
Expected: `chat OK`; grep shows the new ChatRequest/ChatResponse + `_resources` + no `/conversations`/`/message`.

---

## Task 5: Backend deps + config

**Files:** Modify `backend/requirements.txt`, `backend/app/core/config.py`

- [ ] **Step 1: Bump langchain + add langgraph/qdrant in backend requirements**

In `backend/requirements.txt`, the current block is:
```
qdrant-client==1.7.0
# LangChain & OpenAI (for chatbot)
langchain==0.2.16
langchain-openai==0.1.23
langchain-core==0.2.38
openai==1.42.0
tiktoken==0.7.0
```
Replace it with (match chatbot_2's working set; unpin langchain-qdrant as chatbot_2 does):
```
qdrant-client==1.12.1
# LangChain / LangGraph (agentic chatbot — chatbot_2 graph)
langchain==1.3.2
langchain-core==1.4.0
langchain-openai==1.2.2
langchain-text-splitters==1.1.2
langgraph==1.2.2
langchain-qdrant
openai==2.40.0
tiktoken==0.7.0
```

- [ ] **Step 2: Add CHATBOT_QDRANT_COLLECTION to config.py**

In `backend/app/core/config.py`, find the Vector Database block:
```python
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "car_chatbot_vectors")
```
Add the chatbot collection right after it:
```python
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "car_chatbot_vectors")
    CHATBOT_QDRANT_COLLECTION: str = os.getenv("CHATBOT_QDRANT_COLLECTION", "car_vectorize")
```
(The graph reads `CHATBOT_QDRANT_COLLECTION` from env directly via os.getenv in
generate_response.py; this Settings field documents it + ensures the env is recognized.)

- [ ] **Step 3: Verify + commit**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/backend
python -m py_compile app/core/config.py && echo "config OK"
grep -nE "langchain==1.3.2|langgraph==1.2.2|langchain-qdrant|CHATBOT_QDRANT_COLLECTION" requirements.txt app/core/config.py
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/backend/requirements.txt car-recsys-system/backend/app/core/config.py
git commit -m "chore(backend): bump langchain 0.2->1.3.2 + langgraph + langchain-qdrant; add CHATBOT_QDRANT_COLLECTION

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
Expected: `config OK`; grep shows the bumped deps + the new config field.

---

## Task 6: Shared chatbot-embed builder in the pipeline

**Files:** Create `crawler/temporal_app/pipeline/chatbot_embeddings.py`, modify `pipeline/__init__.py`, `crawler/temporal_app/requirements.txt`

- [ ] **Step 1: Create the shared ingest function**

Create `crawler/temporal_app/pipeline/chatbot_embeddings.py` — the same logic as
`chatbot_2/ingest_database.py` but as an importable function (no `load_dotenv`, params instead
of module globals), so both the standalone script and the Temporal activity can call it:
```python
"""Re-ingest gold.vehicles (+ features) into the chatbot's Qdrant collection
(`car_vectorize`) as chatbot_2-style chunked documents. Pure function called by
the embed_chatbot_vehicles activity and (optionally) the standalone script.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional
from uuid import uuid4


def embed_chatbot_vehicles(
    warehouse_dsn: str,
    qdrant_url: str,
    openai_api_key: str,
    collection: str = "car_vectorize",
    qdrant_api_key: Optional[str] = None,
    embedding_model: str = "text-embedding-3-large",
    embedding_dim: int = 3072,
    chunk_size: int = 250,
    chunk_overlap: int = 30,
    batch_size: int = 128,
) -> dict[str, int]:
    from sqlalchemy import create_engine, text
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_openai import OpenAIEmbeddings
    from langchain_qdrant import QdrantVectorStore
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    engine = create_engine(warehouse_dsn)
    with engine.connect() as con:
        vehicles = con.execute(text("""
            SELECT vin, new_used AS status, title, brand, car_name, car_model,
                   price, monthly_payment, mileage, mpg,
                   exterior_color, interior_color, drivetrain, fuel_type,
                   transmission, engine, vehicle_url
            FROM gold.vehicles WHERE title IS NOT NULL
        """)).mappings().all()
        feats = con.execute(text("""
            SELECT vehicle_id, feature_category, feature_name
            FROM gold.vehicle_features WHERE feature_name IS NOT NULL
        """)).all()
    by_vin: dict = defaultdict(lambda: defaultdict(list))
    for vid, cat, name in feats:
        if name not in by_vin[vid][cat or "Other"]:
            by_vin[vid][cat or "Other"].append(name)

    docs = []
    for v in vehicles:
        d = dict(v)
        feat = {k: list(vs) for k, vs in by_vin.get(d["vin"], {}).items()}
        page_content = (
            f"status: {d.get('status','')}. title: {d.get('title','')}"
            f". brand: {d.get('brand','')}. interior_color: {d.get('interior_color','')}"
            f". exterior_color: {d.get('exterior_color','')}. drivetrain: {d.get('drivetrain','')}"
            f". fuel_type: {d.get('fuel_type','')}. transmission: {d.get('transmission','')}"
            f". engine: {d.get('engine','')}. features: {feat}"
        )
        metadata = {
            "VIN": d.get("vin"),
            "Price": float(d["price"]) if d.get("price") is not None else None,
            "Monthly Payment": float(d["monthly_payment"]) if d.get("monthly_payment") is not None else None,
            "Mileage": int(d["mileage"]) if d.get("mileage") is not None else None,
            "Miles Per Gallon": d.get("mpg"),
            "Post Link": d.get("vehicle_url"),
            "Status": d.get("status", ""),
            "Title": d.get("title", ""),
            "Brand": d.get("brand", ""),
            "Interior Color": d.get("interior_color", ""),
            "Exterior Color": d.get("exterior_color", ""),
            "Drivetrain": d.get("drivetrain", ""),
            "Fuel Type": d.get("fuel_type", ""),
            "Transmission": d.get("transmission", ""),
            "Engine": d.get("engine", ""),
        }
        docs.append(Document(page_content=page_content, metadata=metadata))

    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_documents(docs)

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key or None, timeout=120)
    existing = {c.name for c in client.get_collections().collections}
    if collection not in existing:
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
        )
    embeddings = OpenAIEmbeddings(model=embedding_model, api_key=openai_api_key)
    store = QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings)

    added = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        store.add_documents(documents=batch, ids=[str(uuid4()) for _ in batch])
        added += len(batch)
    return {"chunks": added, "vehicles": len(vehicles)}
```

- [ ] **Step 2: Export it + add deps**

In `crawler/temporal_app/pipeline/__init__.py`, add to the imports + `__all__`:
```python
from .bronze import BronzeLoaderConfig, load_bronze
from .chatbot_embeddings import embed_chatbot_vehicles
from .embeddings import embed_vehicles
from .similarity import compute_item_similarity

__all__ = [
    "BronzeLoaderConfig",
    "load_bronze",
    "compute_item_similarity",
    "embed_vehicles",
    "embed_chatbot_vehicles",
]
```
In `crawler/temporal_app/requirements.txt`, append (the pipeline image needs the langchain
splitter + qdrant integration; it likely already has langchain-openai/qdrant-client for
embed_vehicles — only add what's missing):
```
langchain-qdrant
langchain-text-splitters
```
(If `grep -iE "langchain-text-splitters|langchain-qdrant" crawler/temporal_app/requirements.txt` already shows them, skip the ones present.)

- [ ] **Step 3: Verify + commit**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
python -m py_compile crawler/temporal_app/pipeline/chatbot_embeddings.py && echo "embed fn OK"
grep -nE "embed_chatbot_vehicles" crawler/temporal_app/pipeline/__init__.py
git add crawler/temporal_app/pipeline/chatbot_embeddings.py crawler/temporal_app/pipeline/__init__.py crawler/temporal_app/requirements.txt
git commit -m "feat(pipeline): embed_chatbot_vehicles pure fn (gold.vehicles -> Qdrant car_vectorize chunked)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
Expected: `embed fn OK`; grep shows the export.

---

## Task 7: `embed_chatbot_vehicles_activity`

**Files:** Modify `crawler/temporal_app/activities.py`

- [ ] **Step 1: Add the activity (mirror embed_vehicles_activity's env-skip pattern)**

In `crawler/temporal_app/activities.py`, add a result dataclass + activity. Near the existing
`EmbedResult` dataclass add:
```python
@dataclass
class ChatbotEmbedResult:
    chunks: int
    vehicles: int
    skipped: bool = False
```
And add the activity (place it next to `embed_vehicles_activity`):
```python
@activity.defn
def embed_chatbot_vehicles_activity() -> ChatbotEmbedResult:
    """Re-ingest gold.vehicles -> Qdrant `car_vectorize` (chatbot v2 collection)."""
    from temporal_app.pipeline import embed_chatbot_vehicles

    api_key = os.environ.get("OPENAI_API_KEY", "")
    qdrant_url = os.environ.get("QDRANT_URL", "")
    if not api_key or not qdrant_url:
        activity.logger.warning("OPENAI_API_KEY / QDRANT_URL unset — skipping chatbot embed")
        return ChatbotEmbedResult(chunks=0, vehicles=0, skipped=True)

    result = embed_chatbot_vehicles(
        warehouse_dsn=_require_env("WAREHOUSE_DSN"),
        qdrant_url=qdrant_url,
        qdrant_api_key=os.environ.get("QDRANT_API_KEY") or None,
        openai_api_key=api_key,
        collection=os.environ.get("CHATBOT_QDRANT_COLLECTION", "car_vectorize"),
        embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
        embedding_dim=int(os.environ.get("OPENAI_EMBEDDING_DIM", "3072")),
    )
    activity.logger.info("embed_chatbot_vehicles: %s", result)
    return ChatbotEmbedResult(chunks=result["chunks"], vehicles=result["vehicles"])
```
(`_require_env` already exists in this file — used by `embed_vehicles_activity`. Confirm with `grep -n "_require_env" crawler/temporal_app/activities.py`.)

- [ ] **Step 2: Verify + commit**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
python -m py_compile crawler/temporal_app/activities.py && echo "activity OK"
grep -nE "embed_chatbot_vehicles_activity|ChatbotEmbedResult" crawler/temporal_app/activities.py
git add crawler/temporal_app/activities.py
git commit -m "feat(pipeline): embed_chatbot_vehicles_activity (Temporal, env-skip like embed_vehicles)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
Expected: `activity OK`; grep shows the activity + result class.

---

## Task 8: Wire into MLWorkflow + register on the worker

**Files:** Modify `crawler/temporal_app/workflows.py`, `crawler/temporal_app/pipeline_worker.py`

- [ ] **Step 1: Extend MLResult + run the activity in parallel**

In `crawler/temporal_app/workflows.py`:

(a) The activities are imported at module top inside `with workflow.unsafe.imports_passed_through():` (or similar). Add `embed_chatbot_vehicles_activity` to that import from `temporal_app.activities` (find the existing import of `embed_vehicles_activity` and add the new name alongside it).

(b) Extend the `MLResult` dataclass:
```python
@dataclass
class MLResult:
    similarity_items: int
    similarity_pairs: int
    embedded: int
    chatbot_chunks: int = 0
```

(c) In `MLWorkflow.run`, add a third task and gather it. Current:
```python
        sim, embed = await asyncio.gather(sim_task, embed_task)

        return MLResult(
            similarity_items=sim.items,
            similarity_pairs=sim.pairs,
            embedded=embed.embedded,
        )
```
Change to:
```python
        chatbot_task = workflow.execute_activity(
            embed_chatbot_vehicles_activity,
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        sim, embed, chatbot = await asyncio.gather(sim_task, embed_task, chatbot_task)

        return MLResult(
            similarity_items=sim.items,
            similarity_pairs=sim.pairs,
            embedded=embed.embedded,
            chatbot_chunks=chatbot.chunks,
        )
```
(`timedelta`, `RetryPolicy`, `asyncio` are already imported in this file — confirm with grep.)

- [ ] **Step 2: Register the activity on the pipeline worker**

In `crawler/temporal_app/pipeline_worker.py`, add `embed_chatbot_vehicles_activity` to BOTH the import from `temporal_app.activities` AND the `activities=[...]` list (next to `embed_vehicles_activity`).

- [ ] **Step 3: Verify + commit**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
python -m py_compile crawler/temporal_app/workflows.py crawler/temporal_app/pipeline_worker.py && echo "wf OK"
grep -nE "embed_chatbot_vehicles_activity|chatbot_chunks|chatbot_task" crawler/temporal_app/workflows.py
grep -nE "embed_chatbot_vehicles_activity" crawler/temporal_app/pipeline_worker.py
git add crawler/temporal_app/workflows.py crawler/temporal_app/pipeline_worker.py
git commit -m "feat(pipeline): MLWorkflow runs embed_chatbot_vehicles parallel; worker registers it

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
Expected: `wf OK`; grep shows the activity wired in both files (import + gather + register).

---

## Task 9: Delete the dead standalone chatbot_2 server

**Files:** delete `chatbot_2/api_server.py`

- [ ] **Step 1: Remove it (logic now lives in the backend route)**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git rm chatbot_2/api_server.py
git commit -m "chore(chatbot_2): remove standalone api_server (logic moved into backend /api/v1/chat)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
(Keep `chatbot_2/generate_response.py` + `user_profile.py` + `ingest_database.py` as the source
of truth / standalone ingest; the backend has its own copies. Optionally note in a comment that
the backend copy is the live one — but do not delete the chatbot_2 originals in this task.)

---

## Task 10: User build + deploy + verify (USER runs)

**Files:** none (deploy + live test).

- [ ] **Step 1: Build + push + deploy backend (max-instances=1)**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
P=cobalt-bond-494609-a6
REG=us-central1-docker.pkg.dev/$P/car-recsys
docker build -t $REG/backend:latest car-recsys-system/backend
docker push $REG/backend:latest
gcloud run deploy car-backend --image=$REG/backend:latest \
  --region=us-central1 --project=$P --allow-unauthenticated \
  --max-instances=1 \
  --set-env-vars=CHATBOT_QDRANT_COLLECTION=car_vectorize
```
Expected: new revision deploys. (The langchain 1.x bump installs at image build — if pip
conflicts, paste the resolver error; the fix is to align versions as chatbot_2 did.)

- [ ] **Step 2: Verify the agentic chat works on prod**
```bash
BACKEND_URL=https://car-backend-vtinskoecq-uc.a.run.app
echo "--- health ---"; curl -s "$BACKEND_URL/api/v1/chat/health"; echo
echo "--- turn 1 ---"
SID=$(curl -s -X POST "$BACKEND_URL/api/v1/chat" -H "Content-Type: application/json" \
  -d '{"message":"I want a reliable hybrid SUV under 30k"}' | tee /dev/stderr | python3 -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
echo "--- turn 2 (same session, should keep context) ---"
curl -s -X POST "$BACKEND_URL/api/v1/chat" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"which of those is cheapest?\"}" | head -c 600; echo
echo "--- no regression ---"
curl -s -o /dev/null -w "listings:%{http_code} reco:%{http_code}\n" "$BACKEND_URL/api/v1/listings?limit=1"
```
Expected: health `healthy`; turn 1 returns a grounded answer citing real cars; turn 2 keeps
context; listings still 200.

- [ ] **Step 3: Rebuild + deploy the pipeline-worker, run MLWorkflow once**
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
REG=us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys
docker build -f crawler/Dockerfile.pipeline -t car-pipeline-worker:latest .
docker tag car-pipeline-worker:latest $REG/pipeline-worker:latest
docker push $REG/pipeline-worker:latest
gcloud compute ssh temporal-worker --zone=us-central1-a --project=cobalt-bond-494609-a6 --command='
  IMG=us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys/pipeline-worker:latest
  docker pull "$IMG"; docker rm -f pipeline-worker
  # add CHATBOT_QDRANT_COLLECTION if missing
  grep -q CHATBOT_QDRANT_COLLECTION worker.env || echo "CHATBOT_QDRANT_COLLECTION=car_vectorize" >> worker.env
  docker run -d --name pipeline-worker --restart unless-stopped --env-file worker.env "$IMG"
  sleep 4 && docker logs --tail 8 pipeline-worker'
# trigger an ML run from local (Temporal Cloud)
cd crawler
TEMPORAL_ADDRESS=car-recsys.islko.tmprl.cloud:7233 TEMPORAL_NAMESPACE=car-recsys.islko \
TEMPORAL_API_KEY='<tmprl key>' \
  PYTHONPATH=. .venv/bin/python -m temporal_app.scripts.trigger_once ml
```
Expected: worker reconnects; the ML workflow runs and `embed_chatbot_vehicles` completes;
`car_vectorize` point count reflects a fresh re-ingest.

- [ ] **Step 4: Report**
If chat answers multi-turn on prod, listings/reco unaffected, and the ML run re-embeds
`car_vectorize`, Sub-2 is done — Sub-3 (React) is next. Paste any error.

---

## Self-Review Notes
- **Spec coverage:** (A) move graph + delete old → Tasks 1–3; in-memory profile → Task 2; one-leftover analytics gate — handled in Sub-1 already (`fab38f6`/note), re-confirm during Task 1 py_compile. (B) rewrite chat.py to POST /api/v1/chat, drop old endpoints, keep /health → Task 4. (C) deps bump + CHATBOT_QDRANT_COLLECTION + delete api_server → Tasks 5, 9. (D) pipeline embed_chatbot_vehicles activity in MLWorkflow → Tasks 6–8. Deploy max-instances=1 + verify → Task 10. All spec parts mapped.
- **Placeholder scan:** No TBD. Every code step has full content. The only `<...>` are the user's Temporal key (Task 10). The two "confirm import path / confirm _require_env exists" notes are concrete grep checks, not hand-waving.
- **Type consistency:** `initialize_resources()`/`generate_response(llm, vector_store, history, user_input, session_id)` used in chat.py match the graph. `load_profile/save_profile/delete_profile/UserProfile` signatures preserved (graph untouched). `embed_chatbot_vehicles(...)` params match the activity call; returns `{chunks, vehicles}` → `ChatbotEmbedResult{chunks, vehicles}` → `MLResult.chatbot_chunks`. `CHATBOT_QDRANT_COLLECTION` consistent across config.py, the graph, the activity, worker.env. Collection `car_vectorize` consistent throughout.
- **Two deploy targets** (backend Cloud Run + pipeline-worker VM image) — Task 10 covers both, as the user accepted keeping Part D in Sub-2.
- **No test runner** — verify is py_compile + grep here; real build/deploy/live-chat + pipeline run are user-run (Task 10), the correct gate for langchain-install + cloud behavior.
