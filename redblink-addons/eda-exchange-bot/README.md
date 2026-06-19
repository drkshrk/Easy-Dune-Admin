# EDA Exchange Bot

`EDA Exchange Bot` is a native RedBlink Dune Docker Console addon built from
Easy Dune Admin's exchange seeder. It previews EDA's planned market listings
and can run manual market seed, buyback, EDA NPC clear, and unsafe NPC cleanup
actions through RedBlink's permissioned addon bridge without replacing the
standalone Easy Dune Admin panel.

## RedBlink Stack Compatibility

Target stack: RedBlink Dune Docker Console `v1.3.16` or newer.

RedBlink `v1.3.16` includes multi-statement `database.execute` result
normalization, so backup-protected write actions can return the addon's final
summary rows cleanly after successful writes.

The current RedBlink addon bridge exposes `database.query` and
`database.execute` for this addon. Background/automatic market sweeps are not
enabled here yet because the inspected `v1.3.16` stack does not expose an addon
scheduler or addon storage bridge. Keep sweeps manual until RedBlink publishes a
persistent addon task path.

## Files

```text
addon.json
web/index.html
web/dune-addon-bridge.js
web/market-seed-plan.json
scripts/validate.js
scripts/package.sh
install-eda-exchange-bot.sh
patch-redblink-local-addons.sh
```

The addon package itself is only `addon.json` plus `web/`. The install helper
is for private VM testing and mirrors RedBlink's local development flow. Its
default mode is community-review safe: installed disabled, with no permissions
pre-approved.

`patch-redblink-local-addons.sh` is a legacy/private compatibility helper for
pre-`v1.3.16` test stacks. It is not needed for current community-index installs
or current RedBlink stacks that already include installed-addon rendering and
multi-statement result normalization.

## Validate

```bash
node scripts/validate.js
```

## Install On A RedBlink VM

Upload this `eda-exchange-bot` folder to the VM, then run:

```bash
cd /path/to/eda-exchange-bot
chmod +x install-eda-exchange-bot.sh
./install-eda-exchange-bot.sh /home/steihl/dune-awakening-selfhost-docker
```

The helper copies `addon.json` and `web/` into:

```text
/home/steihl/dune-awakening-selfhost-docker/runtime/addons/installed/eda-exchange-bot
```

It also creates a disabled state entry in:

```text
/home/steihl/dune-awakening-selfhost-docker/runtime/addons/state.json
```

No permissions are pre-approved in the default helper flow. The addon manifest
requests `database:read` and `database:write`; server owners should enable the
addon and approve those permissions from RedBlink Console only when they want
the market seeder active. `database:read` is used to populate the exchange
selector; RedBlink's Console API creates a database backup before write SQL
runs through the addon bridge.

For private development only, you can intentionally install enabled with both
database permissions already approved:

```bash
./install-eda-exchange-bot.sh /home/steihl/dune-awakening-selfhost-docker --dev-enable
```

If the target server has tightened PostgreSQL credentials, configure RedBlink's
Console container with its existing DB environment variables instead of putting
secrets in the addon:

```text
ADMIN_DATABASE_URL
DUNE_DB_HOST
DUNE_DB_PORT
DUNE_DB_NAME
DUNE_DB_USER
DUNE_DB_PASSWORD
```

The addon iframe never receives DB credentials.

If you are testing against an older private stack where the addon exists in
`runtime/addons/installed` and `state.json` but does not appear in the Addons
table, apply the local-addons UI compatibility patch:

```bash
cd /path/to/eda-exchange-bot
chmod +x patch-redblink-local-addons.sh
./patch-redblink-local-addons.sh /home/steihl/dune-awakening-selfhost-docker
cd /home/steihl/dune-awakening-selfhost-docker
runtime/scripts/dune console restart
```

## Package

On Linux with `zip` installed:

```bash
bash scripts/package.sh
```

This creates:

```text
dist/eda-exchange-bot-<version>.zip
dist/eda-exchange-bot-<version>.zip.sha256
```

Publishing to RedBlink's community addon index can come later after the addon
is tested and reviewed.
