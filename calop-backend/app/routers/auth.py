from fastapi import APIRouter, Depends, HTTPException

from app.auth.base import AuthError, AuthProvider, AuthSession
from app.deps import get_auth_provider, get_current_user
from app.models import User
from app.schemas import LoginIn, RefreshIn, SessionOut, SignUpIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _out(s: AuthSession) -> SessionOut:
    return SessionOut(
        access_token=s.access_token,
        refresh_token=s.refresh_token,
        expires_in=s.expires_in,
        user=UserOut.model_validate(s.user),
    )


@router.post("/signup")
def signup(body: SignUpIn, provider: AuthProvider = Depends(get_auth_provider)):
    try:
        session = provider.sign_up(body.email, body.password)
    except AuthError as e:
        raise HTTPException(e.status_code, e.message)
    if session is None:
        return {"detail": "Check your email to confirm your account, then log in."}
    return _out(session)


@router.post("/login", response_model=SessionOut)
def login(body: LoginIn, provider: AuthProvider = Depends(get_auth_provider)):
    try:
        return _out(provider.sign_in(body.email, body.password))
    except AuthError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/refresh", response_model=SessionOut)
def refresh(body: RefreshIn, provider: AuthProvider = Depends(get_auth_provider)):
    try:
        return _out(provider.refresh(body.refresh_token))
    except AuthError as e:
        raise HTTPException(e.status_code, e.message)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
