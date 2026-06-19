# EDA Catalog Editor

`EDA Catalog Editor` is a native RedBlink Dune Docker Console addon slice for
reviewing and locally editing Easy Dune Admin's item catalog.

## Current Scope

- Visual item selector built from `web/catalog.json`.
- Structured editor for common catalog fields such as name, category,
  tradeable, stack size, vendor price, tier, rarity, durability, schematic,
  augment, gradeable, and icon metadata.
- Browser-local edit persistence with full catalog export and compact patch
  export.
- Full catalog or patch import.

The addon requests no RedBlink permissions. RedBlink's template lists
`files:addon-data` as reserved, but this stack does not yet expose bridge
actions for addon-owned file reads/writes. Until that exists, this tool exports
JSON for review or manual replacement of Easy Dune Admin's
`data/easy-dune-item-catalog.json`.

## Files

```text
addon.json
web/index.html
web/catalog.json
web/base-unknown.png
web/base-schematic.png
web/base-augment.png
scripts/validate.js
install-eda-catalog-editor.sh
```

The fallback images are original Easy Dune Admin placeholder assets. Dune:
Awakening game-art icons are not redistributed in this addon package.

## Install On A RedBlink VM

Upload this `eda-catalog-editor` folder to the VM, then run:

```bash
cd /path/to/eda-catalog-editor
sed -i 's/\r$//' install-eda-catalog-editor.sh
chmod +x install-eda-catalog-editor.sh
./install-eda-catalog-editor.sh /home/steihl/dune-awakening-selfhost-docker

cd /home/steihl/dune-awakening-selfhost-docker
runtime/scripts/dune console restart
```

## Validate

```bash
node scripts/validate.js
```
