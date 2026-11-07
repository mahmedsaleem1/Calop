"""Importing this package registers every table on Base.metadata (Alembic relies on it)."""
from app.models.capture import Capture
from app.models.device import Device
from app.models.user import User

__all__ = ["Capture", "Device", "User"]
