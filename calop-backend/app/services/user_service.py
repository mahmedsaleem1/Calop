from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.auth.auth_provider import AuthUser
from app.models import User


def get_or_create_user(db: Session, auth_user: AuthUser) -> User:
    user = db.get(User, auth_user.id)
    if user is None:  # first request from this user: create the app-side row
        user = User(id=auth_user.id, email=auth_user.email)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.get(User, auth_user.id)
    return user
