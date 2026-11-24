import json
import os
import re
import hashlib
import secrets
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import dns.resolver
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auth import Principal, get_principal
from .config import settings
from .db import get_db
from .models import Artifact, Build, BuildEvent, DomainVerification
from .queue import android_queue, ios_queue
from .schemas import BuildCreate, DomainChallengeIn, DomainVerifyIn
from .storage import get_download_url

router = APIRouter()


def event(db: Session, build: Build, status: str, progress: int, message: str, level: str = "info"):
    build.status = status
    build.progress = progress
    if status == "failed":
        build.failure_reason = message
        build.finished_at = datetime.now(timezone.utc)
    elif status == "completed":
        build.finished_at = datetime.now(timezone.utc)
    if status not in {"queued", "failed", "completed"} and build.started_at is None:
        build.started_at = datetime.now(timezone.utc)
    db.add(BuildEvent(build_id=build.id, status=status, progress=progress, level=level, message=message[:4000]))
    db.commit()



def write_build_snapshot(build: Build) -> Path:
    """Write the immutable request manifest to a private app/build folder."""
    slug = re.sub(r"[^a-z0-9]+", "-", build.app_name.lower()).strip("-")[:48] or "mobile-app"
    owner_hash = hashlib.sha256(build.owner_id.encode("utf-8")).hexdigest()[:24]
    root = Path(settings.config_snapshot_root).resolve()
    folder = (root / slug / owner_hash / build.id).resolve()
    if root not in folder.parents:
        raise RuntimeError("Build snapshot path escaped its private root")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(folder, 0o700)
    manifest = {
        "schema_version": 1,
        "build_id": build.id,
        "tenant_reference": owner_hash,
        "created_at": build.created_at.isoformat() if build.created_at else datetime.now(timezone.utc).isoformat(),
        "app": {
            "name": build.app_name,
            "package_id": build.package_id,
            "platform": build.platform,
            "website_url": build.website_url,
            "formats": json.loads(build.formats_json),
        },
        "features": json.loads(build.config_json),
    }
    temporary = folder / (".request-" + secrets.token_hex(8) + ".tmp")
    destination = folder / "request.json"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
    return destination


def normalise_host(hostname: str, require_public_dns: bool = False) -> str:
    host = hostname.strip().rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise HTTPException(422, "Invalid internationalized domain name") from exc
    labels = host.split(".")
    label_pattern = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    if not host or len(host) > 253 or len(labels) < 2 or any(not label_pattern.fullmatch(part) for part in labels):
        raise HTTPException(422, "Invalid hostname")
    if host == "localhost" or host.endswith(".localhost"):
        raise HTTPException(422, "Localhost domains cannot be used")
    try:
        ip = socket.getaddrinfo(host, None)
        for item in ip:
            address = item[4][0]
            import ipaddress
            parsed = ipaddress.ip_address(address)
            if not parsed.is_global:
                raise HTTPException(422, "Domain must resolve only to public IP addresses")
    except socket.gaierror as exc:
        if require_public_dns:
            raise HTTPException(422, "Website hostname must resolve to a public IP address before building") from exc
        # A challenge may be created before the owner publishes the DNS record.
    else:
        if not ip:
            if require_public_dns:
                raise HTTPException(422, "Website hostname must resolve to a public IP address")
    return host


