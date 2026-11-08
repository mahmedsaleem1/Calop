"""The `recognize_capture` job: ask the AI what food is in the photo, then log it or ask the user."""
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.ai.food_recognizer import (
    FoodRecognizer, RecognizedCandidate, RecognizerError, RecognizerRateLimited,
)
from app.models import Capture, Job, RecognitionCandidate, RecognitionRun
from app.services import food_service, job_service, log_service
from app.services.event_service import record_event
from app.services.presenters import publish_capture

logger = logging.getLogger(__name__)

PROMPT_VERSION = "recognize-v1"
PROMPT = """You identify the single food item in a photo for a nutrition app in Pakistan.
Choose ONLY from the catalog below. Each line is: CODE | name | preparation state | other names.
Return up to 3 candidates, most likely first, with confidence between 0 and 1.
Confidence must reflect real uncertainty; do not give high confidence unless you are sure.
If the food is not in the catalog, return no candidates and put your best name for it in
not_in_catalog_label. Otherwise set not_in_catalog_label to null."""

MAX_ATTEMPTS = 6
RETRY_SCHEDULE_SECONDS = (2, 5, 15, 30, 60)


@dataclass
class Decision:
    candidates: list[tuple[int, str, int | None, float]]  # (rank, returned_code, food_id or None, confidence)
    decision: str  # auto_logged | needs_review
    selected_food_id: int | None
    top_confidence: float | None


def decide(candidates: list[RecognizedCandidate], catalog: dict, threshold: float) -> Decision:
    """Maps returned codes to matchable foods and picks auto-log or review. Pure: no database, no network.
    The first valid candidate at or above the threshold is logged automatically; anything else is reviewed."""
    mapped = []
    for rank, candidate in enumerate(candidates, start=1):
        entry = catalog.get(candidate.code)
        mapped.append((rank, candidate.code, entry.food_id if entry else None, candidate.confidence))
    first_valid = next((m for m in mapped if m[2] is not None), None)
    if first_valid is not None and first_valid[3] >= threshold:
        return Decision(mapped, "auto_logged", first_valid[2], first_valid[3])
    return Decision(mapped, "needs_review", None, first_valid[3] if first_valid else None)


def _confidence(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.001"), ROUND_HALF_UP)


def _load_image(capture: Capture) -> bytes:
    if capture.image_local_path:
        try:
            return Path(capture.image_local_path).read_bytes()
        except FileNotFoundError:
            pass  # the upload job may have just moved it to Cloudinary
    if capture.image_url:
        response = httpx.get(capture.image_url, timeout=20, follow_redirects=True)
        response.raise_for_status()
        return response.content
    raise RecognizerError("The image is not available")


def _fail_run(db: Session, job: Job, capture: Capture, run: RecognitionRun, status: str, code: str, message: str,
              started: float) -> None:
    run.status = status
    run.error_code = code
    run.error_message = message[:1000]
    run.latency_ms = int((time.perf_counter() - started) * 1000)
    run.finished_at = datetime.now(timezone.utc)
    exhausted = job_service.retry_later(job, job_service.delay_from(RETRY_SCHEDULE_SECONDS, job.attempts), message)
    if exhausted:
        locked = log_service.lock_capture(db, capture)
        if locked.status == "identifying":
            locked.status = "failed"
            record_event(db, "ai", None, "capture.recognition_failed", "capture", capture.id,
                         {"user_id": str(capture.user_id), "error_code": code})
    db.commit()
    if exhausted:
        publish_capture(db, capture)


def process_job(db: Session, job: Job, recognizer: FoodRecognizer, settings: Settings) -> None:
    capture = db.get(Capture, job.capture_id)
    if capture is None or capture.status != "identifying":
        job_service.finish_without_work(db, job)
        return

    run = RecognitionRun(
        capture_id=capture.id, attempt=job.attempts, provider=settings.vision_ai_provider,
        model=settings.vision_ai_model, prompt_version=PROMPT_VERSION, status="running",
    )
    db.add(run)
    db.commit()

    started = time.perf_counter()
    try:
        image = _load_image(capture)
        output = recognizer.recognize(image, food_service.catalog_text(), PROMPT)
    except RecognizerRateLimited as exc:
        _fail_run(db, job, capture, run, "rate_limited", "rate_limited", str(exc), started)
        return
    except (RecognizerError, httpx.HTTPError) as exc:
        _fail_run(db, job, capture, run, "failed", "recognizer_error", str(exc), started)
        return

    decision = decide(output.candidates, food_service.catalog_by_code(), settings.vision_auto_log_threshold)
    for rank, code, food_id, confidence in decision.candidates:
        db.add(RecognitionCandidate(
            run_id=run.id, rank=rank, returned_code=code[:100], food_id=food_id, confidence=_confidence(confidence)
        ))
    run.status = "succeeded"
    run.decision = decision.decision
    run.top_confidence = _confidence(decision.top_confidence) if decision.top_confidence is not None else None
    run.latency_ms = int((time.perf_counter() - started) * 1000)
    run.input_tokens, run.output_tokens = output.input_tokens, output.output_tokens
    run.raw_response = output.raw_response
    run.finished_at = datetime.now(timezone.utc)

    capture = log_service.lock_capture(db, capture)
    if capture.status == "identifying":  # the user may have discarded or reprocessed it meanwhile
        label = (output.not_in_catalog_label or "").strip()
        capture.not_in_catalog_label = label[:255] or None
        capture.recognized_at = datetime.now(timezone.utc)
        if decision.decision == "auto_logged":
            capture.selected_food_id = decision.selected_food_id
            log_service.try_log(db, capture, "auto", "ai", None)
        else:
            capture.status = "needs_review"
        record_event(db, "ai", None, "capture.recognized", "capture", capture.id, {
            "user_id": str(capture.user_id), "run_id": str(run.id), "decision": decision.decision,
            "top_confidence": decision.top_confidence,
        })
    job_service.mark_succeeded(job)
    db.commit()
    publish_capture(db, capture)
