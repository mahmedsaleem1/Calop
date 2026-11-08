"""A small job queue stored in Postgres. Workers claim jobs with FOR UPDATE SKIP LOCKED."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.models import Job

STALE_RUNNING_SECONDS = 300


def enqueue(db: Session, kind: str, capture_id: uuid.UUID, max_attempts: int) -> Job:
    """Adds a job to the session without committing, so it commits with the capture change."""
    job = Job(kind=kind, capture_id=capture_id, status="queued", attempts=0, max_attempts=max_attempts)
    db.add(job)
    return job


def claim_next(db: Session) -> Job | None:
    job = db.scalar(
        select(Job).where(Job.status == "queued", Job.run_after <= func.now())
        .order_by(Job.id).limit(1).with_for_update(skip_locked=True)
    )
    if job is None:
        db.rollback()
        return None
    job.status = "running"
    job.locked_at = datetime.now(timezone.utc)
    job.attempts += 1
    db.commit()
    return job


def mark_succeeded(job: Job) -> None:
    job.status = "succeeded"
    job.last_error = None
    job.locked_at = None


def finish_without_work(db: Session, job: Job) -> None:
    """Marks the job done when there is nothing left to do. The job row itself may have been deleted
    with its capture, so a stale update is fine."""
    try:
        mark_succeeded(job)
        db.commit()
    except (StaleDataError, SQLAlchemyError):
        db.rollback()


def retry_later(job: Job, delay_s: float, error: str) -> bool:
    """Requeues the job if attempts remain. Returns True when attempts are exhausted (the job is now failed)."""
    job.last_error = error[:1000]
    job.locked_at = None
    if job.attempts < job.max_attempts:
        job.status = "queued"
        job.run_after = datetime.now(timezone.utc) + timedelta(seconds=delay_s)
        return False
    job.status = "failed"
    return True


def delay_from(schedule: tuple[int, ...], attempt: int, cap: int = 300) -> int:
    """Delay before the next try after `attempt` failed tries: walks the schedule, then doubles, up to the cap."""
    if attempt <= len(schedule):
        return min(schedule[attempt - 1], cap)
    return min(schedule[-1] * 2 ** (attempt - len(schedule)), cap)


def reset_stale_running(db: Session) -> int:
    """Crash recovery: jobs stuck in 'running' go back to the queue."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_RUNNING_SECONDS)
    result = db.execute(
        update(Job).where(Job.status == "running", Job.locked_at < cutoff).values(status="queued", locked_at=None)
    )
    db.commit()
    return result.rowcount
