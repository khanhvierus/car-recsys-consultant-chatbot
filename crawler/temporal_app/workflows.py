"""Temporal workflows for the car-recsys data platform.

  WeeklyCrawlWorkflow    crawl → scrape → upload for one page
  TransformWorkflow      load_bronze → dbt_build → refresh_matviews
  MLWorkflow             compute_item_similarity ∥ embed_vehicles (parallel)
  WeeklyPipelineWorkflow crawl → transform → ml  (the scheduled chain)

Replaces the three Airflow DAGs. The single scheduled entrypoint is
WeeklyPipelineWorkflow — it runs the three as child workflows in order,
fail-stop (a failed step aborts the rest). See scripts/create_schedule.py.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal_app.shared import CRAWL_TASK_QUEUE, PIPELINE_TASK_QUEUE

with workflow.unsafe.imports_passed_through():
    from temporal_app.activities import (
        CrawlInput,
        CrawlLinksResult,
        EmbedResult,
        LoadBronzeResult,
        ScrapeResult,
        SimilarityResult,
        UploadResult,
        compute_item_similarity_activity,
        crawl_links_activity,
        dbt_build_activity,
        embed_vehicles_activity,
        ensure_partition_activity,
        load_bronze_activity,
        refresh_matviews_activity,
        scrape_details_activity,
        upload_gcs_activity,
    )


@dataclass
class WeeklyCrawlInput:
    page: int = 1
    crawl_date: str = ""   # set by WeeklyPipeline so the chain shares one date


@dataclass
class WeeklyCrawlResult:
    page: int
    link_count: int
    detail_done: int
    detail_fail: int
    detail_skip: int
    json_uploaded: int
    images_uploaded: int


# Default retry — Temporal already retries automatically; tune timeouts only.
_LINK_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=30),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=10),
    maximum_attempts=3,
)
_SCRAPE_RETRY = RetryPolicy(
    initial_interval=timedelta(minutes=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=15),
    maximum_attempts=2,  # scrape is expensive; don't retry many times
)
_UPLOAD_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=5,  # GCS is cheap to retry
)


@workflow.defn(name="WeeklyCrawl")
class WeeklyCrawlWorkflow:
    @workflow.run
    async def run(self, inp: WeeklyCrawlInput) -> WeeklyCrawlResult:
        page = inp.page
        workflow.logger.info("WeeklyCrawl starting page=%s", page)
        crawl_date = inp.crawl_date or workflow.now().strftime("%Y-%m-%d")
        act_in = CrawlInput(page=page, crawl_date=crawl_date)

        link_res: CrawlLinksResult = await workflow.execute_activity(
            crawl_links_activity,
            act_in,
            start_to_close_timeout=timedelta(minutes=15),
            heartbeat_timeout=timedelta(minutes=5),
            retry_policy=_LINK_RETRY,
        )

        scrape_res: ScrapeResult = await workflow.execute_activity(
            scrape_details_activity,
            act_in,
            start_to_close_timeout=timedelta(hours=2),
            heartbeat_timeout=timedelta(minutes=10),
            retry_policy=_SCRAPE_RETRY,
        )

        upload_res: UploadResult = await workflow.execute_activity(
            upload_gcs_activity,
            act_in,
            start_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(minutes=5),
            retry_policy=_UPLOAD_RETRY,
        )

        return WeeklyCrawlResult(
            page=page,
            link_count=link_res.link_count,
            detail_done=scrape_res.done,
            detail_fail=scrape_res.fail,
            detail_skip=scrape_res.skip,
            json_uploaded=upload_res.json_uploaded,
            images_uploaded=upload_res.images_uploaded,
        )


# ─────────────────────────────── Transform ──────────────────────────────────

@dataclass
class TransformResult:
    bronze_inserted: int
    bronze_scanned: int


_DB_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=15),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=3,
)


@workflow.defn(name="Transform")
class TransformWorkflow:
    """Bronze JSON → Postgres → dbt silver/gold → materialized views."""

    @workflow.run
    async def run(self, crawl_date: str = "") -> TransformResult:
        dt = crawl_date or workflow.now().strftime("%Y-%m-%d")
        workflow.logger.info("Transform starting dt=%s", dt)

        bronze: LoadBronzeResult = await workflow.execute_activity(
            load_bronze_activity,
            dt,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=_DB_RETRY,
        )

        await workflow.execute_activity(
            ensure_partition_activity,
            dt,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=_DB_RETRY,
        )

        await workflow.execute_activity(
            dbt_build_activity,
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        await workflow.execute_activity(
            refresh_matviews_activity,
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=_DB_RETRY,
        )

        return TransformResult(
            bronze_inserted=bronze.inserted,
            bronze_scanned=bronze.scanned,
        )


# ─────────────────────────────────── ML ─────────────────────────────────────

@dataclass
class MLResult:
    similarity_items: int
    similarity_pairs: int
    embedded: int


@workflow.defn(name="ML")
class MLWorkflow:
    """Recompute item-item similarity + re-embed vehicles to Qdrant.

    The two activities are independent → run them concurrently.
    ``crawl_date`` (YYYY-MM-DD) is forwarded to embed_vehicles_activity as the
    ``since_date`` watermark so only vehicles updated that day are re-embedded.
    When omitted the workflow uses today's date (workflow.now()).
    """

    @workflow.run
    async def run(self, crawl_date: str = "") -> MLResult:
        dt = crawl_date or workflow.now().strftime("%Y-%m-%d")
        workflow.logger.info("ML starting dt=%s", dt)

        sim_task = workflow.execute_activity(
            compute_item_similarity_activity,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=_DB_RETRY,
        )
        embed_task = workflow.execute_activity(
            embed_vehicles_activity,
            dt,
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        sim: SimilarityResult
        embed: EmbedResult
        sim, embed = await asyncio.gather(sim_task, embed_task)

        return MLResult(
            similarity_items=sim.items,
            similarity_pairs=sim.pairs,
            embedded=embed.embedded,
        )


# ───────────────────────────── Weekly pipeline ──────────────────────────────

@dataclass
class WeeklyPipelineResult:
    crawl_date: str
    crawl: WeeklyCrawlResult
    transform: TransformResult
    ml: MLResult


@workflow.defn(name="WeeklyPipeline")
class WeeklyPipelineWorkflow:
    """The scheduled chain: crawl → transform → ml, run as child workflows.

    Child workflows route to the right worker by task queue: WeeklyCrawl on the
    host queue (needs Chrome), Transform + ML on the Dockerized pipeline queue.
    Fail-stop: a failed child raises and aborts the rest, so transform/ml never
    run on a failed crawl. All three share the parent's crawl_date so the GCS
    dt= slice, the bronze load, and the embed watermark agree.
    """

    @workflow.run
    async def run(self, page: int = 1) -> WeeklyPipelineResult:
        crawl_date = workflow.now().strftime("%Y-%m-%d")
        workflow.logger.info("WeeklyPipeline starting dt=%s page=%s", crawl_date, page)

        # Running markdown summary, shown in the UI "Details" panel and updated
        # after each step so progress is readable without digging into History.
        steps = {
            "1. Crawl (page %s)" % page: "⏳ running…",
            "2. Transform": "⬜ pending",
            "3. ML / embeddings": "⬜ pending",
        }

        def _render() -> str:
            lines = [f"### Weekly pipeline — `{crawl_date}`", "", "| Step | Status |", "|---|---|"]
            lines += [f"| {k} | {v} |" for k, v in steps.items()]
            return "\n".join(lines)

        workflow.set_current_details(_render())

        # 1. Crawl — on the host worker (Chrome + Xvfb).
        crawl: WeeklyCrawlResult = await workflow.execute_child_workflow(
            WeeklyCrawlWorkflow.run,
            WeeklyCrawlInput(page=page, crawl_date=crawl_date),
            id=f"weekly-crawl-{crawl_date}",
            task_queue=CRAWL_TASK_QUEUE,
        )
        steps["1. Crawl (page %s)" % page] = (
            f"✅ {crawl.link_count} links · scraped {crawl.detail_done} "
            f"(fail {crawl.detail_fail}, skip {crawl.detail_skip}) · "
            f"uploaded {crawl.json_uploaded} json / {crawl.images_uploaded} imgs"
        )
        steps["2. Transform"] = "⏳ running…"
        workflow.set_current_details(_render())

        # 2. Transform — on the Docker pipeline worker.
        transform: TransformResult = await workflow.execute_child_workflow(
            TransformWorkflow.run,
            crawl_date,
            id=f"weekly-transform-{crawl_date}",
            task_queue=PIPELINE_TASK_QUEUE,
        )
        steps["2. Transform"] = (
            f"✅ bronze +{transform.bronze_inserted} inserted "
            f"({transform.bronze_scanned} scanned) → dbt + matviews"
        )
        steps["3. ML / embeddings"] = "⏳ running…"
        workflow.set_current_details(_render())

        # 3. ML — on the Docker pipeline worker.
        ml: MLResult = await workflow.execute_child_workflow(
            MLWorkflow.run,
            crawl_date,
            id=f"weekly-ml-{crawl_date}",
            task_queue=PIPELINE_TASK_QUEUE,
        )
        steps["3. ML / embeddings"] = (
            f"✅ similarity {ml.similarity_items} items / {ml.similarity_pairs} pairs · "
            f"embedded {ml.embedded} vehicles"
        )
        workflow.set_current_details(_render())

        return WeeklyPipelineResult(
            crawl_date=crawl_date, crawl=crawl, transform=transform, ml=ml
        )
