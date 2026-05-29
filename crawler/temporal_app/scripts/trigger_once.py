"""Manually start one workflow run — smoke-test before enabling schedules.

Usage:
    python -m temporal_app.scripts.trigger_once pipeline  # full chain (recommended)
    python -m temporal_app.scripts.trigger_once crawl     # WeeklyCrawl page 1 only
    python -m temporal_app.scripts.trigger_once transform # Transform only
    python -m temporal_app.scripts.trigger_once ml        # ML only
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from temporal_app.client import connect
from temporal_app.shared import (
    CRAWL_TASK_QUEUE,
    PIPELINE_TASK_QUEUE,
    WORKFLOW_ID_PREFIX,
)
from temporal_app.workflows import (
    MLWorkflow,
    TransformWorkflow,
    WeeklyCrawlInput,
    WeeklyCrawlWorkflow,
    WeeklyPipelineWorkflow,
)

# job -> (run_fn, arg, label, task_queue)
# The full pipeline is started on the pipeline queue; it spawns the crawl child
# onto the crawler queue itself.
_JOBS = {
    "pipeline": (WeeklyPipelineWorkflow.run, 1, "pipeline", PIPELINE_TASK_QUEUE),
    "crawl": (WeeklyCrawlWorkflow.run, WeeklyCrawlInput(page=1),
              "crawl", CRAWL_TASK_QUEUE),
    "transform": (TransformWorkflow.run, None, "transform", PIPELINE_TASK_QUEUE),
    "ml": (MLWorkflow.run, None, "ml", PIPELINE_TASK_QUEUE),
}


async def main() -> None:
    job = sys.argv[1] if len(sys.argv) > 1 else "crawl"
    if job not in _JOBS:
        sys.exit(f"Unknown job '{job}'. Choose: {', '.join(_JOBS)}")

    run_fn, arg, label, task_queue = _JOBS[job]
    client = await connect()

    wf_id = f"{WORKFLOW_ID_PREFIX}-{label}-{uuid.uuid4().hex[:8]}"
    print(f"Starting {job} workflow {wf_id} on {task_queue}")

    start_kwargs = dict(id=wf_id, task_queue=task_queue)
    if arg is not None:
        handle = await client.start_workflow(run_fn, arg, **start_kwargs)
    else:
        handle = await client.start_workflow(run_fn, args=[], **start_kwargs)

    print("Started. Waiting for result...")
    result = await handle.result()
    print(f"DONE: {result}")


if __name__ == "__main__":
    asyncio.run(main())
