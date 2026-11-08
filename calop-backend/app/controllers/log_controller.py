import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.dependencies import get_current_user
from app.core.database import get_db
from app.models import Capture, User
from app.services import log_service, presenters
from app.views.log_views import EntryFoodUpdate, EntryList, EntryOut

router = APIRouter(prefix="/api/v1/log-entries", tags=["log"])


@router.get("", response_model=EntryList)
def list_log_entries(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entries = log_service.list_entries(db, current_user, date_from, date_to)
    return EntryList(items=presenters.entries_out(db, entries))


@router.get("/{entry_id}", response_model=EntryOut)
def get_log_entry(entry_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return presenters.entries_out(db, [log_service.get_owned_entry(db, current_user, entry_id)])[0]


@router.patch("/{entry_id}", response_model=EntryOut)
def correct_log_entry_food(
    entry_id: uuid.UUID, body: EntryFoodUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """'Wrong food?': changes only the food. The weight and time stay."""
    entry, capture = log_service.correct_entry_food(db, current_user, entry_id, body.food_code)
    presenters.publish_capture(db, db.get(Capture, capture.id))
    return presenters.entries_out(db, [entry])[0]
