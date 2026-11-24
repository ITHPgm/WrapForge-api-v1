import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from engine.api.config import settings
from engine.api.db import SessionLocal
from engine.api.models import Artifact, Build, BuildEvent
from engine.api.storage import store_file


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "mobile-app"


def record(build_id: str, status: str, progress: int, message: str, level: str = "info"):
    with SessionLocal() as db:
        build = db.get(Build, build_id)
        if not build:
            return
        build.status = status
        build.progress = max(0, min(100, int(progress)))
        if status not in {"queued", "failed", "completed", "cancelled"} and build.started_at is None:
            build.started_at = datetime.now(timezone.utc)
        if status in {"failed", "completed", "cancelled"}:
            build.finished_at = datetime.now(timezone.utc)
        if status == "failed":
            build.failure_reason = message[:4000]
        db.add(BuildEvent(build_id=build_id, status=status, progress=build.progress, level=level, message=message[:4000]))
        db.commit()


def save_artifact(build: Build, fmt: str, source: Path):
    if not source.is_file() or source.stat().st_size < 1024:
        raise RuntimeError(f"Build output {source.name} is missing or unexpectedly small")
    if fmt in {"apk", "aab", "ipa"}:
        with source.open("rb") as handle:
            if handle.read(4) != b"PK\x03\x04":
                raise RuntimeError(f"Output {source.name} is not a valid ZIP-based mobile package")
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    sha256 = digest.hexdigest()
    app_slug = slugify(build.app_name)
    target_name = f"{app_slug}.{fmt}"
    key = f"{app_slug}/{build.id}/{target_name}"
    content_type = "application/vnd.android.package-archive" if fmt == "apk" else "application/octet-stream"
    storage_path = store_file(source, key, content_type)
    with SessionLocal() as db:
        db.add(Artifact(id=str(uuid.uuid4()), build_id=build.id, format=fmt, file_name=target_name, storage_path=storage_path, sha256=sha256, size_bytes=source.stat().st_size))
        db.commit()
    return source
