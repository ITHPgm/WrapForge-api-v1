import base64
import hashlib
import hmac
import os
import subprocess
from pathlib import Path
from engine.api.config import settings


def android_signing_material(owner_id: str, package_id: str) -> tuple[Path, str, str]:
    if len(settings.signing_master_key) < 48:
        raise RuntimeError("SIGNING_MASTER_KEY must be set to a stable secret (48+ characters)")
    safe_key = hashlib.sha256(f"{owner_id}:{package_id}".encode()).hexdigest()
    root = Path(settings.signing_root).resolve() / safe_key[:2]
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    store = root / f"{safe_key}.jks"
    material = hmac.new(settings.signing_master_key.encode(), safe_key.encode(), hashlib.sha256).digest()
    password = base64.urlsafe_b64encode(material).decode("ascii").rstrip("=")[:32]
    if not store.exists():
        env = os.environ.copy()
        env["WRAPFORGE_ANDROID_STORE_PASSWORD"] = password
        env["WRAPFORGE_ANDROID_KEY_PASSWORD"] = password
        command = ["keytool", "-genkeypair", "-v", "-keystore", str(store), "-storetype", "JKS", "-storepass:env", "WRAPFORGE_ANDROID_STORE_PASSWORD", "-keypass:env", "WRAPFORGE_ANDROID_KEY_PASSWORD", "-alias", "wrapforge", "-keyalg", "RSA", "-keysize", "3072", "-validity", "10000", "-dname", f"CN={package_id}, OU=WrapForge, O=WrapForge, C=US"]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=120, env=env)
        os.chmod(store, 0o600)
    return store, password, "wrapforge"
