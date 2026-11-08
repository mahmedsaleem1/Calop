import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.controllers import (
    auth_controller, capture_controller, device_api_controller, device_controller, food_controller,
    health_controller, log_controller, me_controller, realtime_controller, report_controller,
)
from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.core.request_context import request_id_var
from app.realtime import hub
from app.worker import worker

logger = logging.getLogger("calop")

HTTP_ERROR_CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
    413: "payload_too_large", 415: "unsupported_media_type", 422: "invalid_input",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.set_loop(asyncio.get_running_loop())
    worker.start()
    try:
        yield
    finally:
        worker.stop()
        hub.set_loop(None)


app = FastAPI(title="Calop API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in get_settings().cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


class RequestIdMiddleware:
    """Gives every request a UUID, available to the whole call chain and returned in X-Request-ID."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = [h for h in message.get("headers", []) if h[0].lower() != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_header)


app.add_middleware(RequestIdMiddleware)

for module in (
    auth_controller, me_controller, device_controller, device_api_controller, capture_controller, log_controller,
    food_controller, report_controller, realtime_controller, health_controller,
):
    app.include_router(module.router)


def _error(request: Request, status_code: int, code: str, message: str, **extra) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or request_id_var.get()
    body = {"error": {"code": code, "message": message, "request_id": request_id, **extra}}
    return JSONResponse(status_code=status_code, content=body, headers={"X-Request-ID": request_id or ""})


@app.exception_handler(ApplicationError)
async def handle_application_error(request: Request, error: ApplicationError) -> JSONResponse:
    return _error(request, error.status_code, error.code, error.message)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    fields = [
        {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"], "type": item["type"]}
        for item in error.errors()
    ]
    return _error(request, 422, "invalid_input", "The request is not valid", fields=fields)


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
    code = HTTP_ERROR_CODES.get(error.status_code, "http_error")
    return _error(request, error.status_code, code, str(error.detail))


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    logger.error("Unhandled error", exc_info=error)
    return _error(request, 500, "internal_error", "Something went wrong")
