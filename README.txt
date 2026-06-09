Easy Dune Admin
===============

Independent companion administration platform for RedBlink's Dune Awakening
self-hosted Docker stack.

Status
------

Panel version: 0.8.6-beta
Target RedBlink Stack: v1.3.3
License: GPLv3
Platform: Linux
Python: 3.11+

This beta is intended for private/LAN/VPN-hosted self-hosted servers.

Easy Dune Admin is an independent webadmin project built to support RedBlink's
MIT-licensed dune-awakening-selfhost-docker stack:
https://github.com/Red-Blink/dune-awakening-selfhost-docker

Development is being continued with RedBlink's permission, while keeping
RedBlink's stack, scripts, command workflows, and contributors credited where
they are used or targeted.


Security Notes
--------------

- LAN/private/VPN use only.
- Do not expose this panel directly to the public internet.
- Use a reverse proxy, HTTPS, and additional authentication before any
  wider exposure.
- Basic access testing has been performed over direct LAN, VPN, and HTTPS
  reverse-proxy paths. Command-level behavior should still be verified on your
  own stack before relying on high-impact admin actions remotely.
- The panel can grant items, restart services, run database utilities,
  repair vehicles, teleport offline characters, and optionally open a
  browser-based host shell.
- Direct SQL and host shell features are intentionally admin-only and
  should be treated as high-trust tools.
- setup.sh creates /etc/sudoers.d/dune-web-admin with a restricted allowlist
  for only the optional Infrastructure installer commands Easy Dune Admin
  actually calls. It does not grant NOPASSWD: ALL.
- Viewer accounts are intentionally privacy-limited. They can see
  viewer-safe status, online player names, Funcom IDs, and map markers, but they
  cannot view sensitive database identifiers such as raw player IDs,
  account IDs, FLS IDs, direct logs, or admin database output.


Features
--------

Dashboard:
- Live CPU/RAM/Disk usage bars
- Network RX/TX statistics
- AJAX auto-refresh
- World/player/vehicle summary cards
- Full-width online player table with character, status, Funcom ID, map, and
  partition

Live Maps:
- Hagga Basin live map
- Deep Desert map support
- Configurable map instances for multi-sietch / dual Deep Desert setups
- Player/vehicle/base markers
- Offline character markers render purple so they are distinct from online players
- Mouse-wheel zoom
- Drag panning
- Click-to-fill teleport coordinates

Teleportation:
- Offline teleportation
- Character dropdown targeting
- Emergency return to safe Hagga Basin point
- Live map and VIP self teleport use a DB-observed map partition picker
  instead of raw partition entry
- Multi-partition map/teleport support is experimental and currently
  untested until additional Survival or Deep Desert instances are available
- Default Hagga Basin partition: 1
- Default Deep Desert partition: 8
- Partition IDs are server-specific and may differ between multiple Survival
  or Deep Desert instances

Vehicle Teleport:
- Admin-only vehicle relocation using dune.actors
- Preserves existing vehicle rotation while updating map, partition, and XYZ
- Supported actor families: Ornithopter, Sandbike, Buggy, TreadWheel, SandCrawler
- Zoomable, draggable admin vehicle map with double-click coordinate targeting
- Requires restarting the affected map/server instance before loaded vehicles
  appear at the new location
- Z-axis warning because below-terrain values can place vehicles underground

VIP Tools:
- VIP role with viewer-safe access plus self-service tools
- Admin-managed exact character-name link for each VIP web account
- Self-only overrepair across all inventories owned by the linked character,
  including equipped/hotbar rows with current durability
- Self-only offline teleport using the linked character account/FLS ID
- Self-only Mk6 Scout and Mk6 Medium Ornithopter grants

Item Grants:
- Item search
- Item grant tools
- Admin-only Builder Supply Packs that insert curated build resources into
  empty main-backpack slots after validating free space. These can temporarily
  overload character carry weight, so equip a build tool before using them.
- Admin-only Base Storage Warehouse Fill that discovers owned large base
  containers, validates four empty selections, and fills them with a curated
  four-box resource/component layout. Restart the affected map before expecting
  new container contents to appear in game.
