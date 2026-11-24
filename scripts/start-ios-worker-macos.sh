#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

# Run this script on a dedicated macOS host with Xcode and XcodeGen installed.
# It must use the same DATABASE_URL, REDIS_URL, SIGNING_MASTER_KEY and storage settings
# as the API. Keep signing credentials and the worker host outside public web roots.

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This worker must run on macOS; IPA builds require xcodebuild." >&2
  exit 2
fi
command -v xcodebuild >/dev/null || { echo "Install Xcode and Xcode Command Line Tools first." >&2; exit 2; }
command -v xcodegen >/dev/null || { echo "Install XcodeGen: brew install xcodegen" >&2; exit 2; }
python3 -m venv .venv-ios-worker
source .venv-ios-worker/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
exec python -m engine.worker.worker_entry --queue ios-builds
