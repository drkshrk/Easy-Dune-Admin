# RedBlink Console Addon Strategy

Easy Dune Admin remains a standalone companion panel. RedBlink v1.3.16 also
supports permissioned Dune Docker Console addons, so selected Easy Dune Admin
features can be cherry-picked into native Console addon slices.

## Current Addon Slice

The Infrastructure panel can install/update an `eda-exchange-bot` addon under:

```text
<redblink-stack>/runtime/addons/installed/eda-exchange-bot
```

The source/test workspace for this addon lives in:

```text
redblink-addons/eda-exchange-bot
```

That folder follows RedBlink's addon template shape (`addon.json`, `web/`,
`scripts/validate.js`, and `scripts/package.sh`) and includes a private VM
install helper for the `docs/local-development.md` flow.

The first feature slice is the exchange seeder:

- `entry.navigation`: `EDA Exchange Bot`
- `entry.path`: `web/index.html`
- permission: `database:read`, `database:write`
- bundled data: `web/market-seed-plan.json`
- feature: Easy Dune Admin market seed preview, one-shot NPC seeding, buyback
  sweeps, EDA NPC listing clears, and unsafe NPC listing cleanup

This proves the native addon flow without depending on Easy Dune Admin's
standalone login or published port, while still using RedBlink's permissioned
database bridge and backup behavior for writes.

RedBlink v1.3.16 includes the multi-statement `database.execute` result
normalization needed for the addon's backup-protected write actions to return
their final summary rows. The inspected bridge still exposes static UI request
actions only (`database.query` and `database.execute` for this addon), with no
addon scheduler/storage bridge yet. Automated/background exchange sweeps should
therefore remain in standalone Easy Dune Admin until RedBlink publishes a
persistent addon task path.

## Good Cherry-Pick Candidates

- Player snapshot / online roster: `players:read`
- VIP-style self info if RedBlink exposes current-user identity later
- Market/catalog read-only views: `database:read`
- Visual item picker for RedBlink's existing grant endpoints, if exposed by the
  Console bridge or a future addon action
- Server status widgets: `server:status`
- Broadcast helpers: `broadcast:send`

## Panel Comparison

RedBlink v1.3.16 already has strong native Console panels for core server
ownership:

- Players and character admin
- Care packages
- Backups, updates, logs, and services
- Database browsing/querying
- Live maps and map settings
- Admin item, vehicle, broadcast, and restart helpers

Easy Dune Admin currently adds the most value where it has accumulated
opinionated workflows, catalog cleanup, or research tooling:

- Curated visual item catalog and local icon handling
- Market seeder rules, unsafe-template cleanup, and exchange category repair
- Item Edits / augment stat research
- Progression recovery experiments and faction/prescience helpers
- VIP/self-service workflows
- Docker-mode EDA install maintenance, port switching, and standalone APK/PWA

Native RedBlink addon slices should therefore complement the Console instead of
rebuilding whole EDA pages inside it.

## Recommended Addon Test Order

1. **EDA Exchange Bot**
   - Status: implemented as the first local addon slice.
   - Permission: `database:read`, `database:write`.
   - Why: this is the best first real test because it is uniquely Easy Dune
     Admin: prices, category masks, parent-bucket coverage, unsafe exclusions,
     and listing counts can be reviewed inside RedBlink's addon UX before
     triggering the seed, buyback, or cleanup write through RedBlink's bridge.

2. **Catalog Browser / Visual Item Picker**
   - Status: implemented as `EDA Catalog Editor`.
   - Permission: none while edits are browser-local with full catalog/patch
     export. Future server-side persistence should use `files:addon-data` when
     RedBlink exposes bridge actions for it.
   - Why: this is visually distinctive EDA value, gives RedBlink a clean test
     case for larger static data, and lets admins correct catalog names,
     categories, tradeable flags, prices, stack hints, and icon metadata without
     hand-editing JSON.

3. **EDA Player Snapshot**
   - Permission: `players:read`.
   - Why: useful as a bridge/API smoke test, but RedBlink already has strong
     native player panels, so this is less distinctive than market tooling.

4. **Unsafe Market Cleanup Report**
   - Permission: `database:read` for reporting-only variants; `database:write`
     is already used by EDA Exchange Bot for the explicit cleanup button.
   - Why: useful to other admins, and worth keeping as a separate report view
     if RedBlink wants visibility without exposing cleanup.

5. **Augment Research Viewer**
   - Permission: `database:read`.
   - Why: compare selected item/augment stats without writing. The raw editor
     should stay standalone until the write shape is better understood.

6. **Broadcast Presets**
   - Permission: `broadcast:send`.
   - Why: small, low-data, and uses an existing RedBlink permission. Good test
     for write-like bridge UX without database risk.

7. **Progression Repair Diagnostics**
   - Permission: `database:read`.
   - Why: diagnostics are useful inside Console. Actual repair buttons should
     stay standalone or wait for narrow RedBlink bridge actions.

## Heavier Candidates

These should stay standalone until the RedBlink bridge exposes narrower actions
or the permission tradeoff is deliberate:

- Item row editor / augment editor: `database:write`
- Market seeder: `database:write`
- Progression repair tools: `database:write`
- Restart/destructive server actions: `server:restart`

## Implementation Rules

- Keep standalone Easy Dune Admin routes and UI working.
- Add native addon slices as separate static addon UI files using RedBlink's
  `dune-addon-request` / `dune-addon-response` bridge.
- Request the narrowest RedBlink addon permission possible.
- Prefer RedBlink bridge actions over direct SQL where the Console exposes them.
- If a feature needs direct SQL, make the query path explicit and expect
  RedBlink's bridge to create a backup before writes.