- Admin-only Base Storage Empty tool that discovers owned base storage
  containers of any size, validates up to four selected containers, and deletes
  only their item rows. Restart the affected map before expecting emptied
  containers to update in game.
- Mk6 Scout Ornithopter grant
- Mk6 Medium Ornithopter grant
- Medium thopter kit includes 250 rockets, one RepairTool5, and 500
  WeldingMaterial
- Admin-only Lightning Gun kit grant using the normal RedBlink item grant command
- Admin-only SolarisCoin grant with preset amount dropdown
- Admin-only Solari Coin inventory-stack lookup, add, and set-exact correction tools
- Admin-only Solari Credit lookup, add, and set-exact correction tools for the
  live exchange/bank balance
- Admin-only research point setter for selected characters
- Admin-only character XP grant for the actual displayed character level
- Admin-only set character level tool using the same level XP curve
- Admin-only skill point grant that adds usable skill points without changing
  character level XP
- Admin-only live unspent skill point setter using RedBlink v1.3.3's dune admin
  skill-points / SkillsSetUnspentSkillPoints RabbitMQ command. This is an
  experimental compare-path that sets the current unspent value; it may not
  change total earned skill points.
- Admin-only bulk skill-module presets for catalog-validated skill
  key/capstone and ability unlock testing through RedBlink v1.3.3's dune admin
  skill-module helper
- Item grants target the selected player/account inventory path and do not use
  map partition IDs
- WIP/unconfirmed Developer-only specialization tools for Combat, Crafting,
  Gathering, Exploration, and Sabotage tracks. These now target character
  pawn actor IDs, can add XP to one track, grant missing all-track rows at 0
  XP for testing, or max all tracks plus discovered keystones.
- Developer-only specialization reset for one track or all tracks plus keystones
- WIP/experimental Developer-only Class Progression preset dropdown for
  observed trainer/class unlock tag bundles. Currently appears nonfunctional
  for actual in-game class unlocks because the account tags alone are not
  sufficient; advanced trainer unlocks appear to require full multi-quest
  chains rather than one completion tag. The hidden /developer page also
  includes removal actions for the Planetologist, Trooper, and Advanced Bene
  Gesserit test tags.
- Experimental Developer-only progression preset apply/reset tools for curated
  journey roots. These are for testing/research only because advancing journey
  rows this way can currently lock the character out of the 3rd combat skill
  slot.
- Progression edits may require relogging, restarting the affected map, or
  restarting the battlegroup. Restarts can appear slow, and login may briefly
  show an error before recovering.

Market Tools:
- Admin-only preset market seeding
- Seeds NPC exchange listings for equippable items, schematics, and resources
- Adds manual NPC stock for RocketAmmo, InfantryRocketAmmo, Napalm, Healkit
  Mk6, Iodine Pill, Sapho Juice, Melange Spiced Wine, Personal Light, and
  Blank Sinkchart
- Uses a Revy-style bot owner and is_npc_order = TRUE
- Seed Exchange selector is populated from observed database exchange IDs and
  supports servers whose visible player market is not the DB Global exchange id
- Default preset clears only the market bot's existing NPC listings before reseeding
- Per-run price multiplier input defaults to 5x so Solari keeps value
- Items or schematics with names/IDs containing wing, track, or locomotion
  seed 8 listings by default
- Refined resources use an additional 2.5x category price multiplier
- Raw resources use an additional 5x category price multiplier, with
  overrides for Spice Sand/Residue, Titanium Ore, Stravidium Mass, Agave
  Seeds, and Basalt Stone
- Clear NPC Market Listings removes the bot's NPC listings without relisting
- Buy Eligible Player Listings lets Revy buy player listings priced at or
  below 60% of the current preset price
- Buyback threshold, max buys per sweep, and sweep interval are editable in
  the Admin UI
- Start/Stop Buyback Sweep controls run Revy buyback immediately once, then
  on the configured interval while Easy Dune Admin is running
- Start/Stop Market Reseed controls clear Revy's NPC listings and reseed
  preset stock immediately once, then on the configured interval while Easy
  Dune Admin is running
