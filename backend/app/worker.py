"""Indexing worker for INDEX_WORKERS=external: `python -m app.worker`. Run as many as you like.

Each claims one queued job at a time from the database and runs it as the API process would,
with a heartbeat so that another worker picks the job up again if this one dies. Start the
API first: it applies the database migrations.
"""

import asyncio
import os
import socket

import structlog

from app.core.config import get_settings
from app.services import repository_service as jobs

logger = structlog.get_logger()

IDLE_SECONDS = 2.0


async def run_one(worker: str) -> bool:
    """Run the next queued job, if there is one; True when one ran"""
    job = jobs.claim_job(worker)
    if job is None:
        return False

    async def beat():
        while True:
            await asyncio.sleep(jobs.JOB_HEARTBEAT_SECONDS)
            try:
                jobs.heartbeat_job(job.id, worker)
            except Exception as e:
                # One failed write must not end the heartbeats, or the job is queued again while it runs
                logger.warning("Heartbeat failed", job_id=job.id, error=str(e))

    heartbeat = asyncio.create_task(beat())
    try:
        logger.info("Running job", worker=worker, job_id=job.id, repository_id=job.repository_id)
        await jobs._run_job(job.repository_id, job.force_reprocess, job.incremental)
    finally:
        heartbeat.cancel()
        jobs.finish_job(job.id)
    return True


async def main() -> None:
    worker = f"{socket.gethostname()}:{os.getpid()}"
    if get_settings().index_workers != "external":
        logger.warning("INDEX_WORKERS is not 'external', so the API runs jobs itself and queues none")
    logger.info("Indexing worker started", worker=worker)
    while True:
        if not await run_one(worker):
            await asyncio.sleep(IDLE_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
