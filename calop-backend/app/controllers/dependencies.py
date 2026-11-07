"""FastAPI dependencies shared by the controllers: request authentication and integrations."""
from functools import lru_cache

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AuthError
from app.integrations.auth.auth_provider import AuthProvider
from app.integrations.auth.supabase_auth_provider import SupabaseAuthProvider
from app.integrations.storage.cloudinary_image_storage import CloudinaryImageStorage
from app.integrations.storage.image_storage import ImageStorage
from app.models import Device, User
from app.services import device_service, user_service

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_auth_provider() -> AuthProvider:
    return SupabaseAuthProvider(get_settings())


@lru_cache
def get_image_storage() -> ImageStorage:
    return CloudinaryImageStorage(get_settings())


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    auth_provider: AuthProvider = Depends(get_auth_provider),
) -> User:
    if credentials is None:
        raise AuthError("Not authenticated")
    auth_user = auth_provider.verify_token(credentials.credentials)
    return user_service.get_or_create_user(db, auth_user)


# `x_api_key` is not just a variable name: FastAPI derives the X-API-Key header from it.
def get_authenticated_device(
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Device:
    if not x_api_key:
        raise AuthError("Missing X-API-Key")
    return device_service.authenticate_device(db, x_api_key)
