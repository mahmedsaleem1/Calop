import uuid

import httpx
import jwt
from jwt import PyJWKClient

from app.auth.base import AuthError, AuthProvider, AuthSession, AuthUser
from app.config import Settings


class SupabaseAuthProvider(AuthProvider):
    def __init__(self, settings: Settings):
        self._base = settings.supabase_url.rstrip("/")
        self._issuer = f"{self._base}/auth/v1"
        self._headers = {"apikey": settings.supabase_publishable_key}
        self._jwks = PyJWKClient(f"{self._issuer}/.well-known/jwks.json", cache_keys=True)

    # ---- token verification (local, via the project's public keys) ----
    def verify_token(self, token: str) -> AuthUser:
        try:
            alg = jwt.get_unverified_header(token).get("alg")
            if alg not in ("ES256", "RS256"):
                raise AuthError("Unsupported token algorithm")
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=[alg], audience="authenticated", issuer=self._issuer
            )
            return AuthUser(id=uuid.UUID(claims["sub"]), email=claims.get("email"))
        except AuthError:
            raise
        except jwt.PyJWKClientConnectionError:
            raise AuthError("Auth service unavailable", 503)
        except Exception:
            raise AuthError("Invalid or expired token")

    # ---- calls to Supabase Auth ----
    def _post(self, path: str, json: dict, params: dict | None = None) -> httpx.Response:
        try:
            return httpx.post(
                f"{self._issuer}{path}", json=json, params=params, headers=self._headers, timeout=10
            )
        except httpx.HTTPError:
            raise AuthError("Auth service unavailable", 503)

    @staticmethod
    def _message(resp: httpx.Response) -> str:
        try:
            body = resp.json()
            return body.get("msg") or body.get("error_description") or body.get("message") or "Request failed"
        except ValueError:
            return "Request failed"

    @staticmethod
    def _session(data: dict) -> AuthSession:
        user = data["user"]
        return AuthSession(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_in=int(data["expires_in"]),
            user=AuthUser(id=uuid.UUID(user["id"]), email=user.get("email")),
        )

    def sign_up(self, email: str, password: str) -> AuthSession | None:
        resp = self._post("/signup", {"email": email, "password": password})
        if resp.status_code >= 400:
            raise AuthError(self._message(resp), 400)
        data = resp.json()
        return self._session(data) if "access_token" in data else None

    def sign_in(self, email: str, password: str) -> AuthSession:
        resp = self._post("/token", {"email": email, "password": password}, {"grant_type": "password"})
        if resp.status_code >= 500:
            raise AuthError("Auth service unavailable", 503)
        if resp.status_code >= 400:
            raise AuthError("Invalid email or password", 401)
        return self._session(resp.json())

    def refresh(self, refresh_token: str) -> AuthSession:
        resp = self._post("/token", {"refresh_token": refresh_token}, {"grant_type": "refresh_token"})
        if resp.status_code >= 500:
            raise AuthError("Auth service unavailable", 503)
        if resp.status_code >= 400:
            raise AuthError("Invalid refresh token", 401)
        return self._session(resp.json())
