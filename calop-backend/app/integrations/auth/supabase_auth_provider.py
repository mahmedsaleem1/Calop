import uuid

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import Settings
from app.core.exceptions import AuthError
from app.integrations.auth.auth_provider import AuthProvider, AuthSession, AuthUser


class SupabaseAuthProvider(AuthProvider):
    def __init__(self, settings: Settings):
        base_url = settings.supabase_url.rstrip("/")
        self._issuer = f"{base_url}/auth/v1"
        self._request_headers = {"apikey": settings.supabase_publishable_key}
        self._jwks_client = PyJWKClient(f"{self._issuer}/.well-known/jwks.json", cache_keys=True)

    # ---- token verification (local, via the project's public keys) ----
    def verify_token(self, token: str) -> AuthUser:
        try:
            algorithm = jwt.get_unverified_header(token).get("alg")
            if algorithm not in ("ES256", "RS256"):
                raise AuthError("Unsupported token algorithm")
            signing_key = self._jwks_client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, signing_key, algorithms=[algorithm], audience="authenticated", issuer=self._issuer
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
                f"{self._issuer}{path}", json=json, params=params, headers=self._request_headers, timeout=10
            )
        except httpx.HTTPError:
            raise AuthError("Auth service unavailable", 503)

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
            return body.get("msg") or body.get("error_description") or body.get("message") or "Request failed"
        except ValueError:
            return "Request failed"

    @staticmethod
    def _parse_session(data: dict) -> AuthSession:
        user = data["user"]
        return AuthSession(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_in=int(data["expires_in"]),
            user=AuthUser(id=uuid.UUID(user["id"]), email=user.get("email")),
        )

    def sign_up(self, email: str, password: str) -> AuthSession | None:
        response = self._post("/signup", {"email": email, "password": password})
        if response.status_code >= 400:
            raise AuthError(self._extract_error_message(response), 400)
        data = response.json()
        return self._parse_session(data) if "access_token" in data else None

    def sign_in(self, email: str, password: str) -> AuthSession:
        response = self._post("/token", {"email": email, "password": password}, {"grant_type": "password"})
        if response.status_code >= 500:
            raise AuthError("Auth service unavailable", 503)
        if response.status_code >= 400:
            raise AuthError("Invalid email or password", 401)
        return self._parse_session(response.json())

    def refresh(self, refresh_token: str) -> AuthSession:
        response = self._post("/token", {"refresh_token": refresh_token}, {"grant_type": "refresh_token"})
        if response.status_code >= 500:
            raise AuthError("Auth service unavailable", 503)
        if response.status_code >= 400:
            raise AuthError("Invalid refresh token", 401)
        return self._parse_session(response.json())
