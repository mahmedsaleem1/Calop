from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.controllers import auth_controller, capture_controller, device_controller, health_controller
from app.core.config import get_settings
from app.core.exceptions import ApplicationError

app = FastAPI(title="Calop API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in get_settings().cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_controller.router)
app.include_router(device_controller.router)
app.include_router(capture_controller.router)
app.include_router(health_controller.router)


@app.exception_handler(ApplicationError)
async def handle_application_error(request: Request, error: ApplicationError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"detail": error.message})
