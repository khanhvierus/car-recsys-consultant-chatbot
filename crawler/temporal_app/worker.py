"""Crawler worker — runs on the HOST (needs Chrome + Xvfb).

Serves only WeeklyCrawl on CRAWL_TASK_QUEUE. The Transform/ML workflows run in
the Dockerized pipeline worker (pipeline_worker.py) on a separate queue, so
this worker never has to import psycopg2/dbt/sklearn.

Connection (no TLS for local self-host):
  TEMPORAL_ADDRESS    default localhost:7233
  TEMPORAL_NAMESPACE  default "default"
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import Worker

from temporal_app.activities import (
    crawl_links_activity,
    scrape_details_activity,
    upload_gcs_activity,
)
from temporal_app.client import connect
from temporal_app.shared import CRAWL_TASK_QUEUE
from temporal_app.workflows import WeeklyCrawlWorkflow


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    log = logging.getLogger("crawler-worker")

    client = await connect()
    log.info("Connected. Crawler worker on task queue %s", CRAWL_TASK_QUEUE)

    # SeleniumBase is blocking; cap at 1 so two Chrome instances never co-exist.
    with ThreadPoolExecutor(max_workers=1) as executor:
        worker = Worker(
            client,
            task_queue=CRAWL_TASK_QUEUE,
            workflows=[WeeklyCrawlWorkflow],
            activities=[
                crawl_links_activity,
                scrape_details_activity,
                upload_gcs_activity,
            ],
            activity_executor=executor,
            max_concurrent_activities=1,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
