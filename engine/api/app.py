import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from .config import settings
from .db import SessionLocal
from .auth import redis_client
from . import models  # noqa: F401
from .routes import router

app = FastAPI(title=settings.app_name, version="1.0.0", docs_url="/docs" if settings.app_env != "production" else None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list(), allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "X-API-Key", "Idempotency-Key", "Last-Event-ID"])


@app.middleware("http")
async def request_guard(request: Request, call_next):
    request.state.request_time = time.time()
    if request.method in {"POST", "PUT", "PATCH"}:
        raw_length = request.headers.get("content-length", "0") or "0"
        try:
            length = int(raw_length)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length header"}, status_code=400)
        if length < 0:
            return JSONResponse({"detail": "Invalid Content-Length header"}, status_code=400)
        if length > settings.max_request_bytes:
            return JSONResponse({"detail": "Request body is too large"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.on_event("startup")
def startup():
    Path(settings.artifact_root).mkdir(parents=True, exist_ok=True)
    Path(settings.work_root).mkdir(parents=True, exist_ok=True)
    Path(settings.config_snapshot_root).mkdir(parents=True, exist_ok=True)
    Path(settings.signing_root).mkdir(parents=True, exist_ok=True)
    if not settings.api_key_records():
        raise RuntimeError("Configure at least one API key in API_KEYS before starting the API")
    if settings.app_env == "production" and len(settings.signing_master_key) < 48:
        raise RuntimeError("SIGNING_MASTER_KEY must be a stable, high-entropy secret of at least 48 characters")


@app.get("/health/live")
def liveness():
    return {"success": True, "service": "wrapforge-build-api", "state": "live"}


@app.get("/health/ready")
def readiness():
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        redis_client.ping()
    except Exception:
        return JSONResponse({"success": False, "service": "wrapforge-build-api", "state": "not_ready"}, status_code=503)
    return {"success": True, "service": "wrapforge-build-api", "state": "ready"}


@app.get("/health")
def health():
    return readiness()


app.include_router(router, prefix=settings.api_prefix)
