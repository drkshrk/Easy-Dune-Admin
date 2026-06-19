#!/usr/bin/env bash
set -euo pipefail

REDBLINK_ROOT="${1:-/home/steihl/dune-awakening-selfhost-docker}"
ADDONS_PANEL="$REDBLINK_ROOT/console/web/src/features/addons/AddonsPanel.tsx"
STYLES_FILE="$REDBLINK_ROOT/console/web/src/styles.css"
DB_FILE="$REDBLINK_ROOT/console/api/src/db.js"

if [ ! -f "$ADDONS_PANEL" ]; then
  echo "Could not find RedBlink AddonsPanel source:" >&2
  echo "$ADDONS_PANEL" >&2
  exit 2
fi

if [ ! -f "$STYLES_FILE" ]; then
  echo "Could not find RedBlink styles source:" >&2
  echo "$STYLES_FILE" >&2
  exit 2
fi

if [ ! -f "$DB_FILE" ]; then
  echo "Could not find RedBlink database helper source:" >&2
  echo "$DB_FILE" >&2
  exit 2
fi

ADDONS_PANEL="$ADDONS_PANEL" STYLES_FILE="$STYLES_FILE" DB_FILE="$DB_FILE" python3 - <<'PY'
import os
from pathlib import Path

addons_panel = Path(os.environ["ADDONS_PANEL"])
styles_file = Path(os.environ["STYLES_FILE"])
db_file = Path(os.environ["DB_FILE"])
text = addons_panel.read_text(encoding="utf-8")

old_load = """      const [result, installedResult] = await Promise.all([addonsApi.community(), addonsApi.installed()]);
      setAddons(result.addons || []);
      setAddonCount((result.addons || []).length);
      setInstalled(installedResult.addons || []);
      setInstalledLoaded(true);"""

new_load = """      const [result, installedResult] = await Promise.all([addonsApi.community(), addonsApi.installed()]);
      const communityAddons = result.addons || [];
      const installedAddons = installedResult.addons || [];
      setAddons(communityAddons);
      setAddonCount(new Set([...communityAddons.map((addon) => addon.id), ...installedAddons.map((addon) => addon.id)]).size);
      setInstalled(installedAddons);
      setInstalledLoaded(true);"""

old_pin = """  useEffect(() => {
    if (!installedLoaded) return;
    setPinnedAddons((current) => current
      .map((item) => {
        const installedAddon = installed.find((addon) => addon.id === item.id && addon.enabled);
        return installedAddon ? { id: installedAddon.id, name: installedAddon.name, entryPath: installedAddon.entryPath, enabled: installedAddon.enabled } : null;
      })
      .filter((item): item is PinnedAddon => Boolean(item)));
  }, [installed, installedLoaded, setPinnedAddons]);"""

new_pin = """  useEffect(() => {
    if (!installedLoaded) return;
    setPinnedAddons((current) => current
      .map((item) => {
        const installedAddon = installed.find((addon) => addon.id === item.id && addon.enabled);
        return installedAddon ? { id: installedAddon.id, name: installedAddon.name, entryPath: installedAddon.entryPath, enabled: installedAddon.enabled } : null;
      })
      .filter((item): item is PinnedAddon => Boolean(item))
      .concat(installed
        .filter((addon) => addon.enabled && !addons.some((communityAddon) => communityAddon.id === addon.id))
        .filter((addon) => !current.some((item) => item.id === addon.id))
        .map((addon) => ({ id: addon.id, name: addon.name, entryPath: addon.entryPath, enabled: addon.enabled }))));
  }, [addons, installed, installedLoaded, setPinnedAddons]);"""

old_rows = """  const rows = addons.map((addon) => {
    const installedAddon = installedById.get(addon.id);
    return { ...addon, status: installedAddon ? installedAddon.status || "Installed" : "Available" };
  });"""

