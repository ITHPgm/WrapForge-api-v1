import base64
import hashlib
import io
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from PIL import Image, ImageDraw
from engine.api.config import settings
from .common import record, save_artifact

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "ios"


def _run(command: list[str], cwd: Path, timeout: int, env: dict[str, str] | None = None):
    proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode:
        raise RuntimeError(f"iOS build command failed: {' '.join(command[:3])}\n{output[-6000:]}")
    return output


def verify_ipa_signature(ipa_path: Path, work_dir: Path):
    with zipfile.ZipFile(ipa_path, "r") as archive:
        names = archive.namelist()
        app_names = sorted({name.split("/")[1] for name in names if name.startswith("Payload/") and len(name.split("/")) >= 3 and name.split("/")[1].endswith(".app")})
        if len(app_names) != 1:
            raise RuntimeError("IPA must contain exactly one top-level Payload/*.app bundle")
        app_name = app_names[0]
        if f"Payload/{app_name}/Info.plist" not in names:
            raise RuntimeError("IPA app bundle is missing its Info.plist")
    # `ditto` is the macOS-native archive extractor and preserves framework symlinks
    # needed by valid iOS app bundles. The archive was first checked for a single app root.
    with tempfile.TemporaryDirectory(prefix="wrapforge-ipa-verify-") as temporary:
        _run(["ditto", "-x", "-k", str(ipa_path), temporary], work_dir, 120)
        app_bundle = Path(temporary) / "Payload" / app_name
        if not app_bundle.is_dir():
            raise RuntimeError("Unable to extract the iOS app bundle for signature validation")
        proc = subprocess.run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app_bundle)], cwd=work_dir, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            output = (proc.stdout or "") + (proc.stderr or "")
            raise RuntimeError(f"IPA code signature verification failed: {output[-4000:]}")


