# Architecture Diagrams (Mermaid)

Các sơ đồ dưới đây dùng **Mermaid** — render trực tiếp trên GitHub, [mermaid.live](https://mermaid.live),
VSCode (extension *Markdown Preview Mermaid*), hoặc Notion. Đã verify render ra SVG hợp lệ.

> Muốn có logo Docker/Postgres/Temporal nhúng trong chart? Mermaid hỗ trợ qua
> `@{ icon: "logos:postgresql" }` (v11.3+) **nhưng chỉ hiển thị trên trình render bật
> *iconify*** (mermaid.live) — GitHub README sẽ hiện dấu `?`. Vì vậy các diagram dưới
> dùng **màu + label** để render đẹp ở mọi nơi.

---

## 1. Kiến trúc tổng thể

```mermaid
flowchart TB
  subgraph HOST["🖥️ HOST (./run_worker.sh)"]
    direction LR
    carscom["cars.com"]:::ext
    crawlw["crawler worker<br/>Chrome + Xvfb"]:::host
    carscom -->|crawl| crawlw
  end

  gcs["GCS bronze<br/>gs://incremental_raw/dt=YYYY-MM-DD/"]:::store

  subgraph DOCKER["🐳 DOCKER (docker compose up)"]
    temporal["Temporal<br/>server :7233 · UI :8233"]:::orch
    pworker["pipeline-worker<br/>load_bronze · dbt · refresh · embed"]:::orch
    subgraph PG["🐘 PostgreSQL :5432"]
      bronze["bronze<br/>raw_listings (JSONB)"]:::bronze
      silver["silver<br/>dim/fct/bridge (3NF)"]:::silver
      gold["gold<br/>vehicles · marts · matviews"]:::gold
      bronze --> silver --> gold
    end
    qdrant["Qdrant :6333"]:::vec
    redis["Redis :6379"]:::cache
    backend["backend :8000 (FastAPI)<br/>reco + chatbot"]:::api
    temporal -->|tasks| pworker
    pworker -->|dbt| bronze
    pworker -->|embed| qdrant
    gold -->|read| backend
    backend -.->|vector| qdrant
    backend -.-> redis
  end

  frontend["frontend :3000<br/>Vite + React (host npm)"]:::ui

  crawlw -->|upload| gcs
  gcs -->|read dt=| bronze
  backend <-->|/api| frontend

  classDef ext fill:#ffd8a8,stroke:#f59e0b,color:#000
  classDef host fill:#a5d8ff,stroke:#4a9eed,color:#000
  classDef store fill:#c3fae8,stroke:#06b6d4,color:#000
  classDef orch fill:#d0bfff,stroke:#8b5cf6,color:#000
  classDef bronze fill:#ffd8a8,stroke:#f59e0b,color:#000
  classDef silver fill:#a5d8ff,stroke:#4a9eed,color:#000
  classDef gold fill:#b2f2bb,stroke:#22c55e,color:#000
  classDef vec fill:#eebefa,stroke:#ec4899,color:#000
  classDef cache fill:#ffc9c9,stroke:#ef4444,color:#000
  classDef api fill:#a5d8ff,stroke:#4a9eed,color:#000
  classDef ui fill:#fff3bf,stroke:#f59e0b,color:#000
```

---

## 2. Temporal pipeline — WeeklyPipeline

```mermaid
flowchart TB
  sched{{"Schedule<br/>cron Mon 02:00"}}:::sched
  parent["WeeklyPipeline<br/>(parent workflow)"]:::orch
  sched -->|fire| parent

  subgraph CHAIN["fail-stop chain (bước fail → dừng cả chain)"]
    crawl["1. WeeklyCrawl<br/>queue: car-crawler-tq · HOST"]:::host
    transform["2. Transform<br/>queue: car-pipeline-tq · DOCKER"]:::gold
    ml["3. ML<br/>queue: car-pipeline-tq · DOCKER"]:::vec
    crawl -->|ok| transform -->|ok| ml
  end
  parent -->|child| crawl

  crawl --- crawlsteps["crawl_links → scrape_details → upload_gcs<br/>(dt=YYYY-MM-DD/ on GCS)"]:::note
  transform --- transteps["load_bronze → ensure_partition →<br/>dbt_build → refresh_matviews"]:::note
  ml --- mlsteps["compute_item_similarity ∥<br/>embed_vehicles → Qdrant"]:::note

  classDef sched fill:#fff3bf,stroke:#f59e0b,color:#000
  classDef orch fill:#d0bfff,stroke:#8b5cf6,color:#000
  classDef host fill:#a5d8ff,stroke:#4a9eed,color:#000
  classDef gold fill:#b2f2bb,stroke:#22c55e,color:#000
  classDef vec fill:#eebefa,stroke:#ec4899,color:#000
  classDef note fill:#f8f9fa,stroke:#adb5bd,color:#000
```

---

## 3. dbt medallion — data flow

```mermaid
flowchart TB
  bronze["bronze.raw_listings<br/>JSONB landing · idempotent (file_hash)"]:::bronze
  stg["staging (views)<br/>stg_raw_latest (DISTINCT ON vin) → stg_listings (parse)"]:::stg
  bronze -->|dedup VIN| stg

  subgraph SILVER["SILVER (3NF tables)"]
    fct["fct_listing<br/>incremental delete+insert"]:::silver
    dims["dim_car_model · dim_seller<br/>dim_feature · bridge_listing_feature"]:::silver
  end
  stg --> fct

  subgraph GOLD["GOLD (app marts)"]
    vehicles["vehicles — MERGE by VIN (current)<br/>source · first_seen · last_updated"]:::gold
    pricehist["vehicle_price_history<br/>change-events · partition by day"]:::bronze
    goldrest["car_models · sellers · reviews<br/>features/images · matviews"]:::store
  end
  fct -->|dbt| vehicles
  fct -->|dbt| pricehist
  vehicles --> goldrest

  goldrest -->|read| consumers["backend reco/chatbot · embed → Qdrant"]:::api

  classDef bronze fill:#ffd8a8,stroke:#f59e0b,color:#000
  classDef stg fill:#fff3bf,stroke:#f59e0b,color:#000
  classDef silver fill:#a5d8ff,stroke:#4a9eed,color:#000
  classDef gold fill:#b2f2bb,stroke:#22c55e,color:#000
  classDef store fill:#c3fae8,stroke:#06b6d4,color:#000
  classDef api fill:#a5d8ff,stroke:#4a9eed,color:#000
```

---

## 4. Recommendation engine (multi-stage hybrid)

```mermaid
flowchart LR
  subgraph RECALL["Candidate generation"]
    collab["Collaborative<br/>(gold.item_similarity)"]:::recall
    content["Content<br/>(brand/price/fuel)"]:::recall
    vector["Vector (Qdrant)"]:::recall
    pop["Popularity (matview)"]:::recall
  end
  ranker["WeightedLinearRanker"]:::rank
  mmr["MMR Reranker<br/>(diversity)"]:::rank
  topk["top-K<br/>recommendations"]:::out

  collab --> ranker
  content --> ranker
  vector --> ranker
  pop --> ranker
  ranker -->|rank| mmr -->|re-rank| topk

  classDef recall fill:#d0bfff,stroke:#8b5cf6,color:#000
  classDef rank fill:#ffd8a8,stroke:#f59e0b,color:#000
  classDef out fill:#b2f2bb,stroke:#22c55e,color:#000
```

---

## 5. Chatbot — RAG hybrid retrieval

```mermaid
flowchart LR
  umsg["user message"]:::host
  parser["query_parser<br/>(hard constraints)"]:::rank
  sql["SQL filter<br/>gold.vehicles WHERE"]:::gold
  vec["Qdrant vector<br/>(payload filter)"]:::vec
  rrf["RRF fusion<br/>(merge ranks)"]:::rank
  gen["gpt-4o-mini<br/>grounded · cite VIN"]:::orch

  umsg --> parser
  parser --> sql
  parser --> vec
  sql --> rrf
  vec --> rrf
  rrf --> gen

  classDef host fill:#a5d8ff,stroke:#4a9eed,color:#000
  classDef rank fill:#fff3bf,stroke:#f59e0b,color:#000
  classDef gold fill:#b2f2bb,stroke:#22c55e,color:#000
  classDef vec fill:#eebefa,stroke:#ec4899,color:#000
  classDef orch fill:#d0bfff,stroke:#8b5cf6,color:#000
```

---

## 6. SILVER — ERD (3NF dimensional)

Surrogate key = `md5(natural_key)`, NULL-safe. FK được enforce bằng dbt
`relationships` tests (không dùng FK cứng vì gold rebuild). **Grain rule:** dữ liệu
`car.*` (rating/reviews) thuộc về car MODEL — keyed `car_model_sk`, không bao giờ per-listing.

```mermaid
erDiagram
  dim_car_model   ||--o{ fct_listing       : "1 model : N listings"
  dim_car_model   ||--|| fct_model_rating   : "1 : 1 rating"
  dim_car_model   ||--o{ fct_model_review   : "1 : N reviews"
  dim_seller      ||--o{ fct_listing        : "1 dealer : N listings"
  fct_listing     ||--o{ bridge_listing_feature : "listing has features"
  dim_feature     ||--o{ bridge_listing_feature : "feature in listings"
  fct_listing     ||--o{ dim_listing_image  : "1 listing : N images"

  dim_car_model {
    text    car_model_sk PK "md5(car_model_slug)"
    text    car_model_slug
    text    brand
    text    car_name
    text    car_link
    text    review_link
  }
  fct_model_rating {
    text    car_model_sk PK "= FK dim_car_model (1:1)"
    numeric car_rating
    int     car_rating_count
    numeric percentage_recommend
    numeric rating_comfort
    numeric rating_interior
    numeric rating_performance
    numeric rating_value
    numeric rating_exterior
    numeric rating_reliability
  }
  fct_model_review {
    text    review_sk PK "content hash"
    text    car_model_sk FK
    numeric overall_rating
    date    review_date
    text    review_title
    text    review_text
  }
  dim_seller {
    text    seller_sk PK "md5(seller_key)"
    text    seller_key
    text    seller_name
    text    seller_link
    text    destination
    numeric seller_rating
    int     seller_rating_count
    text    phone_new
    text    phone_used
    jsonb   hours
    jsonb   highlights
  }
  fct_listing {
    text    listing_sk PK "md5(vin)"
    text    vin
    text    car_model_sk FK
    text    seller_sk FK
    text    stock_number
    text    new_used
    text    title
    numeric price
    numeric monthly_payment
    int     mileage
    date    crawl_date
    text    source
    date    last_updated_date
    text    fuel_type
    text    transmission
    text    drivetrain
    bool    clean_title
    bool    has_accidents
    bool    is_one_owner
    bool    has_open_recall
    timestamp crawled_at
  }
  dim_feature {
    text    feature_sk PK "md5(cat||name)"
    text    feature_category
    text    feature_name
  }
  bridge_listing_feature {
    text    listing_sk FK
    text    feature_sk FK
  }
  dim_listing_image {
    text    listing_sk FK
    text    vin
    int     image_order
    text    image_url
  }
```

---

## 7. GOLD — ERD (app marts, denormalized)

Gold làm phẳng silver (join sẵn) để backend đọc nhanh. Quan hệ qua
`vehicle_id = vin` (TEXT, không FK cứng — `gold.vehicles` bị dbt DROP/CREATE).
`vehicles` MERGE theo VIN (current state); `vehicle_price_history` append (change-events).

```mermaid
erDiagram
  vehicles ||--o{ vehicle_images        : "vehicle_id"
  vehicles ||--o{ vehicle_features      : "vehicle_id"
  vehicles ||--o{ vehicle_price_history : "vin (history)"
  car_models ||--o{ vehicles            : "car_model (slug)"
  car_models ||--o{ reviews             : "car_model"
  sellers  ||--o{ vehicles              : "seller_key"

  vehicles {
    text    vehicle_id PK "= vin"
    text    title
    text    brand
    text    car_model
    numeric price
    int     mileage
    text    fuel_type
    numeric car_rating "copied from model"
    text    seller_name "copied from seller"
    text    primary_image_url
    int     image_count
    int     feature_count
    text    source
    date    first_seen_date
    date    last_updated_date
  }
  vehicle_price_history {
    text    vin FK
    numeric price
    int     mileage
    text    status
    date    crawl_date "partition key"
    timestamp inserted_at
  }
  vehicle_images {
    text    vehicle_id FK
    int     image_order
    text    image_url
  }
  vehicle_features {
    text    vehicle_id FK
    text    feature_category
    text    feature_name
  }
  car_models {
    text    car_model PK
    text    brand
    numeric car_rating
    int     listing_count
    int     review_count
  }
  sellers {
    text    seller_key PK
    text    seller_name
    int     inventory_count
  }
  reviews {
    text    review_sk PK
    text    car_model FK
    numeric overall_rating
    text    review_text
  }
```

---

## 8. Recommendation / App-domain ERD

Khác với marts dbt (#7) — đây là các bảng **app ghi runtime** + **ML precompute** +
**Qdrant vector**, là input/output của hệ thống đề xuất.

- `users · user_interactions · user_favorites · user_searches · chat_*` — backend ghi (có FK cứng tới `users`).
- `item_similarity` — **ML workflow** precompute (item-item CF), reco đọc, không fit runtime.
- `mv_popular_vehicles` — matview (cold-start fallback).
- `vehicle_id` (TEXT = VIN) nối tới `gold.vehicles` nhưng **không FK cứng** (vehicles bị dbt rebuild).

```mermaid
erDiagram
  users ||--o{ user_interactions : "tracks"
  users ||--o{ user_favorites    : "saves"
  users ||--o{ user_searches     : "searches"
  users ||--o{ chat_sessions     : "owns (NULL=guest)"
  chat_sessions ||--o{ chat_messages : "has turns"
  vehicles ||--o{ user_interactions : "vehicle_id (no FK)"
  vehicles ||--o{ item_similarity   : "vehicle_id / neighbor_id"

  users {
    uuid    id PK
    text    username UK
    text    email UK
    text    hashed_password
    bool    is_active
  }
  user_interactions {
    int     id PK
    uuid    user_id FK
    text    vehicle_id "VIN, no FK"
    text    interaction_type "view|click|compare|save|favorite|contact|inquiry"
    numeric interaction_score
    jsonb   extra_data
    timestamp created_at
  }
  user_favorites {
    int     id PK
    uuid    user_id FK
    text    vehicle_id "VIN"
  }
  user_searches {
    int     id PK
    uuid    user_id FK
    text    search_query
    jsonb   filters
    int     results_count
  }
  chat_sessions {
    uuid    id PK
    uuid    user_id FK "NULL for guests"
    text    session_token
    text    title
  }
  chat_messages {
    int     id PK
    uuid    session_id FK
    text    role "user|assistant|system"
    text    content
    jsonb   vehicles "cited cards"
  }
  item_similarity {
    text    vehicle_id PK "VIN"
    text    neighbor_id PK "VIN"
    numeric score
    int     rank
    timestamp computed_at
  }
  vehicles {
    text    vehicle_id PK "= VIN (dbt mart)"
  }
```

### Hệ thống đề xuất dùng các store này thế nào

```mermaid
flowchart LR
  interactions["gold.user_interactions<br/>(app ghi: view/click/save...)"]:::store
  itemsim["gold.item_similarity<br/>(ML precompute CF)"]:::store
  popmv["gold.mv_popular_vehicles<br/>(matview)"]:::store
  qdrant["Qdrant car-vectors<br/>point_id=uuid5(vin)<br/>payload: brand/price/fuel/rating"]:::vec
  vehicles["gold.vehicles"]:::gold

  interactions -->|"ML: cosine CF"| itemsim
  vehicles -->|"ML: embed"| qdrant

  itemsim --> collab["CollaborativeRecaller"]:::recall
  vehicles --> content["ContentRecaller"]:::recall
  qdrant --> vecr["VectorRecaller"]:::recall
  popmv --> popr["PopularityRecaller"]:::recall
  collab & content & vecr & popr --> ranker["Ranker → MMR → top-K"]:::rank

  classDef store fill:#c3fae8,stroke:#06b6d4,color:#000
  classDef vec fill:#eebefa,stroke:#ec4899,color:#000
  classDef gold fill:#b2f2bb,stroke:#22c55e,color:#000
  classDef recall fill:#d0bfff,stroke:#8b5cf6,color:#000
  classDef rank fill:#ffd8a8,stroke:#f59e0b,color:#000
```
