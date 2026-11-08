"""The `upload_image` job: copy the local photo to Cloudinary, then delete the local file."""
import logging
import time
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.storage.image_storage import ImageStorage, StorageError
from app.models import Capture, Job
from app.services import job_service
from app.services.event_service import record_event
from app.services.presenters import publish_capture

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 10
RETRY_SCHEDULE_SECONDS = (5, 15, 30, 60, 120)  # then doubling, capped at 300


def local_path_for(settings: Settings, capture_id: uuid.UUID) -> Path:
    return Path(settings.local_image_dir).resolve() / f"{capture_id}.jpg"


def delete_local_file(path: str | None) -> None:
    """Deletes a local photo. On Windows a file another thread is still reading can't be removed yet,
    so a few quick retries are made before giving up with a warning."""
    if not path:
        return
    for attempt in range(5):
        try:
            Path(path).unlink(missing_ok=True)
            return
        except OSError:
            time.sleep(0.2)
    logger.warning("Could not delete local image %s", path)


def process_job(db: Session, job: Job, image_storage: ImageStorage, settings: Settings) -> None:
    capture = db.get(Capture, job.capture_id)
    if capture is None:  # deleted while the job waited: remove the leftover file
        delete_local_file(str(local_path_for(settings, job.capture_id)))
        job_service.finish_without_work(db, job)
        return
    if capture.image_status == "uploaded":
        job_service.finish_without_work(db, job)
        return
    path = capture.image_local_path
    try:
        data = Path(path).read_bytes() if path else None
        if data is None:
            raise StorageError("The local image file is missing")
        stored = image_storage.upload(data)
    except (StorageError, OSError) as exc:
        message = str(exc)
        exhausted = job_service.retry_later(job, job_service.delay_from(RETRY_SCHEDULE_SECONDS, job.attempts), message)
        if exhausted:
            capture.image_status = "upload_failed"
            record_event(db, "system", None, "capture.image_upload_failed", "capture", capture.id,
                         {"user_id": str(capture.user_id), "error": message[:300]})
        db.commit()
        if exhausted:
            publish_capture(db, capture)
        return

    capture.image_url = stored.url
    capture.image_public_id = stored.public_id
    capture.image_status = "uploaded"
    capture.image_local_path = None
    record_event(db, "system", None, "capture.image_uploaded", "capture", capture.id, {"user_id": str(capture.user_id)})
    job_service.mark_succeeded(job)
    db.commit()
    delete_local_file(path)
    publish_capture(db, capture)
