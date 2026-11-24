import base64
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image
from engine.api.config import settings
from .common import record, save_artifact
from .signing import android_signing_material

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "android"


def run(command: list[str], cwd: Path, timeout: int, env: dict[str, str] | None = None):
    proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(command[:3])}\n{output[-6000:]}")
    return output


def create_icons(config: dict, project_dir: Path):
    encoded = config.get("app_icon_png_base64") if config.get("launcher_icon", True) else None
    if not encoded:
        return
    import io
    image = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGBA")
    image.thumbnail((512, 512), Image.Resampling.LANCZOS)
    sizes = {"mipmap-mdpi": 48, "mipmap-hdpi": 72, "mipmap-xhdpi": 96, "mipmap-xxhdpi": 144, "mipmap-xxxhdpi": 192}
    for folder, size in sizes.items():
        output_dir = project_dir / "app" / "src" / "main" / "res" / folder
        output_dir.mkdir(parents=True, exist_ok=True)
        resized = image.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(output_dir / "ic_launcher.png", format="PNG", optimize=True)


def verify_android_signature(path: Path, fmt: str):
    if not path.is_file():
        raise RuntimeError(f"Expected {fmt.upper()} output was not produced")
    if fmt == "apk":
        command = ["apksigner", "verify", "--verbose", "--print-certs", str(path)]
    elif fmt == "aab":
        command = ["jarsigner", "-verify", "-verbose", "-certs", str(path)]
    else:
        raise RuntimeError("Unsupported Android artifact format")
    proc = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        output = (proc.stdout or "") + (proc.stderr or "")
        raise RuntimeError(f"{fmt.upper()} signature verification failed: {output[-4000:]}")


def build_android(build):
    cfg = __import__("json").loads(build.config_json)
    formats = __import__("json").loads(build.formats_json)
    owner_dir = hashlib.sha256(build.owner_id.encode()).hexdigest()[:24]
    work_dir = Path(settings.work_root) / owner_dir / build.id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEMPLATE, work_dir)
    record(build.id, "preparing", 8, "Android project template staged in an isolated workspace.")
    create_icons(cfg, work_dir)
    store_file, store_password, key_alias = android_signing_material(build.owner_id, build.package_id)
    host = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(build.website_url).hostname
    allowed_hosts = host
    record(build.id, "signing", 20, "Managed application signing key selected.")
    properties = [
        f"-PcompileSdk={settings.android_compile_sdk}", f"-PbuildToolsVersion={settings.android_build_tools}",
        f"-PapplicationId={build.package_id}", f"-PappName={build.app_name}", f"-PstartUrl={build.website_url}",
        f"-PallowedHosts={allowed_hosts}", f"-Porientation={cfg.get('orientation', 'portrait')}",
        f"-PallowScreenshots={str(cfg.get('allow_screenshots', True)).lower()}", f"-PshowLoading={str(cfg.get('show_loading_indicator', True)).lower()}",
        f"-PallowZoom={str(cfg.get('allow_zoom', True)).lower()}", f"-PdownloadsEnabled={str(cfg.get('downloads_enabled', True)).lower()}",
        f"-PjavascriptEnabled={str(cfg.get('javascript_enabled', True)).lower()}", f"-PfileUploadsEnabled={str(cfg.get('file_uploads_enabled', True)).lower()}",
        f"-PexternalLinks={cfg.get('external_links', 'in_app_browser')}",
        f"-PprimaryColor={cfg.get('primary_color', '#635BFF')}", f"-PstatusBarColor={cfg.get('status_bar_color', '#101522')}",
        f"-PnavigationBarColor={cfg.get('navigation_bar_color', '#101522')}",
    ]
    env = os.environ.copy()
    env["ANDROID_HOME"] = settings.android_sdk_root
    env["ANDROID_SDK_ROOT"] = settings.android_sdk_root
    # Gradle reads these project properties from the child environment, not process argv.
    env["ORG_GRADLE_PROJECT_storeFile"] = str(store_file)
    env["ORG_GRADLE_PROJECT_storePassword"] = store_password
    env["ORG_GRADLE_PROJECT_keyAlias"] = key_alias
    env["ORG_GRADLE_PROJECT_keyPassword"] = store_password
    tasks = []
    if "apk" in formats:
        tasks.append(":app:assembleRelease")
    if "aab" in formats:
        tasks.append(":app:bundleRelease")
    record(build.id, "compiling", 35, "Gradle release compilation started.")
    run([settings.gradle_command, "--no-daemon", *properties, *tasks], work_dir, settings.build_timeout_seconds, env)
    record(build.id, "validating", 85, "Checking APK/AAB output files.")
    artifacts = []
    if "apk" in formats:
        src = work_dir / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
        verify_android_signature(src, "apk")
        artifacts.append(save_artifact(build, "apk", src))
    if "aab" in formats:
        src = work_dir / "app" / "build" / "outputs" / "bundle" / "release" / "app-release.aab"
        verify_android_signature(src, "aab")
        artifacts.append(save_artifact(build, "aab", src))
    record(build.id, "completed", 100, f"Android build completed. {len(artifacts)} signed artifact(s) saved privately.")
    shutil.rmtree(work_dir, ignore_errors=True)