- Market category mapping and item-data research adapted from IceHunter /
  Ryan Wilson's MIT-licensed dune-admin project

Server Management:
- Grouped restart controls
- Gameplay services: Survival, Deep Desert, Overmap
- Infrastructure services: Gateway, Director, Text Router
- Map spawn controls
- RedBlink v1.3.3 battlegroup overview controls:
  - dune status
  - dune ready
  - dune version
  - dune ports
  - dune ps
  - dune servers
  - dune doctor
- RedBlink v1.3.3 map runtime controls:
  - dune maps list
  - dune maps mode
  - dune maps set <map> dynamic
  - dune maps set <map> always-on
  - dune maps reconcile
- RedBlink v1.3.3 autoscaler controls:
  - dune autoscaler status
  - dune autoscaler logs
  - dune autoscaler start|stop|restart
- RedBlink v1.3.3 Sietch and memory controls:
  - dune sietches list|show|dimensions|sync|validate
  - dune memory status|list-maps|set|unset
- RedBlink v1.3.3 update check/status controls:
  - dune self-update check|list
  - dune update check
  - dune update auto status
  - dune restart-schedule status
- RedBlink v1.3.3 admin helpers:
  - dune admin players
  - dune admin player-location
  - dune admin refill-water
  - dune admin spawn-vehicle
  - dune admin spawn-vehicle-at
  - dune admin skill-module
  - dune admin kick
  - dune admin vehicle-list
  - dune admin item-search
  - dune admin history

RedBlink v1.3.3 currently exposes one grant-template, scout-ornithopter-mk6.
Easy Dune Admin's Medium Ornithopter kit uses the normal RedBlink item grant
command as a bundled workflow rather than a RedBlink grant-template.

Deep Desert:
- Dual PvP/PvE status
- Enable dual mode
- Disable dual mode
- Force disable dual mode
- Bootstrap dual mode
- Repair dual mode

Database Tools:
- DB Health
- DB Status
- List Backups
- Create Backup

Restore/import/delete database actions are intentionally not exposed yet.

Infrastructure:
- Host diagnostics
- Docker diagnostics
- Guided RedBlink installer
- Browser-based host shell
- Open Shell + dune init
- Open Shell + dune manager

Mobile / PWA:
- Progressive Web App metadata for install-to-home-screen support on phones
  and tablets
- Uses the existing Easy Dune Admin icons for app installation
- Root-scoped service worker serves a simple offline fallback when the panel is
  unreachable
- Authenticated pages and API responses remain network-first and are not
  intentionally cached for offline admin-data viewing
- Keep mobile access behind LAN/VPN or other private access controls; do not
  expose the panel directly to the public internet
- Optional sideloadable Android APK wrapper lives in android-app/. It opens
  your existing Easy Dune Admin server in a native WebView and stores only the
  server URL on the phone.
- Admin users can reach Developer Tools from the hamburger menu in the
  Android/PWA UI. The page still requires the separate Developer key before
  any research commands are visible.

Android PWA install:

1. Connect the phone to the same LAN or VPN as the Easy Dune Admin server.
2. Open Chrome on Android and browse to http://SERVER-IP:8089.
3. Log in once so Chrome sees the app as usable.
4. Open Chrome's menu and choose Install app or Add to Home screen.
5. Launch Easy Dune Admin from the new home-screen icon.

If Chrome only offers Add to Home screen, use that option. No rooted phone is
required.

Android APK build:

1. Open android-app in Android Studio.
2. Build app with Build > Build Bundle(s) / APK(s) > Build APK(s).
3. Or build from a terminal with the included Gradle wrapper. Java 17 and the
   Android SDK are still required.

cd android-app
.\gradlew.bat assembleDebug

Linux/macOS:

cd android-app
chmod +x gradlew
./gradlew assembleDebug

The debug APK is written to:

android-app/app/build/outputs/apk/debug/EDA.apk

If the Gradle wrapper starts but fails on Android SDK licenses or missing
packages, install/accept the SDK components first:

