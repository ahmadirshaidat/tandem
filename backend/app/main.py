import json
import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.ai.router import router as ai_router
from app.auth.router import router as auth_router
from app.channels.gateway import router as socket_router
from app.channels.router import router as channel_router
from app.core.db import engine
from app.tasks.router import router as task_router
from app.workspaces.router import invites
from app.workspaces.router import router as workspace_router

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("tandem")
app = FastAPI(title="Tandem", version="0.1.0")
app.include_router(auth_router)
app.include_router(workspace_router)
app.include_router(invites)
app.include_router(ai_router)
app.include_router(channel_router)
app.include_router(socket_router)
app.include_router(task_router)


def error_response(status: int, message: str, request: Request, details=None, headers=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
                "details": details,
            }
        },
        headers=headers,
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exception: StarletteHTTPException):
    return error_response(
        exception.status_code,
        str(exception.detail),
        request,
        details={"kind": "task_conflict", "current": exception.current_task}
        if hasattr(exception, "current_task")
        else None,
        headers=exception.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exception: RequestValidationError):
    # Never echo rejected input: it can contain passwords or bearer tokens.
    details = [
        {"field": ".".join(map(str, item["loc"][1:])), "message": item["msg"]}
        for item in exception.errors()
    ]
    return error_response(422, "Please check the highlighted fields", request, details)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exception: Exception):
    logger.error(
        json.dumps(
            {
                "event": "request_error",
                "request_id": request.state.request_id,
                "type": type(exception).__name__,
            }
        )
    )
    return error_response(500, "Something went wrong. Please try again.", request)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    start = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    route = request.scope.get("route")
    logger.info(
        json.dumps(
            {
                "event": "request",
                "request_id": request.state.request_id,
                "method": request.method,
                "route": getattr(route, "path", "unmatched"),
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - start) * 1000),
            }
        )
    )
    return response


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM workspaces LIMIT 1"))
            vector = connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            )
        if not vector:
            raise HTTPException(503, "Database extensions are not ready")
    except SQLAlchemyError:
        raise HTTPException(503, "Database is not ready") from None
    return {"status": "ok", "database": "connected", "vector": True}
