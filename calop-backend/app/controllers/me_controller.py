from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.dependencies import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import profile_service
from app.views.me_views import (
    ActivityOut, GoalIn, GoalOut, GoalSetOut, MeOut, OnboardingIn, OnboardingOut, ProfileOut, ProfileUpdate,
    ProfileUpdateOut, TargetOut, WeightEntryOut, WeightIn, WeightRecordedOut, build_me, warnings_out,
)

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("", response_model=MeOut)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_me(
        current_user,
        profile_service.get_profile(db, current_user.id),
        profile_service.latest_weight(db, current_user.id),
        profile_service.active_goal(db, current_user.id),
        profile_service.latest_target(db, current_user.id),
    )


@router.post("/onboarding", response_model=OnboardingOut)
def complete_onboarding(body: OnboardingIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The questionnaire, answered once after signup. Warnings never block: the app shows the suggested date."""
    profile, goal, target, warnings = profile_service.complete_onboarding(db, current_user, body)
    return OnboardingOut(
        profile=ProfileOut.model_validate(profile), goal=GoalOut.model_validate(goal),
        target=TargetOut.model_validate(target), warnings=warnings_out(warnings),
    )


@router.patch("/profile", response_model=ProfileUpdateOut)
def update_profile(body: ProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile, target, warnings = profile_service.update_profile(
        db, current_user, body.model_dump(exclude_unset=True, exclude_none=True)
    )
    return ProfileUpdateOut(
        profile=ProfileOut.model_validate(profile), target=TargetOut.model_validate(target),
        warnings=warnings_out(warnings),
    )


@router.post("/weights", response_model=WeightRecordedOut, status_code=201)
def record_weight(body: WeightIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry, target, warnings = profile_service.add_weight(db, current_user, body.weight_kg)
    return WeightRecordedOut(
        entry=WeightEntryOut.model_validate(entry), target=TargetOut.model_validate(target),
        warnings=warnings_out(warnings),
    )


@router.get("/weights", response_model=list[WeightEntryOut])
def list_weights(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return profile_service.list_weights(db, current_user, date_from, date_to)


@router.put("/goal", response_model=GoalSetOut)
def replace_goal(body: GoalIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    goal, target, warnings = profile_service.set_goal(db, current_user, body.target_weight_kg, body.target_date)
    return GoalSetOut(
        goal=GoalOut.model_validate(goal), target=TargetOut.model_validate(target), warnings=warnings_out(warnings)
    )


@router.get("/activity", response_model=list[ActivityOut])
def list_activity(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return profile_service.list_activity(db, current_user, limit, offset)