$env:ANDROID_SDK_ROOT="$env:LOCALAPPDATA\Android\Sdk"
& "$env:ANDROID_SDK_ROOT\cmdline-tools\latest\bin\sdkmanager.bat" --install "platforms;android-35" "build-tools;34.0.0" "platform-tools"
& "$env:ANDROID_SDK_ROOT\cmdline-tools\latest\bin\sdkmanager.bat" --licenses

If the SDK reports package.xml (Access is denied), repair permissions or
reinstall that SDK platform/build-tools with Android Studio's SDK Manager.

Android APK sideload:

1. Copy EDA.apk to the phone by USB, file share, cloud drive, or Android file
   transfer.
2. Open EDA.apk from the phone's Files app or file manager.
3. Android will usually block the first install attempt because the APK was not
   installed from Google Play.
4. When prompted, open the Android settings screen for that file
   manager/browser and allow installs from that source.
5. Return to the APK and continue the install.
6. Launch Easy Dune Admin.
7. Enter your LAN/VPN/HTTPS Easy Dune Admin URL, such as
   http://SERVER-IP:8089 or https://eda.example.com.

No rooted phone is required. To update an existing sideloaded install, build a
new EDA.apk and install it over the old one.

Release packaging note:

- The Android wrapper source lives in android-app/ and should be committed with
  the repository.
- The built EDA.apk is ignored by Git and should be attached to GitHub Releases
  only as an optional convenience artifact.
- Suggested release wording: Optional Android WebView wrapper. Sideload at your
  own discretion. Android will block the first install attempt because this APK
  is not from Google Play; allow installs from that source if you trust this
  release. The APK stores only the configured Easy Dune Admin server URL and
  defaults to http://127.0.0.1:8089.


Requirements
------------

sudo apt update
sudo apt install -y python3 python3-pip python3-venv git curl


Installation
------------

git clone https://github.com/n00bgames/Easy-Dune-Admin.git easy-dune-admin
cd easy-dune-admin
cp .env.docker.example .env
nano .env
chmod +x rebuild_docker.sh docker/entrypoint.sh
./rebuild_docker.sh

Set REDBLINK_HOST_DIR in .env to the host path where RedBlink's stack lives.
The default web port is 8089.

Browse to:

http://SERVER-IP:8089

Docker is the primary supported install method as of 0.8.6-beta. Runtime
webadmin state is stored in the named Docker volume easy-dune-admin-data, so
normal rebuilds preserve users.db, roles, and logs. Do not run
docker compose down -v unless you intentionally want to reset the webadmin.

See DOCKER.md for Docker mount and production notes.


Advanced Local Install
----------------------

The legacy local Python launch remains available for Linux hosts that prefer
running Easy Dune Admin directly outside a container:

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

chmod +x setup.sh
./setup.sh

chmod +x start.sh restart.sh shutdown.sh
./start.sh

Browse to:

http://127.0.0.1:8089


Runtime Control
---------------

./start.sh --screen       # detached GNU screen session
./start.sh --headless     # nohup background process with webadmin.pid
./restart.sh              # restarts using the detected/current launch mode
./shutdown.sh             # stops screen or headless mode

For screen mode:

screen -r dune-admin-web

Detach from screen with Ctrl+A, then D.


Line Endings
------------

The repository includes .gitattributes rules to keep Linux shell scripts
using LF line endings.

If shell scripts still fail with "cannot execute: required file not found"
or "/bin/bash^M", run:

find . -type f -name "*.sh" -exec sed -i 's/\r$//' {} \;
chmod +x setup.sh start.sh restart.sh shutdown.sh


Configuration
-------------

Default RedBlink stack path:

~/dune-awakening-selfhost-docker

Override with:

export DUNE_ROOT=/path/to/dune-awakening-selfhost-docker

For Docker mode, keep DUNE_ROOT_CONTAINER equal to REDBLINK_HOST_DIR in .env.
RedBlink restart/spawn scripts create sibling containers through the host
Docker socket, so their bind-mount source paths must also exist on the host.
Mounting the stack at a container-only alias such as /redblink can break
dune restart survival because Docker looks for /redblink on the host.

Login installation profile:

