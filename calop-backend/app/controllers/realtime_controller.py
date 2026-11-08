import asyncio
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.controllers.dependencies import get_auth_provider
from app.core.exceptions import AuthError
from app.integrations.auth.auth_provider import AuthProvider
from app.realtime import hub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["realtime"])

AUTH_TIMEOUT_SECONDS = 5
CLOSE_UNAUTHORIZED = 4401


@router.websocket("/ws")
async def live_updates(websocket: WebSocket, auth_provider: AuthProvider = Depends(get_auth_provider)):
    """Live capture updates. The first message must be {"type": "auth", "token": "<access token>"} within 5 seconds.
    The app then receives {"type": "capture.updated", "capture": ...} and {"type": "capture.deleted", "id": ...}."""
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), AUTH_TIMEOUT_SECONDS)
        if not isinstance(first, dict) or first.get("type") != "auth" or not isinstance(first.get("token"), str):
            raise ValueError("expected an auth message")
        auth_user = await run_in_threadpool(auth_provider.verify_token, first["token"])
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError, AuthError):
        await _close(websocket, CLOSE_UNAUTHORIZED)
        return

    hub.register(auth_user.id, websocket)
    try:
        await websocket.send_json({"type": "ready"})
        while True:
            try:
                message = await websocket.receive_json()
            except ValueError:
                continue  # not JSON: ignore
            if isinstance(message, dict) and message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        hub.unregister(auth_user.id, websocket)


async def _close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except Exception:
        pass
