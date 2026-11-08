"""Background worker: threads that claim jobs from the database and run them.
Run the server as ONE process (no --workers): the worker and the WebSocket hub live in memory."""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from app.core import wakeup
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Job
from app.services import image_service, job_service, recognition_service

logger = logging.getLogger(__name__)

IDLE_WAIT_SECONDS = 1.0


def _run_job(db, job: Job) -> None:
    # Imported here: the dependency getters live in the controllers package, which imports the services.
    from app.controllers.dependencies import get_food_recognizer, get_image_storage

    settings = get_settings()
    if job.kind == "recognize_capture":
        recognition_service.process_job(db, job, get_food_recognizer(), settings)
    elif job.kind == "upload_image":
        image_service.process_job(db, job, get_image_storage(), settings)
    else:
        raise ValueError(f"Unknown job kind {job.kind!r}")


def process_next_job() -> bool:
    """Claims and runs one job. Returns False when the queue had nothing ready."""
    with SessionLocal() as db:
        job = job_service.claim_next(db)
        if job is None:
            return False
        job_id = job.id
        try:
            _run_job(db, job)
        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            db.rollback()
            try:
                failed = db.get(Job, job_id)
                if failed is not None:  # gone if its capture was deleted meanwhile
                    schedule = (5, 15, 60)
                    job_service.retry_later(failed, job_service.delay_from(schedule, failed.attempts), str(exc))
                    db.commit()
            except Exception:
                logger.exception("Could not reschedule job %s", job_id)
                db.rollback()
        return True


class Worker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._executor: ThreadPoolExecutor | None = None

    def start(self) -> None:
        threads = get_settings().worker_threads
        with SessionLocal() as db:
            reset = job_service.reset_stale_running(db)
        if reset:
            logger.info("Requeued %s jobs left running by a crash", reset)
        self._stop.clear()
        self._executor = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="calop-worker")
        for _ in range(threads):
            self._executor.submit(self._loop)
        wakeup.wake()

    def stop(self) -> None:
        self._stop.set()
        wakeup.wake()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = process_next_job()
            except Exception:
                logger.exception("Worker loop error")
                worked = False
            if not worked:
                if wakeup.job_available.wait(IDLE_WAIT_SECONDS):
                    wakeup.job_available.clear()


worker = Worker()
