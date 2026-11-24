import base64
import io
import re
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from PIL import Image

PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}(?:\.[A-Za-z][A-Za-z0-9_]{0,62})+$")


class DomainChallengeIn(BaseModel):
    hostname: str = Field(min_length=3, max_length=253)


class DomainVerifyIn(BaseModel):
    hostname: str = Field(min_length=3, max_length=253)


class WebFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")
    launcher_icon: bool = True
    allow_screenshots: bool = True
    show_loading_indicator: bool = True
    allow_zoom: bool = True
    orientation: Literal["portrait", "landscape", "sensor"] = "portrait"
    downloads_enabled: bool = True
    file_uploads_enabled: bool = True
    external_links: Literal["in_app_browser", "system_browser"] = "in_app_browser"
    javascript_enabled: bool = True
    primary_color: str = "#635BFF"
    status_bar_color: str = "#101522"
    navigation_bar_color: str = "#101522"
    app_icon_png_base64: str | None = None

    @field_validator("primary_color", "status_bar_color", "navigation_bar_color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Colors must use #RRGGBB format")
        return value

    @field_validator("app_icon_png_base64")
    @classmethod
    def validate_icon(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            raw = base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError("app_icon_png_base64 must be valid base64") from exc
        if len(raw) > 2 * 1024 * 1024 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Icon must be a PNG image no larger than 2 MB")
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != "PNG" or image.width != image.height or not (64 <= image.width <= 4096):
                    raise ValueError("Icon must be a square PNG between 64x64 and 4096x4096 pixels")
                image.verify()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Icon PNG could not be decoded") from exc
        return value


class BuildCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Literal["android", "ios"]
    app_name: str = Field(min_length=2, max_length=50)
    package_id: str = Field(min_length=3, max_length=180)
    website_url: str = Field(min_length=10, max_length=2048)
    formats: list[Literal["apk", "aab", "ipa"]] = Field(min_length=1, max_length=2)
    features: WebFeatures = Field(default_factory=WebFeatures)

    @field_validator("app_name")
    @classmethod
    def clean_app_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("App name cannot be blank")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ValueError("App name cannot contain control characters")
        return value

    @field_validator("package_id")
    @classmethod
    def validate_package_id(cls, value: str) -> str:
        if not PACKAGE_RE.fullmatch(value):
            raise ValueError("Use a reverse-domain application identifier, e.g. com.example.myapp")
        return value

    @field_validator("website_url")
    @classmethod
    def validate_website(cls, value: str) -> str:
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ValueError("Website URL cannot contain control characters")
        parsed = urlparse(value.strip())
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Website URL must be a valid HTTPS URL without embedded credentials")
        try:
            port = parsed.port
            hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        except (ValueError, UnicodeError) as exc:
            raise ValueError("Website URL has an invalid hostname or port") from exc
        if port not in (None, 443):
            raise ValueError("Only the standard HTTPS port is supported")
        if "." not in hostname or len(hostname) > 253:
            raise ValueError("Website URL must use a fully qualified public hostname")
        # Canonical host form avoids trailing-dot and mixed-case mismatches in DNS and WebView allowlists.
        return parsed._replace(scheme="https", netloc=hostname).geturl().rstrip("/")

    @model_validator(mode="after")
    def validate_platform_formats(self):
        formats = set(self.formats)
        if len(formats) != len(self.formats):
            raise ValueError("Duplicate output formats are not allowed")
        if self.platform == "android" and not formats.issubset({"apk", "aab"}):
            raise ValueError("Android builds support APK and AAB outputs")
        if self.platform == "ios" and formats != {"ipa"}:
            raise ValueError("iOS builds support IPA output only")
        return self
