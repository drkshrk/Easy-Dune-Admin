#!/usr/bin/env bash
set -euo pipefail

ADDON_ID="eda-exchange-bot"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REDBLINK_ROOT="${1:-/home/steihl/dune-awakening-selfhost-docker}"
INSTALL_MODE="${2:-community-review}"
TARGET_DIR="$REDBLINK_ROOT/runtime/addons/installed/$ADDON_ID"
STATE_FILE="$REDBLINK_ROOT/runtime/addons/state.json"
if [ "$INSTALL_MODE" = "--dev-enable" ]; then
  ENABLED_JSON="true"
  APPROVED_PERMISSIONS_JSON='["database:read", "database:write"]'
else
  ENABLED_JSON="false"
  APPROVED_PERMISSIONS_JSON='[]'
fi

echo "Installing EDA Exchange Bot addon..."
echo "Source: $SOURCE_DIR"
echo "Target: $TARGET_DIR"
echo "Mode: $INSTALL_MODE"
echo

mkdir -p "$(dirname "$TARGET_DIR")" "$(dirname "$STATE_FILE")"
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"
cp -a "$SOURCE_DIR/addon.json" "$SOURCE_DIR/web" "$TARGET_DIR/"

STATE_FILE="$STATE_FILE" TARGET_DIR="$TARGET_DIR" ENABLED_JSON="$ENABLED_JSON" APPROVED_PERMISSIONS_JSON="$APPROVED_PERMISSIONS_JSON" python3 - <<'PY'
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

state["eda-exchange-bot"] = {
    **state.get("eda-exchange-bot", {}),
    "enabled": json.loads(os.environ["ENABLED_JSON"]),
    "approvedPermissions": json.loads(os.environ["APPROVED_PERMISSIONS_JSON"]),
    "installedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "sha256": addon_hash.hexdigest(),
    "installedBy": "easy-dune-admin-manual",
}

state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
PY

echo "EDA Exchange Bot installed in:"
echo "$STATE_FILE"
echo
if [ "$INSTALL_MODE" = "--dev-enable" ]; then
  echo "Developer mode: addon enabled and database permissions approved."
else
  echo "Community-review mode: addon is disabled and permissions are not pre-approved."
  echo "Enable it and approve database:read/database:write from RedBlink Console when you intentionally want it active."
fi
echo
if grep -q "Seed NPC Sell Market" "$TARGET_DIR/web/index.html" && grep -q "Run Buyback Sweep" "$TARGET_DIR/web/index.html"; then
  echo "Installed addon UI includes seed and buyback controls."
else
  echo "WARNING: Installed addon UI still looks like an older preview-only build." >&2
  echo "Check that you uploaded the current eda-exchange-bot folder before running this installer." >&2
fi
echo
echo "Refresh RedBlink Dune Docker Console."
echo "If it still does not appear in the Addons table, test the installed addon directly:"
echo "/api/addons/installed/eda-exchange-bot/content/web/index.html"
