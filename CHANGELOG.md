# Changelog

All notable changes to Easy Dune Admin are documented here.

## 0.7.7-alpha

### Added

- Added an admin-only New Player Kit grant button based on IceHunter / Ryan Wilson's MIT-licensed `t1-starter` pack definition, using RedBlink's normal item grant command for the actual grants.
- Added admin-only Builder Supply Packs that insert curated construction resources into a selected character's main backpack after validating free slots.
- Added an admin-only four-container Base Storage Warehouse Fill that discovers owned large base containers, validates four empty selections, and inserts a curated warehouse pack.
- Added starter-kit attribution to the third-party notices and README credits.
- Updated Developer Class Progression warnings to note that advanced trainer unlocks appear to require full multi-quest chains, not a single observed completion tag.
- Updated the Medium Ornithopter kit with a RepairTool5 and WeldingMaterial, and stacked the grants page Medium kit panel directly under the Scout Thopter panel.

## 0.7.5-alpha

### Changed

- Added purple offline-character markers to Live Map and VIP self-teleport map views, with player online status shown in map marker/list text.
- Added Admin Panel wrappers for RedBlink v1.3.3 `dune admin skill-module`, using RedBlink's MIT-licensed skill-module catalog for dropdown labels and level validation.
- Added Admin Panel RedBlink v1.3.3 kick controls for one selected player or all online players.
- Added Admin Panel RedBlink v1.3.3 coordinate-based vehicle spawning through `dune admin spawn-vehicle-at`, paired with the existing draggable/double-click Vehicle Live Map coordinate workflow.
- Kept the RedBlink command wrappers attributed in README/third-party notices rather than copying RedBlink's RabbitMQ payload implementation.

## 0.7.4-alpha

### Changed

- Split the former `app.py` monolith into a small launcher, `eda_core.py` for shared configuration/helpers/services, and `eda_routes.py` for Flask and Socket.IO route registrations.
- Kept existing routes, templates, and admin workflows behavior-compatible while reducing future app.py bloat.
- Added an admin single-item overrepair picker that discovers inventories and item rows per selected character, for uniques or other items missed by the bulk overrepair pass.
- Updated VIP self-overrepair to cover every inventory row owned by the linked character while still requiring item CurrentDurability.
- Added configurable map instance plumbing for future multi-sietch and dual Deep Desert setups, plus an admin map partition discovery endpoint and server-specific partition warnings in teleport/map docs and placards.
- Replaced raw partition entry on Live Map and VIP self teleport with a DB-observed map partition picker, marked as experimental/untested until additional instances are available.
- Replaced manual market Seed Exchange ID entry with a DB-observed exchange selector.
- Added manual market seed stock for RocketAmmo, InfantryRocketAmmo, Napalm, Healkit Mk6, Iodine Pill, Sapho Juice, Melange Spiced Wine, Personal Light, and Blank Sinkchart.
- Added an automated market reseed loop that clears Revy's NPC listings and reseeds preset stock immediately once, then on a configurable interval.
- Added a full-width Dashboard online player table and removed FLS display from Who's Online output.
- Added admin Solari Coin inventory-stack lookup, add, and set-exact correction tools.
- Added admin Solari Credit lookup, add, and set-exact correction tools using `dune.player_virtual_currency_balances`.
- Updated Specialization XP tools to target character pawn actor IDs, matching the supplied query research.
- Added Developer-gated tools to grant missing all-track specialization rows at 0 XP for testing, or max all specialization tracks plus discovered keystones.
- Moved the broken Class Progression preset dropdown to a hidden Developer page protected by an admin login plus a separate key gate. It is marked WIP/experimental and includes removal actions for Planetologist, Trooper, and Advanced Bene Gesserit test tags.
- Moved research points, skill points, specialization tools, and journey progression presets behind the hidden Developer page; normal Character XP and Set Character Level remain on the Admin Panel.
- Added a login-time installation profile switch for Linux Host, RedBlink Docker Container, and experimental Hyper-V via SSH command routing.
- Added installation-mode UX gating so host installer/shell tools are hidden or relabeled when running in Docker or Hyper-V modes.
- Added a VIP self-only emergency return button using the same configured Hagga Basin safe point as the admin emergency return tool.
- Marked journey progression presets as testing/research-only because manual advancement can currently lock the character out of the 3rd combat skill slot.
- Documented that progression edits may require relogging, restarting the affected map, or restarting the battlegroup. Restarts can appear slow, and login may briefly show an error before recovering.
- Updated RedBlink stack target to `v1.3.3` and expanded Server Management around the v1.3.3 command surface: battlegroup readiness/version/ports/doctor, autoscaler, Sietches, memory tuning, update checks, restart schedule status, and selected `dune admin` helpers.
- Added Admin Panel RedBlink v1.3.3 helpers for water container/fillable refill, player location lookup, and validated vehicle spawning in front of an online player.
- Added VIP self-only water container/fillable refill using RedBlink's `dune admin refill-water` helper.
- Documented that RedBlink v1.3.3 currently ships one grant-template (`scout-ornithopter-mk6`); Easy Dune Admin's Medium Ornithopter kit remains a bundled item-grant workflow.
- Changed Server Management memory tuning from typed map names to DB/stack-discovered map dropdowns showing map labels, active/max dimensions, type, and current memory where RedBlink reports them.
- Added an admin emergency vehicle actor delete tool for cleaning up spawned/stuck vehicles such as accidental cargo containers.
- Added an experimental Docker preview package under `docker-preview/` and linked it from the main README files.

