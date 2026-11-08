from fastapi import APIRouter

from app.services.health_service import is_database_reachable

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health():
    if is_database_reachable():
        return {"status": "ok", "db": True}
    return {"status": "degraded", "db": False}
