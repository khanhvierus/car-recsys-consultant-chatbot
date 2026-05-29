"""Pipeline worker — runs in Docker (no Chrome needed).

Serves Transform + ML on PIPELINE_TASK_QUEUE: load_bronze / dbt_build /
refresh_matviews / compute_item_similarity / embed_vehicles.

Connection (no TLS for local self-host):
  TEMPORAL_ADDRESS    default localhost:7233 (set to temporal:7233 in Docker)
  TEMPORAL_NAMESPACE  default "default"
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import Worker

from temporal_app.activities import (
    compute_item_similarity_activity,
    dbt_build_activity,
    embed_vehicles_activity,
    ensure_partition_activity,
    load_bronze_activity,
    refresh_matviews_activity,
)
from temporal_app.client import connect
from temporal_app.shared import PIPELINE_TASK_QUEUE
from temporal_app.workflows import (
    MLWorkflow,
    TransformWorkflow,
    WeeklyPipelineWorkflow,
)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    log = logging.getLogger("pipeline-worker")

    client = await connect()
    log.info("Connected. Pipeline worker on task queue %s", PIPELINE_TASK_QUEUE)

    # Activities are blocking (psycopg2, dbt subprocess, OpenAI). A small pool
    # is fine — the ML workflow runs similarity + embeddings concurrently.
    with ThreadPoolExecutor(max_workers=4) as executor:
        worker = Worker(
            client,
            task_queue=PIPELINE_TASK_QUEUE,
            workflows=[WeeklyPipelineWorkflow, TransformWorkflow, MLWorkflow],
            activities=[
                load_bronze_activity,
                ensure_partition_activity,
                dbt_build_activity,
                refresh_matviews_activity,
                compute_item_similarity_activity,
                embed_vehicles_activity,
            ],
            activity_executor=executor,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