### Planned

- `0.7.8+` candidate: evaluate faction manipulation tools after faction membership and related database state can be captured and tested safely.

## 0.6.6-rc2

### Added

- Renamed project branding and repository references to Easy Dune Admin.
- Added VIP role tools for linked characters.
- Added admin-managed exact in-game character-name linking for VIP accounts.
- Added VIP self-only overrepair for the linked character inventory.
- Added VIP self-only offline teleport using the linked character account/FLS ID.
- Added VIP self-only Mk6 Scout and Mk6 Medium Ornithopter grants.
- Added admin-only Lightning Gun kit grant through the RedBlink item grant command.
- Added admin-only SolarisCoin grant with preset amount dropdown.
- Added admin-only research point setter for selected characters.
- Added admin-only character XP grant for the actual displayed character level.
- Added admin-only set character level tool using the same level XP curve.
- Added admin-only skill point grant that adds usable skill points without changing character level XP.
- Added WIP/unconfirmed admin-only specialization XP grant for Combat, Crafting, Gathering, Exploration, and Sabotage tracks.
- Added admin-only specialization reset for one track or all tracks plus keystones.
- Added experimental admin-only progression preset apply/reset tools for curated journey roots.
- Added admin-only preset market seeding.
- Added Seed Exchange ID override for servers whose visible player market is not the DB `Global` exchange id.
- Added per-run market price multiplier tuning, defaulting to 5x.
- Added 8-listing boost for market-seeded items/schematics named wing, track, or locomotion.
- Added 2.5x refined-resource category price multiplier.
- Added raw-resource category price tuning with special overrides for spice, titanium, stravidium, agave seeds, and basalt.
- Added clear-only NPC market listing cleanup for the market bot.
- Added market bot buyback for player listings priced at or below 60% of the current preset price.
- Added start/stop controls for automated 30-minute market buyback sweeps.
- Added Admin UI controls for buyback threshold, max buys per sweep, and sweep interval.
- Changed buyback sweep Start to run one sweep immediately before continuing on the interval.
- Added bundled IceHunter-derived market item data and third-party MIT notice.
- Added admin vehicle teleport support for Ornithopter, Sandbike, Buggy, TreadWheel, and SandCrawler actor families.
- Added zoomable/draggable admin vehicle map with marker selection and double-click coordinate targeting.
- Added `restart.sh` and `shutdown.sh` helpers for screen/headless daemon control.

### Changed

- Restricted operator access away from Infrastructure Services, Advanced Management, and logs.
- Updated viewer/VIP privacy handling so sensitive database IDs are not exposed to lower roles.
- Updated vehicle teleport warnings to document that loaded vehicle actors require an affected map/server restart.
- Updated live map mouse-wheel behavior so normal scrolling moves the page and Ctrl/Command+wheel zooms the map.
- Updated dashboard RedBlink stack display variable.
- Removed hard dependency on `dune.inventories.type` for character inventory lookup to support stacks without that column.

### Attribution

- Market tooling research, category mapping, bundled market item data, progression preset structure, specialization XP research, and character-level XP curve research are adapted from IceHunter / Ryan Wilson's MIT-licensed `dune-admin` project. See `THIRD_PARTY_NOTICES.md`.
- RedBlink's MIT license notice is included for the companion stack this panel targets and the wrapper/admin command workflows it uses. See `THIRD_PARTY_NOTICES.md`.
- Linked upstream repositories for RedBlink's `dune-awakening-selfhost-docker` and IceHunter / Ryan Wilson's `dune-admin` in the README and third-party notices.

## 0.6.5-rc1

### Added

- Updated RedBlink stack target to `v1.3.2`.
- Added RedBlink map runtime controls:
  - `dune maps list`
  - `dune maps mode`
  - `dune maps set <map> dynamic`
  - `dune maps set <map> always-on`
  - `dune maps reconcile`
- Added Deep Desert dual PvP/PvE controls.
- Added grouped restart services.
- Added DB health/status/list/backup controls.
- Added `.gitattributes` line-ending guard.
- Added `setup.sh`.
- Added runtime map and banner assets.
- Added GitHub README images under `images/`.

### Changed

- Hardened browser shell fitting.
- Improved `start.sh`.
- Updated release packaging and GPLv3 metadata.
