# Release Cleanup Notes

These notes track temporary/private-test changes made while getting `EDA
Exchange Bot` to appear in RedBlink Dune Docker Console. Review them before
publishing this addon to RedBlink's community addon index.

`EDA Exchange Bot` started as a read-only market seed preview and now uses
RedBlink's permissioned `database.execute` addon bridge for market seed and
buyback sweeps. It also uses `database.query` for the exchange selector. Do not
add DB credentials to addon static files.

## Temporary Compatibility Work

- `patch-redblink-local-addons.sh` is a private testing helper, not part of the
  addon package. It was used for pre-v1.3.16 private stack testing when
  installed-only addons were hard to surface in the Addons panel.
- RedBlink v1.3.16 includes the multi-statement `database.execute` result
  normalization needed by backup-protected addon write actions. Do not ship a
  RedBlink UI/API patch with the addon package.
- Any local runtime copy under
  `<redblink-stack>/runtime/addons/installed/eda-exchange-bot` is generated/test
  output. Do not treat it as source of truth.

## Intended Addon Source

The source/test workspace is:

```text
redblink-addons/eda-exchange-bot
```

The actual addon package is only:

```text
addon.json
web/
```

`scripts/`, `README.md`, `install-eda-exchange-bot.sh`, and
`patch-redblink-local-addons.sh` support development/private testing and are not
included by RedBlink's template `scripts/package.sh`.

## Keep Unless Design Changes

- `addon.json` uses object-form permissions to match RedBlink's template
  validator. The Exchange Bot requests `database:read` and `database:write`.
- `web/index.html` includes `data-addon-id="eda-exchange-bot"`.
- `install-eda-exchange-bot.sh` writes `enabled`, `approvedPermissions`,
  `installedAt`, and `sha256`, matching the installed state shape observed from
  RedBlink's `leadership-board-demo`.
- Community-review installs should remain disabled with no pre-approved
  permissions. Use the helper's `--dev-enable` mode only for private VM tests.
- DB credentials must stay in RedBlink Console configuration, using
  `ADMIN_DATABASE_URL` or the `DUNE_DB_*` environment variables.
- `.gitignore` ignores `redblink-addons/*/dist/`.
- `docs/REDBLINK_ADDON_STRATEGY.md` points to this folder as the addon
  workspace.

## Before Community Submission

```bash
cd redblink-addons/eda-exchange-bot
node scripts/validate.js
bash scripts/package.sh
```

Submit the resulting `dist/eda-exchange-bot-<version>.zip` and SHA-256 through
RedBlink's community addon flow only after the package validates and the
community index entry points at the reviewed release asset.
