import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.integrations.auth.auth_provider import AuthSession


class SignUpIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str | None


class SessionOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
    user: UserOut


def build_session_out(session: AuthSession) -> SessionOut:
    return SessionOut(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
        user=UserOut.model_validate(session.user),
    )
