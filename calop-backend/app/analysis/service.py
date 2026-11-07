import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.analysis.base import AnalysisError, FoodAnalyzer
from app.config import get_settings
from app.db import SessionLocal
from app.models import Analysis, Capture

log = logging.getLogger(__name__)
CONFIDENCE_THRESHOLD = 0.5


def download_image(url: str) -> bytes:
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        return r.content
    except httpx.HTTPError as e:
        raise AnalysisError(f"Could not download image: {type(e).__name__}") from e


def run_analysis(capture_id: uuid.UUID, analyzer: FoodAnalyzer, image: bytes | None = None) -> None:
    """Runs in the background after the response is sent. Uses its own DB session."""
    db = SessionLocal()
    try:
        capture = db.get(Capture, capture_id)
        analysis = db.scalar(select(Analysis).where(Analysis.capture_id == capture_id))
        if capture is None or analysis is None:
            return
        try:
            if capture.weight_g < get_settings().min_analysis_weight_g:
                analysis.status = "SKIPPED"
                analysis.notes = "Nothing on the scale (weight below minimum)."
            else:
                result = analyzer.analyze(image or download_image(capture.image_url), capture.weight_g)
                analysis.provider = analyzer.name
                analysis.label = result.label
                analysis.confidence = result.confidence
                analysis.calories = result.calories
                analysis.protein_g = result.protein_g
                analysis.carbs_g = result.carbs_g
                analysis.fat_g = result.fat_g
                analysis.notes = result.notes
                analysis.error = None
                analysis.status = "IDENTIFIED" if result.confidence >= CONFIDENCE_THRESHOLD else "LOW_CONFIDENCE"
        except AnalysisError as e:
            analysis.status = "FAILED"
            analysis.error = str(e)[:500]
        except Exception:
            log.exception("Unexpected analysis error for capture %s", capture_id)
            analysis.status = "FAILED"
            analysis.error = "Unexpected error"
        analysis.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
