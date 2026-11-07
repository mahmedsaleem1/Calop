from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.base import AuthError, AuthProvider
from app.analysis.base import FoodAnalyzer
from app.analysis.mistral import MistralAnalyzer
from app.auth.supabase import SupabaseAuthProvider
from app.config import get_settings
from app.db import get_db
from app.models import Device, User
from app.security import hash_api_key
from app.storage.base import ImageStorage
from app.storage.cloudinary_storage import CloudinaryStorage

bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_auth_provider() -> AuthProvider:
    return SupabaseAuthProvider(get_settings())


@lru_cache
def get_storage() -> ImageStorage:
    return CloudinaryStorage(get_settings())


@lru_cache
def get_analyzer() -> FoodAnalyzer | None:
    settings = get_settings()
    return MistralAnalyzer(settings) if settings.mistral_api_key else None


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
    provider: AuthProvider = Depends(get_auth_provider),
) -> User:
    if creds is None:
        raise HTTPException(401, "Not authenticated")
    try:
        auth_user = provider.verify_token(creds.credentials)
    except AuthError as e:
        raise HTTPException(e.status_code, e.message)

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


def get_device(
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Device:
    if not x_api_key:
        raise HTTPException(401, "Missing X-API-Key")
    device = db.scalar(select(Device).where(Device.api_key_hash == hash_api_key(x_api_key)))
    if device is None:
        raise HTTPException(401, "Invalid API key")
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return device
