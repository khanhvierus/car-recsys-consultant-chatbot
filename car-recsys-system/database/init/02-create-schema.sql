-- ============================================================================
-- Car Recommendation System — Database Schema (medallion architecture)
-- ============================================================================
-- Layers:
--   bronze : raw crawled JSON landed verbatim (JSONB). Append-only, idempotent.
--   silver : 3NF dimensional model — CREATED AND OWNED BY dbt (not here).
--   gold   : app-facing marts (dbt) + user-domain tables (app-written, here).
--
-- This init script creates ONLY:
--   * the bronze landing table
--   * empty silver / gold schemas (dbt fills silver + the gold marts)
--   * gold user-domain tables the FastAPI app writes to directly
--
-- The denormalized raw.used_vehicles (55-column) table and the 7 CSV tables
-- are intentionally GONE — replaced by bronze.raw_listings + dbt models.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;   -- populated by dbt
CREATE SCHEMA IF NOT EXISTS gold;     -- dbt marts + app tables below

-- ============================================================================
-- BRONZE LAYER — raw JSON landing
-- ============================================================================
-- One row per crawled JSON file. Append-only: a re-crawl of the same VIN with
-- changed content lands a new row (different file_hash). The "current" version
-- per VIN is resolved downstream in dbt staging (DISTINCT ON ... ingested_at).

CREATE TABLE IF NOT EXISTS bronze.raw_listings (
    raw_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_hash       TEXT NOT NULL,                 -- sha256 of file bytes — idempotency key
    gcs_path        TEXT NOT NULL,                 -- gs://incremental_raw/dt=YYYY-MM-DD/<page>/<f>.json
    page_number     INTEGER,                       -- parsed from the GCS path
    crawl_date      DATE,                          -- dt= partition lifted from the path
    vin             TEXT,                          -- payload->post->basic_desc->VIN, lifted out
    car_model_slug  TEXT,                          -- payload->car->car_model, lifted out
    payload         JSONB NOT NULL,                -- the entire crawled file, untouched
    crawled_at      TIMESTAMPTZ,                   -- payload->>'datetime'
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source          TEXT NOT NULL DEFAULT 'incremental',  -- 'initial' | 'incremental'
    run_id          TEXT,                          -- Temporal workflow run that loaded this row
    CONSTRAINT uq_raw_listings_file_hash UNIQUE (file_hash),
    CONSTRAINT chk_raw_listings_source CHECK (source IN ('initial', 'incremental'))
);

CREATE INDEX IF NOT EXISTS idx_raw_listings_vin        ON bronze.raw_listings (vin);
CREATE INDEX IF NOT EXISTS idx_raw_listings_model      ON bronze.raw_listings (car_model_slug);
CREATE INDEX IF NOT EXISTS idx_raw_listings_ingested   ON bronze.raw_listings (ingested_at);
CREATE INDEX IF NOT EXISTS idx_raw_listings_crawl_date ON bronze.raw_listings (crawl_date);
CREATE INDEX IF NOT EXISTS idx_raw_listings_payload    ON bronze.raw_listings USING GIN (payload jsonb_path_ops);

COMMENT ON TABLE bronze.raw_listings IS 'Raw crawled cars.com JSON, one row per file. Append-only, idempotent via file_hash.';

-- ============================================================================
-- GOLD LAYER — user-domain tables (written by the FastAPI app)
-- ============================================================================
-- NOTE: vehicle_id is a plain TEXT VIN with NO foreign key. The gold.vehicles
-- mart is DROP/CREATEd by dbt on every full-refresh; a cross-schema FK into it
-- would break the rebuild. Referential integrity is enforced instead by the
-- dbt test tests/assert_no_orphan_interactions.sql.

CREATE TABLE IF NOT EXISTS gold.users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        TEXT UNIQUE NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name       TEXT,
    phone           TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    is_verified     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gold.user_interactions (
    id                SERIAL PRIMARY KEY,
    user_id           UUID REFERENCES gold.users(id) ON DELETE CASCADE,
    vehicle_id        TEXT NOT NULL,                       -- VIN, no FK (see note above)
    interaction_type  TEXT NOT NULL,                       -- view|click|compare|save|favorite|contact|inquiry
    session_id        TEXT,
    interaction_score NUMERIC DEFAULT 1.0,
    extra_data        JSONB,
    created_at        TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gold.user_favorites (
    id          SERIAL PRIMARY KEY,
    user_id     UUID REFERENCES gold.users(id) ON DELETE CASCADE,
    vehicle_id  TEXT NOT NULL,                              -- VIN, no FK
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, vehicle_id)
);

CREATE TABLE IF NOT EXISTS gold.user_searches (
    id            SERIAL PRIMARY KEY,
    user_id       UUID REFERENCES gold.users(id) ON DELETE CASCADE,
    search_query  TEXT,
    filters       JSONB,
    results_count INTEGER,
    created_at    TIMESTAMP DEFAULT NOW()
);