new_rows = """  const installedOnlyRows = installed
    .filter((addon) => !addons.some((communityAddon) => communityAddon.id === addon.id))
    .map((addon) => ({
      id: addon.id,
      name: addon.name,
      description: addon.description,
      author: addon.author,
      version: addon.version,
      sourceUrl: "",
      manifestUrl: "",
      permissions: addon.permissions
    }));
  const rows = [...addons, ...installedOnlyRows].map((addon) => {
    const installedAddon = installedById.get(addon.id);
    return { ...addon, status: installedAddon ? installedAddon.status || "Installed" : "Available" };
  }).sort((left, right) => left.name.localeCompare(right.name));"""

old_name_cell = """      <td><AddonNameCell addon={row} /></td>"""

new_name_cell = """      <td>{installedAddon?.enabled
        ? <button className="addon-source-link addon-open-link" type="button" onClick={() => setOpenAddonId(openAddonId === installedAddon.id ? "" : installedAddon.id)}>{row.name}</button>
        : <AddonNameCell addon={row} />}</td>"""

changed = False
for old, new, label in [
    (old_load, new_load, "load installed-only addon count"),
    (old_pin, new_pin, "auto-pin installed-only addons"),
    (old_rows, new_rows, "render installed-only addon rows"),
    (old_name_cell, new_name_cell, "open installed addon from name column"),
]:
    if new in text:
        continue
    if old not in text:
        raise SystemExit(f"Expected AddonsPanel block was not found for: {label}")
    text = text.replace(old, new)
    changed = True

if changed:
    addons_panel.write_text(text, encoding="utf-8")
    print(f"Patched {addons_panel}")
else:
    print("RedBlink AddonsPanel already has the local addon visibility patch.")

styles = styles_file.read_text(encoding="utf-8")
style_line = ".addon-open-link { width: auto; min-height: 0; border: 0; background: transparent; padding: 0; text-align: left; }"
if style_line not in styles:
    anchor = ".addon-source-link:hover { color: #f1c96f; text-decoration: underline; }"
    if anchor not in styles:
        raise SystemExit("Expected addon-source-link CSS block was not found.")
    styles = styles.replace(anchor, f"{anchor}\n{style_line}")
    styles_file.write_text(styles, encoding="utf-8")
    print(f"Patched {styles_file}")
else:
    print("RedBlink styles already have addon-open-link.")

db_text = db_file.read_text(encoding="utf-8")
old_rows_result = """export function rowsResult(result) {
  return {
    columns: result.fields.map((field) => ({ name: field.name, dataTypeId: field.dataTypeID })),
    rows: result.rows,
    rowCount: result.rowCount ?? result.rows.length,
    command: result.command || ""
  };
}
"""

new_rows_result = """function normalizeQueryResult(result) {
  if (!Array.isArray(result)) return result;
  return [...result].reverse().find((entry) => Array.isArray(entry?.fields) && entry.fields.length) ||
    [...result].reverse().find((entry) => Array.isArray(entry?.rows)) ||
    result[result.length - 1] ||
    { fields: [], rows: [], rowCount: 0, command: "" };
}

export function rowsResult(result) {
  const normalized = normalizeQueryResult(result);
  const fields = Array.isArray(normalized.fields) ? normalized.fields : [];
  const rows = Array.isArray(normalized.rows) ? normalized.rows : [];
  return {
    columns: fields.map((field) => ({ name: field.name, dataTypeId: field.dataTypeID })),
    rows,
    rowCount: normalized.rowCount ?? rows.length,
    command: normalized.command || ""
  };
}
"""

if new_rows_result in db_text:
    print("RedBlink database helper already normalizes multi-statement query results.")
elif old_rows_result in db_text:
    db_file.write_text(db_text.replace(old_rows_result, new_rows_result), encoding="utf-8")
    print(f"Patched {db_file}")
else:
    raise SystemExit("Expected rowsResult block was not found in RedBlink database helper.")
PY

echo
echo "Now rebuild and restart RedBlink Dune Docker Console:"
echo "cd \"$REDBLINK_ROOT\""
echo "runtime/scripts/dune console restart"
