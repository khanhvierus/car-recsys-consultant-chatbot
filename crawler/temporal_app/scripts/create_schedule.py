"""Create / update the weekly schedule on the self-hosted Temporal server.

One schedule, `car-weekly-pipeline`, fires every Monday 02:00 and runs
WeeklyPipelineWorkflow → crawl → transform → ml (fail-stop chain). You run this
script ONCE; Temporal then triggers the pipeline every week with no further
manual action. Idempotent: updates the schedule if it already exists.

The pipeline parent + Transform + ML run on the Dockerized pipeline-worker
(always up). The crawl step is a child workflow on the host queue, so the host
crawler worker (run_worker.sh) must be online when the schedule fires; until it
is, the chain simply waits at the crawl step.
"""
from __future__ import annotations

import asyncio

from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleSpec,
    ScheduleUpdate,
)

from temporal_app.client import connect
from temporal_app.shared import PIPELINE_TASK_QUEUE, WORKFLOW_ID_PREFIX
from temporal_app.workflows import WeeklyPipelineWorkflow

SCHEDULE_ID = "car-weekly-pipeline"
CRON = "0 2 * * 1"   # every Monday 02:00 (server time)


async def main() -> None:
    client = await connect()

    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            WeeklyPipelineWorkflow.run,
            1,                                   # page=1
            id=f"{WORKFLOW_ID_PREFIX}-pipeline",
            task_queue=PIPELINE_TASK_QUEUE,
            static_summary="Weekly crawl → transform → ml (page 1)",
        ),
        spec=ScheduleSpec(cron_expressions=[CRON]),
    )

    try:
        await client.create_schedule(SCHEDULE_ID, schedule)
        print(f"Created schedule {SCHEDULE_ID} ({CRON})")
    except ScheduleAlreadyRunningError:
        handle = client.get_schedule_handle(SCHEDULE_ID)
        await handle.update(lambda _: ScheduleUpdate(schedule=schedule))
        print(f"Updated schedule {SCHEDULE_ID} ({CRON})")


if __name__ == "__main__":
    asyncio.run(main())