Easy Dune Admin now has a login switch for Linux Host, RedBlink Docker
Container, and experimental Hyper-V via SSH operation. Linux Host and RedBlink
Docker Container run commands locally. Hyper-V via SSH runs those same
RedBlink/Docker commands through SSH on the Linux VM.

export EASY_DUNE_DEFAULT_INSTALL_MODE=linux
export EASY_DUNE_HYPERV_SSH_TARGET='steam@192.168.1.50'
export EASY_DUNE_HYPERV_DUNE_ROOT=/home/steam/dune-awakening-selfhost-docker

Leave the Hyper-V values unset unless you are using the Hyper-V profile.

Set a real secret before sharing or deploying:

export DUNE_SECRET_KEY='long-random-string'

Developer page key:

The hidden /developer page is for incomplete, dangerous, broken, experimental,
or research-only tools. Developer functions can corrupt progression, flags,
inventories, or player state if used casually. The page is admin-only and also
protected by a separate key hash. Set your own hash instead of relying on the
bundled fallback:

python3 - <<'PY'
from werkzeug.security import generate_password_hash
print(generate_password_hash("replace-this-with-your-developer-key"))
PY

export EASY_DUNE_DEVELOPER_KEY_HASH='pbkdf2:sha256:...'

Restart Easy Dune Admin after changing EASY_DUNE_DEVELOPER_KEY_HASH.

Optional high-trust infrastructure features:

export ENABLE_HOST_COMMAND_RUNNER=1
export ENABLE_STACK_INSTALLER=1
export ENABLE_HOST_SHELL=1

Optional RedBlink installer target override:

export REDBLINK_INSTALL_DIR=/path/to/dune-awakening-selfhost-docker

Optional multi-instance map/teleport override:

export EASY_DUNE_MAP_CONFIGS_JSON='{"HaggaBasin":{"key":"HaggaBasin","label":"Hagga Basin 1","actor_map":"HaggaBasin","image":"arrakis_hb.webp","width":8000,"height":8000,"min_x":-456752.21,"max_x":354547.46,"min_y":-450630.14,"max_y":353821.95,"flip_y":false,"default_partition_id":1},"HaggaBasin2":{"key":"HaggaBasin2","label":"Hagga Basin 2","actor_map":"HaggaBasin","image":"arrakis_hb.webp","width":8000,"height":8000,"min_x":-456752.21,"max_x":354547.46,"min_y":-450630.14,"max_y":353821.95,"flip_y":false,"default_partition_id":12}}'

Use verified partition IDs from your own database/runtime state. Do not
assume another server's Survival or Deep Desert partition IDs match yours.

Teleport-capable roles can query /api/map-partitions after logging in to see
observed dune.actors.map / partition_id pairs with actor, player, vehicle,
and base counts.


Docker Package
--------------

The root Dockerfile, docker-compose.yml, .env.docker.example,
docker/entrypoint.sh, and rebuild_docker.sh are the primary deployment package.
The container mounts the host RedBlink stack directory and Docker socket instead
of bundling RedBlink inside the image.

Docker webadmin state is stored in the named Docker volume
easy-dune-admin-data at /data, including /data/users.db and /data/logs.
Rebuilding the image should preserve users and roles as long as that volume is
not removed. Avoid:

  docker compose down -v

unless you intentionally want to reset the webadmin database.

See DOCKER.md for setup notes.


Runtime Assets
--------------

Runtime assets live in ./static:

- dune-admin.js
- dune-admin.png
- dune-admin-large.png
- arrakis_hb.webp
- deep_desert.webp

The map image files are required for the live map pages to render
properly.

Optional item icons are local-only. Easy Dune Admin ships catalog icon path
metadata, but does not redistribute Dune: Awakening icon image assets. For a
private install, place personally supplied icon files in static/item-icons in
the mounted Easy Dune Admin checkout, /data/item-icons for Docker-persistent
storage, or set EDA_ITEM_ICON_DIR to another local folder. Matching catalog
filenames are served to the item picker automatically, and the actual image
files are ignored from Git and Docker release builds. Developer Tools includes
an Item Icon Pack
Utility that lists present and missing local icon filenames and provides a
copyable filename manifest.