@router.post("/domains/challenges", status_code=201)
def create_domain_challenge(payload: DomainChallengeIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    hostname = normalise_host(payload.hostname)
    row = db.scalar(select(DomainVerification).where(DomainVerification.owner_id == principal.owner_id, DomainVerification.hostname == hostname))
    token = "wrapforge-verification=" + secrets.token_urlsafe(32)
    if row is None:
        row = DomainVerification(id=str(uuid.uuid4()), owner_id=principal.owner_id, hostname=hostname, token=token, verified=False)
        db.add(row)
    else:
        row.token, row.verified, row.verified_at = token, False, None
    db.commit()
    return {"success": True, "hostname": hostname, "record": {"type": "TXT", "name": "_wrapforge." + hostname, "value": token}, "next": "POST /domains/verify after DNS propagation"}


@router.post("/domains/verify")
def verify_domain(payload: DomainVerifyIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    hostname = normalise_host(payload.hostname)
    row = db.scalar(select(DomainVerification).where(DomainVerification.owner_id == principal.owner_id, DomainVerification.hostname == hostname))
    if row is None:
        raise HTTPException(404, "Create a domain verification challenge first")
    try:
        answers = dns.resolver.resolve("_wrapforge." + hostname, "TXT", lifetime=5)
        values = {b"".join(item.strings).decode("utf-8", "replace") for item in answers}
    except Exception as exc:
        raise HTTPException(422, "The verification TXT record could not be found") from exc
    if row.token not in values:
        raise HTTPException(422, "DNS TXT value does not match this challenge")
    row.verified = True
    row.verified_at = datetime.now(timezone.utc)
    db.commit()
    return {"success": True, "hostname": hostname, "verified": True}


@router.post("/builds", status_code=202)
def create_build(payload: BuildCreate, request: Request, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    hostname = normalise_host(urlparse(payload.website_url).hostname or "", require_public_dns=True)
    verified = db.scalar(select(DomainVerification).where(DomainVerification.owner_id == principal.owner_id, DomainVerification.hostname == hostname, DomainVerification.verified.is_(True)))
    if not verified:
        raise HTTPException(403, "Verify ownership of this website domain before building")
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 160 or not re.fullmatch(r"[A-Za-z0-9._:-]+", idempotency_key):
            raise HTTPException(422, "Idempotency-Key must contain 1-160 letters, numbers, dots, underscores, colons or hyphens")
        prior = db.scalar(select(Build).where(Build.owner_id == principal.owner_id, Build.idempotency_key == idempotency_key))
        if prior:
            if not identical_build_request(prior, payload):
                raise HTTPException(409, "This Idempotency-Key was already used with a different build request")
            return build_payload(prior)
    build_id = str(uuid.uuid4())
    config = payload.features.model_dump()
    build = Build(id=build_id, owner_id=principal.owner_id, idempotency_key=idempotency_key, platform=payload.platform, app_name=payload.app_name, package_id=payload.package_id, website_url=payload.website_url, formats_json=json.dumps(payload.formats), config_json=json.dumps(config), status="queued", progress=0)
    db.add(build)
    db.add(BuildEvent(build_id=build_id, status="queued", progress=0, message="Build request accepted and queued."))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Two identical requests may race on the unique idempotency constraint.
        if idempotency_key:
            prior = db.scalar(select(Build).where(Build.owner_id == principal.owner_id, Build.idempotency_key == idempotency_key))
            if prior:
                if not identical_build_request(prior, payload):
                    raise HTTPException(409, "This Idempotency-Key was already used with a different build request")
                return build_payload(prior)
        raise
    try:
        write_build_snapshot(build)
    except Exception as exc:
        event(db, build, "failed", 0, "Build configuration snapshot could not be stored securely.", "error")
        raise HTTPException(503, "Build configuration storage is unavailable") from exc
    try:
        queue = android_queue if payload.platform == "android" else ios_queue
        queue.enqueue("engine.worker.build.process_build", build_id, job_id=build_id, job_timeout=settings.build_timeout_seconds, result_ttl=86400, failure_ttl=604800)
    except Exception as exc:
        event(db, build, "failed", 0, "Build queue unavailable; request was not started.", "error")
        raise HTTPException(503, "Build queue unavailable") from exc
    return build_payload(build)


def identical_build_request(build: Build, payload: BuildCreate) -> bool:
    return (
        build.platform == payload.platform
        and build.app_name == payload.app_name
        and build.package_id == payload.package_id
        and build.website_url == payload.website_url
        and json.loads(build.formats_json) == payload.formats
        and json.loads(build.config_json) == payload.features.model_dump()
    )

def build_payload(build: Build):
    return {"success": True, "build_id": build.id, "platform": build.platform, "status": build.status, "progress": build.progress, "status_url": f"{settings.api_prefix}/builds/{build.id}", "events_url": f"{settings.api_prefix}/builds/{build.id}/events", "artifacts_url": f"{settings.api_prefix}/builds/{build.id}/artifacts"}


def owned_build(db: Session, principal: Principal, build_id: str) -> Build:
    build = db.scalar(select(Build).where(Build.id == build_id, Build.owner_id == principal.owner_id))
    if not build:
        raise HTTPException(404, "Build not found")
    return build


@router.get("/builds/{build_id}")
def get_build(build_id: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    build = owned_build(db, principal, build_id)
    artifacts = db.scalars(select(Artifact).where(Artifact.build_id == build.id)).all()
    return {**build_payload(build), "app_name": build.app_name, "package_id": build.package_id, "website_url": build.website_url, "formats": json.loads(build.formats_json), "failure_reason": build.failure_reason, "artifacts": [{"id": a.id, "format": a.format, "file_name": a.file_name, "size_bytes": a.size_bytes, "sha256": a.sha256, "download_url": f"{settings.api_prefix}/builds/{build.id}/artifacts/{a.id}/download"} for a in artifacts]}


@router.get("/builds/{build_id}/events")
def build_events(build_id: str, request: Request, after: int = Query(default=0, ge=0), last_event_id: str | None = Header(default=None, alias="Last-Event-ID"), principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    owned_build(db, principal, build_id)
    try:
        header_cursor = int(last_event_id) if last_event_id is not None else 0
    except ValueError as exc:
        raise HTTPException(400, "Last-Event-ID must be a non-negative integer") from exc
    if header_cursor < 0:
        raise HTTPException(400, "Last-Event-ID must be a non-negative integer")
    initial_last = max(after, header_cursor)

    async def stream():
        import asyncio
        from .db import SessionLocal
        last = initial_last
        while True:
            if await request.is_disconnected():
                break
            with SessionLocal() as session:
                rows = session.scalars(select(BuildEvent).where(BuildEvent.build_id == build_id, BuildEvent.id > last).order_by(BuildEvent.id.asc())).all()
                events = [{"id": row.id, "status": row.status, "progress": row.progress, "level": row.level, "message": row.message, "created_at": row.created_at.isoformat()} for row in rows]
                state = session.get(Build, build_id)
                terminal = bool(state and state.status in {"completed", "failed", "cancelled"})
            for data in events:
                last = data["id"]
                yield f"id: {last}\nevent: build\ndata: {json.dumps(data)}\n\n"
            if terminal and not events:
                yield "event: done\ndata: {}\n\n"
                break
            if not events:
                yield ": keep-alive\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@router.get("/builds/{build_id}/logs")
def get_logs(build_id: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    owned_build(db, principal, build_id)
    rows = db.scalars(select(BuildEvent).where(BuildEvent.build_id == build_id).order_by(BuildEvent.id.asc())).all()
    return {"items": [{"id": row.id, "level": row.level, "status": row.status, "progress": row.progress, "message": row.message, "created_at": row.created_at.isoformat()} for row in rows]}


@router.get("/builds/{build_id}/artifacts")
def list_artifacts(build_id: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    build = owned_build(db, principal, build_id)
    rows = db.scalars(select(Artifact).where(Artifact.build_id == build.id)).all()
    return {"items": [{"id": item.id, "format": item.format, "file_name": item.file_name, "size_bytes": item.size_bytes, "sha256": item.sha256, "download_url": f"{settings.api_prefix}/builds/{build.id}/artifacts/{item.id}/download"} for item in rows]}


@router.get("/builds/{build_id}/artifacts/{artifact_id}/download")
def download_artifact(build_id: str, artifact_id: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    build = owned_build(db, principal, build_id)
    artifact = db.scalar(select(Artifact).where(Artifact.id == artifact_id, Artifact.build_id == build.id))
    if not artifact:
        raise HTTPException(404, "Artifact not found")
    try:
        signed_url = get_download_url(artifact.storage_path)
    except Exception as exc:
        raise HTTPException(503, "Artifact storage is unavailable") from exc
    if signed_url:
        return RedirectResponse(signed_url, status_code=302, headers={"Cache-Control": "private, no-store"})
    root = Path(settings.artifact_root).resolve()
    path = Path(artifact.storage_path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Artifact not found")
    media = "application/vnd.android.package-archive" if artifact.format == "apk" else "application/octet-stream"
    return FileResponse(path, media_type=media, filename=artifact.file_name, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
