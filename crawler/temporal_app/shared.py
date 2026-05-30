"""Shared constants — used by workflows, workers, and scripts.

Two task queues so the two worker types never pick up each other's work:
  * CRAWL_TASK_QUEUE    — WeeklyCrawl (host worker, needs Chrome + Xvfb)
  * PIPELINE_TASK_QUEUE — Transform + ML (Docker worker, psycopg2/dbt/ml only)
"""
from __future__ import annotations

CRAWL_TASK_QUEUE = "car-crawler-tq"
PIPELINE_TASK_QUEUE = "car-pipeline-tq"

WORKFLOW_ID_PREFIX = "weekly"