Easy Dune Admin includes an original base-schematic.png fallback for schematic
or blueprint entries that do not have an exact local icon match, plus an
original base-unknown.png question-mark fallback for other unmatched entries.


GitHub / README Images
----------------------

Documentation and GitHub page images live in ./images:

- dashboard.png
- dune-manager.png
- infrastructure.png
- live-map.png
- logo.png

When dashboard, live map, infrastructure, or GitHub README sections
change, remember to refresh the matching images before publishing.


Expected Layout
---------------

~/dune-admin-web/
|-- app.py
|-- requirements.txt
|-- setup.sh
|-- start.sh
|-- restart.sh
|-- shutdown.sh
|-- README.md
|-- README.txt
|-- LICENSE
|-- templates/
|-- static/
|   |-- dune-admin.js
|   |-- dune-admin.png
|   |-- dune-admin-large.png
|   |-- arrakis_hb.webp
|   `-- deep_desert.webp
|-- images/
|   |-- dashboard.png
|   |-- dune-manager.png
|   |-- infrastructure.png
|   |-- live-map.png
|   `-- logo.png
|-- users.db
|-- logs/
`-- venv/


Upgrade Notes
-------------

Before replacing a running copy:

cp -a ~/dune-admin-web ~/dune-admin-web.backup-before-0.8.6-beta

Preserve local runtime data:

- users.db
- logs/
- .env, if used

After updating:

git pull
cp .env.docker.example .env   # only if .env does not already exist
nano .env                     # verify REDBLINK_HOST_DIR and secrets
./rebuild_docker.sh

For the advanced local Python install, run pip install -r requirements.txt
inside the virtualenv and restart with ./restart.sh.


Known Issues
------------

- Map marker styling is functional but still being refined.
- Autoscaler controls are planned.
- Vehicle repair writes directly to dune.vehicle_modules stats JSON.
- Vehicle teleport writes to dune.actors, but loaded vehicle actors do not
  reload their transform until the affected map/server instance restarts.
- Gear overrepair requires items to be unequipped and in inventory.
- Single item overrepair discovers inventory rows per selected character, so
  inventory IDs do not need to match between players.
- Teleport partition IDs should be verified on each stack/server setup,
  especially when running multiple Survival or Deep Desert instances.


Planned
-------

- VIP self-only generic item grants
- Vehicle ownership discovery for VIP self-repair/teleport
- Live map side panel / scroll-safe layout
- Autoscaler controls
- Dynamic map discovery from RedBlink map runtime config


Release Notes
-------------

See CHANGELOG.md for full release history.

Current highlight for 0.8.6-beta: Easy Dune Admin now adds an admin-only Item
Edits workspace, visual item catalog selection, local icon-pack support, and
catalog editing tools for deeper item-stat and grant workflow research.

Looking ahead: faction manipulation tools are a likely future focus after
faction membership and the related database state can be captured and tested
safely.


Credits
-------

- RedBlink and contributors for the MIT-licensed
  dune-awakening-selfhost-docker stack this panel targets:
  https://github.com/Red-Blink/dune-awakening-selfhost-docker
  This project is being developed with RedBlink's permission; Easy Dune Admin
  remains an independent project and credits RedBlink's stack, scripts, command
  workflows, and the visual item-picker/care-package workflow concepts that
  inspired Easy Dune Admin's independent picker implementation.
- Funcom
- IceHunter / Ryan Wilson's MIT-licensed dune-admin project for market
  tooling research, category mapping, the Easy Dune Admin item catalog derived
  from bundled market item data, progression
  preset structure, specialization XP research, and character-level XP curve
  research:
  https://github.com/Icehunter/dune-admin
- Community researchers and testers; database research for some admin workflows
  was informed by early community testing.


License
-------

GPLv3. See LICENSE.

Third-party reference material remains under its original license. See
THIRD_PARTY_NOTICES.md for included MIT license text and attribution.


AI Collaboration Note
---------------------

Large portions of this project have been collaboratively created with the use
of generative AI tools, including ChatGPT and Codex.
