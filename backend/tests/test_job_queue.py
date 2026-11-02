"""INDEX_WORKERS=external: the API queues jobs in the database and worker processes run them"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.models.job import Job
from app.models.repository import Repository
from app.services import repository_service as jobs
from app.worker import run_one


@pytest.fixture
def external(db_session, job_sessions, monkeypatch):
    monkeypatch.setattr(get_settings(), "index_workers", "external")
    return db_session


def add_repository(db, name="o/a", status="completed"):
    repo = Repository(name=name, url=f"https://github.com/{name}", status=status)
    db.add(repo)
    db.commit()
    return repo


def test_external_mode_queues_instead_of_running(external):
    repo = add_repository(external)

    assert jobs.start_processing(repo.id, force_reprocess=True, incremental=True) is None

    [job] = external.query(Job).all()
    assert (job.repository_id, job.force_reprocess, job.incremental, job.claimed_by) == (repo.id, True, True, None)
    assert jobs.is_processing(repo.id)
    with pytest.raises(jobs.RepositoryBusyError):
        jobs.start_processing(repo.id)


def test_inline_mode_never_reads_the_jobs_table(db_session, job_sessions):
    repo = add_repository(db_session)
    db_session.add(Job(repository_id=repo.id, force_reprocess=False, incremental=False))
    db_session.commit()

    assert not jobs.is_processing(repo.id)  # inline: only this process's tasks count


def test_a_job_is_claimed_by_exactly_one_worker(external):
    repo = add_repository(external)
    jobs.start_processing(repo.id)

    first, second = jobs.claim_job("host:1"), jobs.claim_job("host:2")

    assert first is not None and first.claimed_by == "host:1" and second is None


def test_a_silent_workers_job_is_queued_again_as_a_full_run(external):
    repo = add_repository(external)
    jobs.start_processing(repo.id, force_reprocess=True, incremental=True)
    jobs.claim_job("dead:1")
    external.query(Job).update({"heartbeat_at": datetime.now(UTC) - timedelta(seconds=jobs.JOB_STALE_SECONDS + 5)})
    external.commit()

    job = jobs.claim_job("live:2")

    assert (job.claimed_by, job.incremental) == ("live:2", False)


async def test_a_worker_runs_a_job_then_removes_it(external, monkeypatch):
    repo = add_repository(external)
    jobs.start_processing(repo.id, force_reprocess=True, incremental=True)
    ran = []

    async def fake_run(repository_id, force_reprocess, incremental=False):
        ran.append((repository_id, force_reprocess, incremental))

    monkeypatch.setattr(jobs, "_run_job", fake_run)

    assert await run_one("host:1") is True
    assert ran == [(repo.id, True, True)]
    assert external.query(Job).count() == 0
    assert await run_one("host:1") is False


async def test_a_failing_job_is_still_removed(external, monkeypatch):
    repo = add_repository(external)
    jobs.start_processing(repo.id)

    async def boom(*args):
        raise RuntimeError("crash")

    monkeypatch.setattr(jobs, "_run_job", boom)
    with pytest.raises(RuntimeError):
        await run_one("host:1")
    assert external.query(Job).count() == 0


async def test_a_failed_heartbeat_does_not_stop_the_next_ones(external, monkeypatch):
    # Without later heartbeats the job looks abandoned and a second worker runs it too
    repo = add_repository(external)
    jobs.start_processing(repo.id)
    beats = []

    def flaky_heartbeat(job_id, worker):
        beats.append(job_id)
        if len(beats) == 1:
            raise RuntimeError("database connection lost")

    async def long_run(*args):
        while len(beats) < 2:
            await asyncio.sleep(0)

    monkeypatch.setattr(jobs, "JOB_HEARTBEAT_SECONDS", 0)
    monkeypatch.setattr(jobs, "heartbeat_job", flaky_heartbeat)
    monkeypatch.setattr(jobs, "_run_job", long_run)

    assert await asyncio.wait_for(run_one("host:1"), 5) is True
    assert len(beats) >= 2


def test_recovery_leaves_runs_that_workers_own(external, monkeypatch):
    owned = add_repository(external, "o/owned", status="processing")
    orphan = add_repository(external, "o/orphan", status="processing")
    external.add(Job(repository_id=owned.id, force_reprocess=True, incremental=False, claimed_by="host:1"))
    external.commit()
    started = []
    monkeypatch.setattr(jobs, "start_processing", lambda rid, **kw: started.append(rid))

    assert jobs.recover_interrupted_jobs(external) == 1
    assert started == [orphan.id]


async def test_the_relay_sends_progress_and_the_final_status(external, monkeypatch):
    from app.services.websocket_service import websocket_manager

    repo = add_repository(external, status="processing")
    sent = []

    async def record(**kwargs):
        sent.append((kwargs["status"], kwargs["processed_files"]))
        if len(sent) == 1:
            repo.status, repo.processed_files = "completed", 3
            external.commit()
        else:
            raise asyncio.CancelledError

    monkeypatch.setattr(websocket_manager, "send_repository_status", record)
    with pytest.raises(asyncio.CancelledError):
        await jobs.relay_progress(interval=0.001)
    assert sent == [("processing", 0), ("completed", 3)]
