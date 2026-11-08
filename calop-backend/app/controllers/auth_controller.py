from fastapi import APIRouter, Depends

from app.controllers.dependencies import get_auth_provider
from app.integrations.auth.auth_provider import AuthProvider
from app.views.auth_views import LoginIn, RefreshIn, SessionOut, SignUpIn, build_session_out

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup")
def signup(body: SignUpIn, auth_provider: AuthProvider = Depends(get_auth_provider)):
    session = auth_provider.sign_up(body.email, body.password)
    if session is None:
        return {"message": "Check your email to confirm your account, then log in."}
    return build_session_out(session)


@router.post("/login", response_model=SessionOut)
def login(body: LoginIn, auth_provider: AuthProvider = Depends(get_auth_provider)):
    return build_session_out(auth_provider.sign_in(body.email, body.password))


@router.post("/refresh", response_model=SessionOut)
def refresh(body: RefreshIn, auth_provider: AuthProvider = Depends(get_auth_provider)):
    return build_session_out(auth_provider.refresh(body.refresh_token))
