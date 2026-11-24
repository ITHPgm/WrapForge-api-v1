from dataclasses import dataclass
from hmac import compare_digest
from fastapi import Depends, HTTPException, Request
from redis import Redis
from .config import settings
from .db import get_db

redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


@dataclass(frozen=True)
class Principal:
    owner_id: str
    key_id: str


def authenticate(request: Request) -> Principal:
    supplied = request.headers.get("X-API-Key", "")
    if "." not in supplied:
        raise HTTPException(status_code=401, detail="A valid X-API-Key is required")
    key_id, secret = supplied.split(".", 1)
    record = settings.api_key_records().get(key_id)
    if not record:
        raise HTTPException(status_code=401, detail="Invalid API key")
    owner_id, expected_secret = record
    if not compare_digest(secret.encode(), expected_secret.encode()):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return Principal(owner_id=owner_id, key_id=key_id)


def get_principal(request: Request) -> Principal:
    principal = authenticate(request)
    bucket = int(request.state.request_time // 60) if hasattr(request.state, "request_time") else 0
    key = f"wf:rate:{principal.owner_id}:{bucket}"
    try:
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 90)
        count, _ = pipe.execute()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Rate-limit service unavailable") from exc
    if int(count) > settings.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Rate limit exceeded; retry shortly")
    return principal
