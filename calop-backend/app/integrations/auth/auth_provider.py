import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AuthUser:
    id: uuid.UUID
    email: str | None


@dataclass
class AuthSession:
    access_token: str
    refresh_token: str
    expires_in: int
    user: AuthUser


class AuthProvider(ABC):
    """Everything the app needs from an auth system. Today: Supabase Auth.
    After migration: a FastAPI/JWT implementation of this same interface."""

    @abstractmethod
    def verify_token(self, token: str) -> AuthUser: ...

    @abstractmethod
    def sign_up(self, email: str, password: str) -> AuthSession | None:
        """Returns None when the provider requires email confirmation first."""

    @abstractmethod
    def sign_in(self, email: str, password: str) -> AuthSession: ...

    @abstractmethod
    def refresh(self, refresh_token: str) -> AuthSession: ...
