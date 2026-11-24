import traceback
from sqlalchemy import select
from engine.api.db import SessionLocal
from engine.api.models import Build
from .common import record
from .android import build_android
from .ios import build_ios


def process_build(build_id: str):
    with SessionLocal() as db:
        build = db.scalar(select(Build).where(Build.id == build_id))
        if not build:
            raise RuntimeError(f"Build {build_id} does not exist")
        # Detach the ORM object before releasing the session; all required fields are loaded.
        db.expunge(build)
    try:
        record(build_id, "preparing", 5, "Worker accepted build job.")
        if build.platform == "android":
            build_android(build)
        elif build.platform == "ios":
            build_ios(build)
        else:
            raise RuntimeError("Unsupported platform")
    except Exception as exc:
        record(build_id, "failed", 0, str(exc), "error")
        raise