-- Chatbot persistence — proper tables (was created on-the-fly in chat.py before).
CREATE TABLE IF NOT EXISTS gold.chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES gold.users(id) ON DELETE CASCADE,  -- NULL for guests
    session_token TEXT,
    title       TEXT,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gold.chat_messages (
    id          SERIAL PRIMARY KEY,
    session_id  UUID REFERENCES gold.chat_sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,                              -- user|assistant|system
    content     TEXT NOT NULL,
    vehicles    JSONB,                                      -- vehicle cards cited in the reply
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Precomputed item-item collaborative-filtering neighbors.
-- Refreshed by the car_recsys_ml Airflow DAG (TRUNCATE + INSERT); read by the
-- recommendation engine so it never has to fit a model in-request.
CREATE TABLE IF NOT EXISTS gold.item_similarity (
    vehicle_id   TEXT NOT NULL,
    neighbor_id  TEXT NOT NULL,
    score        NUMERIC NOT NULL,
    rank         INTEGER NOT NULL,
    computed_at  TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (vehicle_id, neighbor_id)
);

-- ----------------------------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_interactions_user    ON gold.user_interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_interactions_vehicle ON gold.user_interactions(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_interactions_type    ON gold.user_interactions(interaction_type);
CREATE INDEX IF NOT EXISTS idx_interactions_created ON gold.user_interactions(created_at);

CREATE INDEX IF NOT EXISTS idx_favorites_user       ON gold.user_favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_favorites_vehicle    ON gold.user_favorites(vehicle_id);

CREATE INDEX IF NOT EXISTS idx_searches_user        ON gold.user_searches(user_id);
CREATE INDEX IF NOT EXISTS idx_searches_created     ON gold.user_searches(created_at);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON gold.chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user    ON gold.chat_sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_item_similarity_vehicle ON gold.item_similarity(vehicle_id);

-- ============================================================================
-- Functions & triggers
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

DROP TRIGGER IF EXISTS update_users_updated_at ON gold.users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON gold.users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_chat_sessions_updated_at ON gold.chat_sessions;
CREATE TRIGGER update_chat_sessions_updated_at
    BEFORE UPDATE ON gold.chat_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- GOLD price/mileage history — change-event log, partitioned by crawl_date.
-- dbt's gold.vehicle_price_history model APPENDS into this parent; Postgres
-- routes each row to the monthly partition. Partitions are created on demand by
-- gold.ensure_price_history_partition(), called by the Temporal ensure_partition
-- activity before dbt runs.
-- ============================================================================
CREATE TABLE IF NOT EXISTS gold.vehicle_price_history (
    vin           TEXT        NOT NULL,
    price         NUMERIC,
    mileage       INTEGER,
    status        TEXT,
    crawl_date    DATE        NOT NULL,
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
) PARTITION BY RANGE (crawl_date);

CREATE INDEX IF NOT EXISTS idx_price_history_vin_date
    ON gold.vehicle_price_history (vin, crawl_date);

-- Idempotently create the monthly partition covering `d`.
CREATE OR REPLACE FUNCTION gold.ensure_price_history_partition(d DATE)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    start_m DATE := date_trunc('month', d)::date;
    end_m   DATE := (date_trunc('month', d) + interval '1 month')::date;
    part    TEXT := format('vehicle_price_history_%s', to_char(start_m, 'YYYY_MM'));
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS gold.%I PARTITION OF gold.vehicle_price_history '
        'FOR VALUES FROM (%L) TO (%L)', part, start_m, end_m
    );
END $$;

-- ============================================================================
-- Permissions
-- ============================================================================
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA bronze TO admin;
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA silver TO admin;
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA gold   TO admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA bronze TO admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA gold   TO admin;
-- dbt creates objects later; make sure admin keeps access to them too.
ALTER DEFAULT PRIVILEGES IN SCHEMA silver GRANT ALL ON TABLES TO admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold   GRANT ALL ON TABLES TO admin;

-- ============================================================================
-- Comments
-- ============================================================================
COMMENT ON TABLE gold.users             IS 'Registered users.';
COMMENT ON TABLE gold.user_interactions IS 'User interaction events feeding the recommender.';
COMMENT ON TABLE gold.user_favorites    IS 'User favorite vehicles (VIN).';
COMMENT ON TABLE gold.user_searches     IS 'User search history.';
COMMENT ON TABLE gold.chat_sessions     IS 'Chatbot conversation sessions.';
COMMENT ON TABLE gold.chat_messages     IS 'Chatbot messages within a session.';
COMMENT ON TABLE gold.item_similarity   IS 'Precomputed item-item CF neighbors (refreshed by car_recsys_ml DAG).';