def build_ios(build):
    if sys.platform != "darwin":
        raise RuntimeError("IPA builds require a dedicated macOS worker with Xcode. Linux/Render containers cannot run xcodebuild.")
    if not settings.ios_team_id:
        raise RuntimeError("Configure IOS_TEAM_ID and Apple signing credentials on the macOS worker before requesting IPA builds.")
    if not shutil.which("xcodebuild") or not shutil.which("xcodegen"):
        raise RuntimeError("Install Xcode Command Line Tools and XcodeGen on the macOS worker.")
    import json
    cfg = json.loads(build.config_json)
    owner_dir = hashlib.sha256(build.owner_id.encode()).hexdigest()[:24]
    work_dir = Path(settings.work_root) / owner_dir / build.id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    shutil.copytree(TEMPLATE, work_dir)
    record(build.id, "preparing", 10, "iOS Swift/WKWebView project staged on macOS worker.")
    website_host = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(build.website_url).hostname or "example.com"
    # Generate per-build Swift configuration and the Info.plist consumed by Xcode.
    swift = (work_dir / "Sources" / "BuildConfig.swift").read_text(encoding="utf-8")
    hosts = json.dumps([website_host])
    swift = swift.replace('static let startURL = "https://example.com"', f'static let startURL = {json.dumps(build.website_url)}')
    swift = swift.replace('static let allowedHosts = ["example.com"]', f'static let allowedHosts = {hosts}')
    swift = swift.replace('static let allowZoom = true', f'static let allowZoom = {str(cfg.get("allow_zoom", True)).lower()}')
    swift = swift.replace('static let showLoading = true', f'static let showLoading = {str(cfg.get("show_loading_indicator", True)).lower()}')
    swift = swift.replace('static let javascriptEnabled = true', f'static let javascriptEnabled = {str(cfg.get("javascript_enabled", True)).lower()}')
    swift = swift.replace('static let downloadsEnabled = true', f'static let downloadsEnabled = {str(cfg.get("downloads_enabled", True)).lower()}')
    swift = swift.replace('static let externalLinks = "in_app_browser"', f'static let externalLinks = {json.dumps(cfg.get("external_links", "in_app_browser"))}')
    (work_dir / "Sources" / "BuildConfig.swift").write_text(swift, encoding="utf-8")
    # App Store icons are generated from the supplied square PNG, or a neutral default mark.
    encoded_icon = cfg.get("app_icon_png_base64") if cfg.get("launcher_icon", True) else None
    background_color = cfg.get("primary_color", "#635BFF")
    if encoded_icon:
        foreground = Image.open(io.BytesIO(base64.b64decode(encoded_icon))).convert("RGBA")
        background = Image.new("RGBA", foreground.size, background_color)
        icon = Image.alpha_composite(background, foreground).convert("RGB")
    else:
        icon = Image.new("RGB", (1024, 1024), background_color)
        draw = ImageDraw.Draw(icon)
        draw.rounded_rectangle((120, 120, 904, 904), radius=190, fill="#171D31")
        draw.text((310, 340), "WF", fill="white", stroke_width=2)
    icon = icon.resize((1024, 1024), Image.Resampling.LANCZOS)
    icon.save(work_dir / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon-1024.png", format="PNG", optimize=True)
    orientation = cfg.get("orientation", "portrait")
    supported = {
        "portrait": ["UIInterfaceOrientationPortrait"],
        "landscape": ["UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"],
        "sensor": ["UIInterfaceOrientationPortrait", "UIInterfaceOrientationPortraitUpsideDown", "UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"],
    }.get(orientation, ["UIInterfaceOrientationPortrait"])
    plist = {
        "CFBundleDevelopmentRegion": "$(DEVELOPMENT_LANGUAGE)",
        "CFBundleExecutable": "$(EXECUTABLE_NAME)",
        "CFBundleIdentifier": "$(PRODUCT_BUNDLE_IDENTIFIER)",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": build.app_name,
        "CFBundleDisplayName": build.app_name,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1",
        "LSRequiresIPhoneOS": True,
        "CFBundleIconName": "AppIcon",
        "UIFileSharingEnabled": True,
        "LSSupportsOpeningDocumentsInPlace": True,
        "WFStartURL": build.website_url,
        "UISupportedInterfaceOrientations": supported,
        "UIViewControllerBasedStatusBarAppearance": True,
        "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": False},
    }
    with (work_dir / "Info.plist").open("wb") as handle:
        plistlib.dump(plist, handle)
    # Build settings are passed as separate argv values; no shell interpolation is used.
    args = [
        "xcodegen", "generate", "--spec", "project.yml",
    ]
    _run(args, work_dir, 120)
    archive = work_dir / "build" / "WrapForge.xcarchive"
    if not cfg.get("allow_screenshots", True):
        record(build.id, "preparing", 18, "Warning: iOS does not provide a supported way for third-party apps to block user-initiated screenshots; this setting cannot be enforced on iOS.", "warning")
    if cfg.get("downloads_enabled", True):
        record(build.id, "preparing", 19, "Note: the current iOS template stores web downloads in the app Documents area; the UI does not yet provide a dedicated download manager.", "warning")
    if not cfg.get("file_uploads_enabled", True):
        record(build.id, "preparing", 20, "Warning: this iOS template relies on WKWebView's native file picker and does not enforce a global file-upload disable switch.", "warning")
    record(build.id, "compiling", 35, "Xcode archive started.")
    manual_profile = settings.ios_provisioning_profile_specifier.strip()
    signing_style = "Manual" if manual_profile else "Automatic"
    command = ["xcodebuild", "-project", "WrapForge.xcodeproj", "-scheme", "WrapForge", "-configuration", "Release", "-destination", "generic/platform=iOS", "-archivePath", str(archive), "archive", f"CODE_SIGN_STYLE={signing_style}", f"CODE_SIGN_IDENTITY={settings.ios_signing_identity}", f"DEVELOPMENT_TEAM={settings.ios_team_id}", f"PRODUCT_BUNDLE_IDENTIFIER={build.package_id}", f"PRODUCT_NAME={build.app_name}", f"WF_START_URL={build.website_url}", f"WF_ALLOW_SCREENSHOTS={str(cfg.get('allow_screenshots', True)).lower()}", f"WF_SHOW_LOADING={str(cfg.get('show_loading_indicator', True)).lower()}", f"WF_ALLOW_ZOOM={str(cfg.get('allow_zoom', True)).lower()}"]
    if manual_profile:
        command.append(f"PROVISIONING_PROFILE_SPECIFIER={manual_profile}")
    else:
        command.append("-allowProvisioningUpdates")
    _run(command, work_dir, settings.build_timeout_seconds)
    export_options_data = {"method": settings.ios_export_method, "teamID": settings.ios_team_id, "signingStyle": signing_style.lower(), "compileBitcode": False}
    if manual_profile:
        export_options_data["signingCertificate"] = settings.ios_signing_identity
        export_options_data["provisioningProfiles"] = {build.package_id: manual_profile}
    export_options = work_dir / "ExportOptions.plist"
    with export_options.open("wb") as handle:
        plistlib.dump(export_options_data, handle)
    export_dir = work_dir / "export"
    record(build.id, "validating", 85, "Exporting signed IPA archive.")
    _run(["xcodebuild", "-exportArchive", "-archivePath", str(archive), "-exportPath", str(export_dir), "-exportOptionsPlist", str(export_options), "-allowProvisioningUpdates"], work_dir, settings.build_timeout_seconds)
    ipa_files = list(export_dir.glob("*.ipa"))
    if len(ipa_files) != 1:
        raise RuntimeError("Xcode export did not produce exactly one IPA")
    verify_ipa_signature(ipa_files[0], work_dir)
    save_artifact(build, "ipa", ipa_files[0])
    record(build.id, "completed", 100, "Signed iOS IPA exported and saved privately.")
    shutil.rmtree(work_dir, ignore_errors=True)
