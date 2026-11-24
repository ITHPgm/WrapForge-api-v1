from pathlib import Path
import shutil
from urllib.parse import urlparse
from .config import settings


def _s3_client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id or None,
        aws_secret_access_key=settings.s3_secret_access_key or None,
    )


def store_file(source: Path, key: str, content_type: str) -> str:
    """Store privately; use S3/R2 in multi-service deployments, local disk in dev."""
    if settings.s3_bucket:
        _s3_client().upload_file(
            str(source), settings.s3_bucket, key,
            ExtraArgs={"ContentType": content_type},
        )
        return f"s3://{settings.s3_bucket}/{key}"
    root = Path(settings.artifact_root).resolve()
    target = (root / key).resolve()
    if root not in target.parents:
        raise RuntimeError("Artifact key escaped storage root")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    shutil.copyfile(source, target)
    return str(target)


def get_download_url(storage_path: str) -> str | None:
    parsed = urlparse(storage_path)
    if parsed.scheme != "s3":
        return None
    if not settings.s3_bucket or parsed.netloc != settings.s3_bucket:
        raise RuntimeError("Artifact object storage configuration mismatch")
    return _s3_client().generate_presigned_url(
        "get_object", Params={"Bucket": parsed.netloc, "Key": parsed.path.lstrip("/")}, ExpiresIn=300,
    )
