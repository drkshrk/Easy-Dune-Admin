#!/usr/bin/env bash
set -euo pipefail

ADDON_ID="eda-catalog-editor"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REDBLINK_ROOT="${1:-/home/steihl/dune-awakening-selfhost-docker}"
TARGET_DIR="$REDBLINK_ROOT/runtime/addons/installed/$ADDON_ID"
STATE_FILE="$REDBLINK_ROOT/runtime/addons/state.json"

echo "Installing EDA Catalog Editor addon..."
echo "Source: $SOURCE_DIR"
echo "Target: $TARGET_DIR"
echo

mkdir -p "$(dirname "$TARGET_DIR")" "$(dirname "$STATE_FILE")"
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"
cp -a "$SOURCE_DIR/addon.json" "$SOURCE_DIR/web" "$TARGET_DIR/"

STATE_FILE="$STATE_FILE" TARGET_DIR="$TARGET_DIR" python3 - <<'PY'
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

state_file = Path(os.environ["STATE_FILE"])
target_dir = Path(os.environ["TARGET_DIR"])
try:
    state = json.loads(state_file.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        state = {}
except Exception:
    state = {}

addon_hash = hashlib.sha256()
hash_files = [target_dir / "addon.json"] + sorted(
    (path for path in (target_dir / "web").rglob("*") if path.is_file()),
    key=lambda path: str(path.relative_to(target_dir)),
)
for file_path in hash_files:
    addon_hash.update(str(file_path.relative_to(target_dir)).replace("\\", "/").encode("utf-8"))
    addon_hash.update(b"\0")
    addon_hash.update(file_path.read_bytes())
    addon_hash.update(b"\0")

state["eda-catalog-editor"] = {
    **state.get("eda-catalog-editor", {}),
    "enabled": True,
    "approvedPermissions": [],
    "installedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "sha256": addon_hash.hexdigest(),
    "installedBy": "easy-dune-admin-manual",
}

state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
PY

echo "EDA Catalog Editor installed and enabled in:"
echo "$STATE_FILE"
echo
if grep -q "EDA Catalog Editor" "$TARGET_DIR/web/index.html" && grep -q "Visual Item Selector" "$TARGET_DIR/web/index.html"; then
  echo "Installed addon UI includes the visual catalog editor."
else
  echo "WARNING: Installed addon UI does not look like the expected catalog editor." >&2
  echo "Check that you uploaded the current eda-catalog-editor folder before running this installer." >&2
fi
echo
echo "Refresh RedBlink Dune Docker Console."
