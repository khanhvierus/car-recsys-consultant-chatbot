-- ============================================================================
-- Materialized views — popularity / trending
-- ============================================================================
-- These are NOT dbt models: they join a dbt-managed mart (gold.vehicles) to
-- app-written tables (gold.user_interactions). dbt should not own objects that
-- depend on tables the application writes.
--
-- Run AFTER the first dbt run (gold.vehicles must exist). The car_recsys_transform
-- Airflow DAG executes this file (idempotent) then REFRESHes the views.
-- The UNIQUE indexes are required for REFRESH MATERIALIZED VIEW CONCURRENTLY.
-- ============================================================================

-- Popularity: per-listing interaction rollup ---------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS gold.mv_popular_vehicles AS
SELECT
    v.vehicle_id,
    v.title,
    v.brand,
    v.car_model,
    v.price,
    v.primary_image_url,
    v.car_rating,
    COUNT(ui.id)                                                              AS total_interactions,
    COUNT(ui.id) FILTER (WHERE ui.interaction_type = 'view')                  AS views,
    COUNT(ui.id) FILTER (WHERE ui.interaction_type IN ('save', 'favorite'))    AS saves,
    COUNT(ui.id) FILTER (WHERE ui.interaction_type IN ('contact', 'inquiry'))  AS contacts,
    COALESCE(SUM(ui.interaction_score)
             FILTER (WHERE ui.created_at > NOW() - INTERVAL '30 days'), 0)     AS pop_score_30d
FROM gold.vehicles v
LEFT JOIN gold.user_interactions ui ON v.vehicle_id = ui.vehicle_id
GROUP BY v.vehicle_id, v.title, v.brand, v.car_model, v.price,
         v.primary_image_url, v.car_rating;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_popular_vehicle
    ON gold.mv_popular_vehicles (vehicle_id);

-- Trending: per-model interaction velocity, last 7d vs prior 7d --------------
CREATE MATERIALIZED VIEW IF NOT EXISTS gold.mv_trending_models AS
SELECT
    v.car_model,
    v.brand,
    COUNT(ui.id) FILTER (
        WHERE ui.created_at > NOW() - INTERVAL '7 days')                      AS interactions_7d,
    COUNT(ui.id) FILTER (
        WHERE ui.created_at <= NOW() - INTERVAL '7 days'
          AND ui.created_at >  NOW() - INTERVAL '14 days')                    AS interactions_prior_7d
FROM gold.vehicles v
LEFT JOIN gold.user_interactions ui ON v.vehicle_id = ui.vehicle_id
WHERE v.car_model IS NOT NULL
GROUP BY v.car_model, v.brand;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_trending_model
    ON gold.mv_trending_models (car_model);
