"""In-memory WebSocket hub. Needs the server to run as ONE process (no --workers)."""
import asyncio
import logging
import uuid

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class Hub:
    def __init__(self) -> None:
        self._sockets: dict[uuid.UUID, set[WebSocket]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        self._loop = loop

    def register(self, user_id: uuid.UUID, socket: WebSocket) -> None:
        self._sockets.setdefault(user_id, set()).add(socket)

    def unregister(self, user_id: uuid.UUID, socket: WebSocket) -> None:
        sockets = self._sockets.get(user_id)
        if sockets is not None:
            sockets.discard(socket)
            if not sockets:
                self._sockets.pop(user_id, None)

    async def _send_all(self, user_id: uuid.UUID, message: dict) -> None:
        for socket in list(self._sockets.get(user_id, ())):
            try:
                await socket.send_json(message)
            except Exception:  # a dead socket: drop it
                self.unregister(user_id, socket)

    def publish(self, user_id: uuid.UUID, message: dict) -> None:
        """Thread-safe: request threads and worker threads may call this."""
        loop = self._loop
        if loop is None or user_id not in self._sockets:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._send_all(user_id, message), loop)
        except RuntimeError:
            logger.warning("Could not publish: event loop is closed")


hub = Hub()
