from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.dependencies import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import report_service
from app.views.report_views import DailyReportOut, WeeklyReportOut

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/daily", response_model=DailyReportOut)
def get_daily_report(
    day: date | None = Query(None, alias="date"), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Logged intake against the target for one day (default: today in the user's timezone)."""
    return report_service.daily_report(db, current_user, day)


@router.get("/weekly", response_model=WeeklyReportOut)
def get_weekly_report(
    week_start: date | None = Query(None), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Seven daily summaries with averages, weights and goal progress (default: the current week, Monday first)."""
    return report_service.weekly_report(db, current_user, week_start)
