{#
  Compensating control for the dropped cross-schema FK
  (gold.user_interactions.vehicle_id -> raw.used_vehicles). The FK had to go
  because dbt DROP/CREATEs gold.vehicles on every full-refresh. This singular
  test flags interactions that point at a VIN absent from gold.vehicles.

  severity = warn: an orphan is a data-quality signal worth surfacing, but it
  must not block the dbt run / Airflow DAG (a vehicle can legitimately drop out
  of inventory after a user interacted with it).
#}
{{ config(severity='warn') }}

select
    ui.vehicle_id,
    count(*) as orphan_interactions
from {{ source('app', 'user_interactions') }} ui
left join {{ ref('vehicles') }} v
    on ui.vehicle_id = v.vehicle_id
where v.vehicle_id is null
group by ui.vehicle_id
