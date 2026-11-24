from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_env: str = "development"
    app_name: str = "WrapForge Build API"
    api_prefix: str = "/api/v1"
    public_base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./wrapforge-dev.db"
    redis_url: str = "redis://localhost:6379/0"
    api_keys: str = ""
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 60
    max_request_bytes: int = 8 * 1024 * 1024
    artifact_root: str = "./var/artifacts"
    work_root: str = "./var/workspaces"
    config_snapshot_root: str = "./var/configurations"
    signing_root: str = "./var/signing"
    signing_master_key: str = ""
    build_timeout_seconds: int = 1800
    android_sdk_root: str = "/opt/android-sdk"
    android_compile_sdk: int = 36
    android_build_tools: str = "36.0.0"
    gradle_command: str = "gradle"
    ios_team_id: str = ""
    ios_signing_identity: str = "Apple Distribution"
    ios_export_method: str = "app-store-connect"
    ios_provisioning_profile_specifier: str = ""
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def api_key_records(self) -> dict[str, tuple[str, str]]:
        """Return {key_id: (owner_id, secret)} from KEY_ID:OWNER_ID:SECRET entries."""
        records: dict[str, tuple[str, str]] = {}
        for raw in self.api_keys.split(","):
            raw = raw.strip()
            if not raw:
                continue
            parts = raw.split(":", 2)
            if len(parts) != 3 or not all(parts):
                raise ValueError("API_KEYS entries must use key-id:owner-id:secret format")
            key_id, owner_id, secret = parts
            records[key_id] = (owner_id, secret)
        return records


@lru_cache

def get_settings() -> Settings:
    return Settings()


settings = get_settings()
