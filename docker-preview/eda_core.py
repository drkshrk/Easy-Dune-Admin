#!/usr/bin/env python3
"""
Easy Dune Admin
Panel version: 0.7.6-alpha
RedBlink stack compatibility target: v1.3.3

0.7.6-alpha RedBlink v1.3.3 support:
- Updates RedBlink stack target to v1.3.3.
- Adds Server Management controls for dune maps runtime modes.
- Adds controls for dynamic vs always-on map runtime behavior.
- Adds map reconcile command.
- Adds Deep Desert dual PvP/PvE status, enable, disable, bootstrap, and repair controls.
- Hardens browser shell fitting with FitAddon fallback/manual resize.
- Adds VIP self-service tools for linked characters.
- Adds admin market seeding tools with IceHunter attribution.
- Splits the former app.py monolith into launcher, core helpers, and routes.

SECURITY NOTES
--------------
- Do not expose this directly to the public internet.
- Viewer role cannot see raw player IDs or logs.
- Operator/admin can grant items, spawn maps, and restart services.
- Admin can run direct SQL utilities and manage users.
"""

import json
import os
import sqlite3
import subprocess
import select
import shlex
import signal
import pty
import fcntl
import termios
import struct
import threading
import time
import psutil
import re
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, redirect, render_template, request, session, jsonify, has_request_context

# Flask-SocketIO is required only for the optional full host shell.
# The app still imports it at startup for the /infrastructure terminal page.
from flask_socketio import SocketIO, emit, disconnect
from werkzeug.security import check_password_hash, generate_password_hash

import market_seed


# =========================================================
# CONFIGURABLE VALUES
# =========================================================

PANEL_VERSION = "0.7.6-alpha"
REDBLINK_STACK_VERSION = "v1.3.3"

# RedBlink stack path. Change this if your install lives elsewhere.
DUNE_ROOT = Path(
    os.environ.get(
        "DUNE_ROOT",
        str(Path.home() / "dune-awakening-selfhost-docker"),
    )
)

# Official RedBlink wrapper script.
DUNE_SCRIPT = DUNE_ROOT / "runtime/scripts/dune"

# RedBlink item catalog.
ITEMS_FILE = DUNE_ROOT / "runtime/data/admin-items.json"

# RedBlink skill-module catalog. This feeds the Admin Panel dropdown for the
# v1.3.3 `dune admin skill-module` helper. If RedBlink changes the catalog
# shape later, keep the browser-facing labels conservative and validate again
# before allowing writes.
SKILL_MODULES_FILE = DUNE_ROOT / "runtime/data/admin-skill-modules.json"

# RedBlink v1.3.3 vehicle spawn templates. These are used by the admin panel's
# "spawn in front of player" helper and should match runtime/data/admin-vehicles.json
# in the RedBlink stack. If RedBlink adds new vehicles/templates later, add them
# here after confirming the exact id/template values with `dune admin vehicle-list`
# or the stack's admin-vehicles.json file.
REDBLINK_VEHICLE_SPAWN_TEMPLATES = {
    "Sandbike": ["T1_ExtraSeat", "T2_Inventory", "T3_Boost", "T4_Scanner", "T5", "T6"],
    "Buggy": ["T3_Inventory", "T4_Boost", "T5_Mining", "T6_Combat"],
    "Tank": ["T6_CombatFire", "T6_CombatDart"],
    "Sandcrawler": ["T6_Harvesting"],
    "OrnithopterLight": ["T4_Inventory", "T5_Boost", "T6_Combat"],
    "OrnithopterMedium": ["T5_Inventory", "T6_Combat"],
    "OrnithopterTransport": ["T6_Boost"],
    "TreadWheel": ["T4_Passenger", "T5_Inventory", "T6_Boost"],
    "ContainerVehicle": ["Container"],
}

# RedBlink's refill-water helper defaults to a very large value when no amount
# is supplied. Keeping this visible lets server owners tune VIP/admin refill
# behavior without editing the route logic.
DEFAULT_WATER_REFILL_AMOUNT = int(os.environ.get("DEFAULT_WATER_REFILL_AMOUNT", "1000000"))

BASE_DIR = Path(__file__).resolve().parent

# Local webadmin state. In the normal non-container install this stays next to
# the app for backward compatibility. In the Docker package, docker-compose sets
# EDA_DATA_DIR=/data and mounts that path as a named volume so rebuilding the
# image does not wipe users.db or action logs.
APP_DATA_DIR = Path(os.environ.get("EDA_DATA_DIR", str(BASE_DIR))).resolve()
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = APP_DATA_DIR / "users.db"

# One-time Docker transition helper: older container builds wrote users.db to
# /app because BASE_DIR was the only state path. If that old file exists inside
# a container and the mounted data volume does not yet have a database, preserve
# it instead of making the admin recreate users after an upgrade.
LEGACY_DB_FILE = BASE_DIR / "users.db"
if DB_FILE != LEGACY_DB_FILE and LEGACY_DB_FILE.exists() and not DB_FILE.exists():
    try:
        import shutil
        shutil.copy2(LEGACY_DB_FILE, DB_FILE)
    except Exception:
        pass

# IceHunter / Ryan Wilson's MIT-licensed dune-admin project includes a richer
# exchange catalog than RedBlink's admin item list. We use this local copy for
# market seeding because it includes tradeable flags, stack sizes, category
# paths, rarity, tiers, and vendor prices. See README credits/third-party notes.
MARKET_ITEM_DATA_FILE = BASE_DIR / "data" / "icehunter-item-data.json"

# Market seed pricing is intentionally inflated from IceHunter's baseline so
# Solari keeps some value on small private servers. Set to 1 to use the
# original-style pricing scale, or tune higher/lower for your economy.
MARKET_PRICE_MULTIPLIER = int(os.environ.get("MARKET_PRICE_MULTIPLIER", "5"))

# Optional explicit Dune Exchange id for market seeding. Leave blank to use the
# game's Global exchange function. If seeded rows succeed but do not appear in
# the in-game exchange, set this to the exchange_id observed from a real player
# listing on your server.
MARKET_SEED_EXCHANGE_ID = os.environ.get("MARKET_SEED_EXCHANGE_ID", "").strip()

# Bot actor class used for NPC exchange listings. IceHunter's marketbot uses
# "Revy"; keeping the same value makes attribution and future compatibility
# straightforward. Change only if you know you need a separate market owner.
MARKET_BOT_CLASS = os.environ.get("MARKET_BOT_CLASS", "Revy")

# Preset stock counts. Equippable items and schematics are individual listings
# because most stack to 1. Resource-like stackables get one large listing.
MARKET_EQUIPPABLE_LISTINGS = int(os.environ.get("MARKET_EQUIPPABLE_LISTINGS", "2"))
MARKET_SCHEMATIC_LISTINGS = int(os.environ.get("MARKET_SCHEMATIC_LISTINGS", "2"))
MARKET_RESOURCE_STACK_SIZE = int(os.environ.get("MARKET_RESOURCE_STACK_SIZE", "1000"))

# Extra seed coverage for vehicle mobility parts that tend to be pain points.
# Matching checks both the template id and display name, case-insensitively.
# Override with, for example:
#   export MARKET_SPECIAL_NAME_TERMS='wing,track,locomotion,tread'
#   export MARKET_SPECIAL_NAME_LISTINGS=8
MARKET_SPECIAL_NAME_TERMS = [
    term.strip().casefold()
    for term in os.environ.get("MARKET_SPECIAL_NAME_TERMS", "wing,track,locomotion").split(",")
    if term.strip()
]
MARKET_SPECIAL_NAME_LISTINGS = int(os.environ.get("MARKET_SPECIAL_NAME_LISTINGS", "8"))

# Refined resources are more progression-critical than common raw mats. This
# multiplier is applied before the per-run market multiplier, so the default
# total for refined resources is baseline * 2.5 * 5.
MARKET_REFINED_RESOURCE_PRICE_MULTIPLIER = float(
    os.environ.get("MARKET_REFINED_RESOURCE_PRICE_MULTIPLIER", "2.5")
)

# Raw resource market tuning. The general raw-resource multiplier is separate
# from the browser's per-run market multiplier. Specific template overrides are
# keyed by the exact item template id from IceHunter's item-data catalog so they
# do not accidentally match unrelated item names.
MARKET_RAW_RESOURCE_PRICE_MULTIPLIER = float(
    os.environ.get("MARKET_RAW_RESOURCE_PRICE_MULTIPLIER", "5")
)
MARKET_RAW_RESOURCE_PRICE_OVERRIDES = {
    "SpiceSand": 10.0,
    "SpiceResidue": 10.0,
    "Basalt": 0.2,
    "T6ResourceA": 8.0,        # Titanium Ore
    "T6ResourceB": 8.0,        # Stravidium Mass
    "SaguaroResourceRaw": 10.0, # Agave Seeds
}

# Revy will buy player listings at or below this percentage of the price the
# current preset would list that same item for. Keep below 100 so players can
# profit by selling to each other, while still letting the bot provide liquidity.
MARKET_BUY_THRESHOLD_PERCENT = int(os.environ.get("MARKET_BUY_THRESHOLD_PERCENT", "60"))
MARKET_BUY_MAX_PER_CLICK = int(os.environ.get("MARKET_BUY_MAX_PER_CLICK", "500"))
MARKET_BUYBACK_INTERVAL_MINUTES = int(os.environ.get("MARKET_BUYBACK_INTERVAL_MINUTES", "30"))
MARKET_RESEED_INTERVAL_MINUTES = int(os.environ.get("MARKET_RESEED_INTERVAL_MINUTES", "30"))

# Logs follow EDA_LOG_DIR when set, otherwise live under APP_DATA_DIR/logs.
LOG_DIR = Path(os.environ.get("EDA_LOG_DIR", str(APP_DATA_DIR / "logs"))).resolve()
LOG_DIR.mkdir(parents=True, exist_ok=True)
ACTION_LOG = LOG_DIR / "actions.log"

POSTGRES_CONTAINER = "dune-postgres"

# Login-selectable installation profiles. Linux host and Dockerized webadmin
# both run commands locally; the Dockerized profile exists so the footer/login
# clearly reflects that Easy Dune Admin is running inside its own container with
# the RedBlink stack and Docker socket mounted. Hyper-V uses SSH to run the same
# RedBlink/Docker commands on the Linux VM. Set EASY_DUNE_HYPERV_SSH_TARGET to
# a value such as "steam@192.168.1.50" before using the Hyper-V profile.
INSTALLATION_MODES = {
    "linux": {
        "label": "Linux Host",
        "description": "Easy Dune Admin runs on the same Linux host as the RedBlink stack.",
    },
    "docker": {
        "label": "RedBlink Docker Container",
        "description": "Easy Dune Admin runs in its own container with Docker socket and RedBlink stack mounted.",
    },
    "hyperv": {
        "label": "Hyper-V via SSH",
        "description": "Experimental: Easy Dune Admin SSHes into the Hyper-V Linux VM to run RedBlink/Docker commands.",
    },
}
DEFAULT_INSTALLATION_MODE = os.environ.get("EASY_DUNE_DEFAULT_INSTALL_MODE", "linux").strip().casefold()
if DEFAULT_INSTALLATION_MODE not in INSTALLATION_MODES:
    DEFAULT_INSTALLATION_MODE = "linux"

# Hyper-V / remote Linux VM settings. These are deliberately environment-only
# because they contain host/user/path details that vary per installation and
# should not be committed into the project.
HYPERV_SSH_TARGET = os.environ.get("EASY_DUNE_HYPERV_SSH_TARGET", "").strip()
HYPERV_DUNE_ROOT = os.environ.get("EASY_DUNE_HYPERV_DUNE_ROOT", str(DUNE_ROOT)).strip()

# Change with:
# export DUNE_SECRET_KEY='long-random-string'
SECRET_KEY = os.environ.get("DUNE_SECRET_KEY", "change-this-secret-before-sharing")

# Developer tools are intentionally hidden behind a separate key gate because
# they may contain broken, dangerous, or research-only panels that should not be
# exposed to normal admins/end users. Store only a salted password hash here.
# Rotate with:
#   export EASY_DUNE_DEVELOPER_KEY_HASH='pbkdf2:sha256:...'
DEVELOPER_KEY_HASH = os.environ.get(
    "EASY_DUNE_DEVELOPER_KEY_HASH",
    "pbkdf2:sha256:1000000$njBZpe9vNjpJaBdwnqvoZw$5e11e89d643dd2ced4f02efbf7275873b100cd7e14d02f72e1ee984ce09b3176",
)

# =========================================================
# INFRASTRUCTURE / HOST ACCESS CONFIGURATION
# =========================================================
#
# These features are intentionally disabled by default.
# Enable only on a trusted LAN/VPN and only for trusted admins.
#
# Example:
#   export ENABLE_HOST_COMMAND_RUNNER=1
#   export ENABLE_HOST_SHELL=1
#   export ENABLE_STACK_INSTALLER=1
#
ENABLE_HOST_COMMAND_RUNNER = os.environ.get("ENABLE_HOST_COMMAND_RUNNER", "0") == "1"
ENABLE_HOST_SHELL = os.environ.get("ENABLE_HOST_SHELL", "0") == "1"
ENABLE_STACK_INSTALLER = os.environ.get("ENABLE_STACK_INSTALLER", "0") == "1"

# Where the RedBlink stack should be cloned/managed by the installer.
REDBLINK_REPO_URL = "https://github.com/Red-Blink/dune-awakening-selfhost-docker.git"
REDBLINK_INSTALL_DIR = Path(
    os.environ.get(
        "REDBLINK_INSTALL_DIR",
        str(Path.home() / "dune-awakening-selfhost-docker"),
    )
)

# Commands allowed in the simple command runner.
# This is separate from the full shell and intended for safer diagnostics.
ALLOWED_INFRA_COMMANDS = {
    "system_info": {
        "label": "Host System Info",
        "cmd": ["bash", "-lc", "uname -a && echo && free -h && echo && df -h / && echo && lscpu | grep -E 'Model name|CPU\\(s\\)|avx|avx2' || true"],
        "timeout": 30,
    },
    "docker_ps": {
        "label": "Docker Containers",
        "cmd": ["bash", "-lc", "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'"],
        "timeout": 30,
    },
    "docker_compose_ps": {
        "label": "Docker Compose Status",
        "cmd": ["bash", "-lc", f"cd {shlex.quote(str(REDBLINK_INSTALL_DIR))} && docker compose ps"],
        "timeout": 30,
    },
    "dune_status": {
        "label": "Dune Status",
        "cmd": ["bash", "-lc", f"cd {shlex.quote(str(REDBLINK_INSTALL_DIR))} && dune status || true"],
        "timeout": 45,
    },
}

# Manual prewarm map list. Names must match:
# ./runtime/scripts/dune sietches list
MAPS = [
    "DeepDesert_1",
    "SH_Arrakeen",
    "SH_HarkoVillage",
]

# Supported restart targets from:
# ./runtime/scripts/dune restart
RESTART_TARGETS = [
    "gateway",
    "director",
    "text-router",
    "survival",
    "overmap",
]

INFRASTRUCTURE_RESTART_TARGETS = {
    "gateway",
    "director",
    "text-router",
}

# RedBlink built-in template alias.
SCOUT_THOPTER_TEMPLATE = "scout-ornithopter-mk6"

# Curated Mk6 Medium Ornithopter bundle.
# NOTE: Inventory is intentionally Mk5 in the current known-good kit.
MEDIUM_THOPTER_BUNDLE = [
    ("OrnithopterMediumBoost_Unique_LessHeat_6", 1),
    ("OrnithopterMediumChassis_6", 1),
    ("OrnithopterMediumEngine_6", 1),
    ("OrnithopterMediumGenerator_PolarCap_6", 1),
    ("OrnithopterMediumHull_6", 1),
    ("OrnithopterMediumHullBack_6", 1),
    ("OrnithopterMediumHullFront_6", 1),
    ("OrnithopterMediumInventory_5", 1),
    ("OrnithopterMediumLauncher_6", 1),
    ("OrnithopterMediumLocomotion_Unique_Strafe_6", 6),
    ("FuelCanister_Large", 5),
    ("RocketAmmo", 250),
]

# Admin-only gift bundle derived from the freely shared lasgun SQL example.
# These are granted through RedBlink's normal grant-item-id command instead of
# direct item-row inserts, so inventory slot placement and item construction
# stay with the supported admin grant path.
LASGUN_AUGMENT_BUNDLE = [
    ("UniqueAr6_Electric", 1),
    ("T6_Augment_Lasgun1", 1),
    ("T6_Augment_Damage2", 1),
    ("T6_Augment_Acuracy1", 1),
]

# Admin-only starter kit adapted from IceHunter / Ryan Wilson's MIT-licensed
# dune-admin web/public/packs.json `t1-starter` pack. The RedBlink grant helper
# accepts template id, quantity, and durability, so the IceHunter quality=0
# field is intentionally omitted here. Keep this list conservative: it is meant
# to get a new private-server player moving, not to skip progression tiers.
NEW_PLAYER_STARTER_KIT = [
    ("Combat_Nati_ScavengerRags02_Boots", 1),
    ("Combat_Nati_ScavengerRags02_Gloves", 1),
    ("Combat_Nati_ScavengerRags02_Helmet", 1),
    ("Combat_Nati_ScavengerRags02_Bottom", 1),
    ("Combat_Nati_ScavengerRags02_Top", 1),
    ("Ammo", 500),
    ("HeavyAmmo", 500),
    ("Kindjal", 1),
    ("ChoamSda2", 1),
    ("HarkAr2", 1),
    ("MiningTool_1h_Heavy", 1),
    ("HighCapacityLiterjon", 1),
    ("BodyFluidExtractor", 1),
    ("Bloodsack_01", 1),
]

# Admin-only Solari grant. Keep this as the SolarisCoin template id so money
# gifts use the same grant path as item grants instead of direct SQL edits.
SOLARIS_COIN_ITEM_ID = "SolarisCoin"

# Preset Solari amounts exposed in the admin dropdown. Server owners can tune
# these values without touching the route logic below.
SOLARIS_GRANT_AMOUNTS = [
    10000,
    50000,
    100000,
    250000,
    500000,
    1000000,
]

# Admin-only stored Solari corrections edit SolarisCoin item stacks owned by
# the selected character actor. Keep this capped so browser mistakes cannot
# silently create absurd balances.
SOLARI_BANK_GRANT_MAX = int(os.environ.get("SOLARI_BANK_GRANT_MAX", "1000000000"))

# Player specialization XP tracks observed in IceHunter's MIT-licensed
# dune-admin project and backed by dune.specializationtracktype. The XP helper
# below uses these exact values and refuses arbitrary browser-supplied tracks.
SPECIALIZATION_XP_TRACKS = [
    "Combat",
    "Crafting",
    "Gathering",
    "Exploration",
    "Sabotage",
]

# IceHunter's implementation caps specialization XP at this value. Keep this
# configurable here so server owners can adjust if Funcom changes progression.
SPECIALIZATION_MAX_XP = 44182

# Character XP controls the displayed character level. This is separate from
# specialization-track XP and is stored on the character's DuneCharacter FGL
# entity. IceHunter's MIT-licensed dune-admin research identifies 344,440 as
# the XP required for level 200, the current hard cap.
CHARACTER_MAX_XP = 344440
CHARACTER_LEVEL_XP = {
    0: 0, 1: 40, 2: 215, 3: 440, 4: 740, 5: 1240, 6: 1790, 7: 2390, 8: 2990, 9: 3590, 10: 4190,
    11: 4790, 12: 5390, 13: 5990, 14: 6590, 15: 7190, 16: 7790, 17: 8390, 18: 8990, 19: 9590, 20: 10190,
    21: 10790, 22: 11390, 23: 11990, 24: 12590, 25: 13190, 26: 13790, 27: 14390, 28: 14990, 29: 15590, 30: 16190,
    31: 16790, 32: 17390, 33: 17990, 34: 18590, 35: 19190, 36: 19790, 37: 20390, 38: 20990, 39: 21590, 40: 22190,
    41: 22790, 42: 23390, 43: 23990, 44: 24590, 45: 25190, 46: 25790, 47: 26390, 48: 26990, 49: 27590, 50: 28190,
    51: 28790, 52: 29390, 53: 29990, 54: 30590, 55: 31190, 56: 31790, 57: 32390, 58: 32990, 59: 33590, 60: 34190,
    61: 34790, 62: 35390, 63: 35990, 64: 36590, 65: 37190, 66: 37790, 67: 38390, 68: 38990, 69: 39590, 70: 40190,
    71: 40790, 72: 41390, 73: 41990, 74: 42590, 75: 43190, 76: 43790, 77: 44390, 78: 44990, 79: 45590, 80: 46190,
    81: 46790, 82: 47390, 83: 47990, 84: 48590, 85: 49190, 86: 49790, 87: 50390, 88: 50990, 89: 51590, 90: 52190,
    91: 52790, 92: 53390, 93: 53990, 94: 54590, 95: 55190, 96: 55790, 97: 56390, 98: 56990, 99: 57590, 100: 58190,
    101: 58840, 102: 59490, 103: 60140, 104: 60790, 105: 61440, 106: 62090, 107: 62740, 108: 63390, 109: 64040, 110: 64690,
    111: 65340, 112: 65990, 113: 66640, 114: 67290, 115: 67940, 116: 68590, 117: 69240, 118: 69890, 119: 70540, 120: 71190,
    121: 71840, 122: 72490, 123: 73140, 124: 73790, 125: 74440, 126: 75090, 127: 75740, 128: 76391, 129: 77044, 130: 77699,
    131: 78357, 132: 79018, 133: 79683, 134: 80353, 135: 81030, 136: 81714, 137: 82407, 138: 83110, 139: 83825, 140: 84554,
    141: 85298, 142: 86060, 143: 86842, 144: 87646, 145: 88475, 146: 89332, 147: 90220, 148: 91141, 149: 92100, 150: 93099,
    151: 94143, 152: 95235, 153: 96380, 154: 97582, 155: 98845, 156: 100175, 157: 101576, 158: 103054, 159: 104614, 160: 106263,
    161: 108006, 162: 109849, 163: 111799, 164: 113862, 165: 116046, 166: 118358, 167: 120806, 168: 123397, 169: 126139, 170: 129041,
    171: 132112, 172: 135360, 173: 138795, 174: 142426, 175: 146263, 176: 150316, 177: 154596, 178: 159114, 179: 163880, 180: 168906,
    181: 174203, 182: 179784, 183: 185661, 184: 191846, 185: 198353, 186: 205195, 187: 212385, 188: 219938, 189: 227868, 190: 236190,
    191: 244918, 192: 254069, 193: 263657, 194: 273700, 195: 284213, 196: 295214, 197: 306719, 198: 318746, 199: 331314, 200: 344440,
}

# Curated journey-node presets adapted from IceHunter's MIT-licensed
# dune-admin progression preset catalog. These intentionally operate only on
# journey story nodes; they are for testing and small private-server recovery,
# not a guarantee that every in-game side effect/tag has been reproduced.
PROGRESSION_PRESETS = [
    {
        "id": "skip_npe",
        "name": "Skip NPE / Tutorial",
        "description": "Marks the tutorial/new-player experience root as complete.",
        "nodes": ["DA_MQ_NPEAutocompleted"],
    },
    {
        "id": "a_new_beginning",
        "name": "Complete: A New Beginning",
        "description": "Completes the early main-story root around crafting, harvesting, and fabricator research.",
        "nodes": ["DA_MQ_ANewBeginning"],
    },
    {
        "id": "find_the_fremen",
        "name": "Complete: Find the Fremen",
        "description": "Completes the Trials of Aql / Fremen discovery root.",
        "nodes": ["DA_MQ_FindTheFremen"],
    },
    {
        "id": "act1_complete",
        "name": "Complete: Act 1",
        "description": "Applies A New Beginning plus Find the Fremen.",
        "nodes": ["DA_MQ_ANewBeginning", "DA_MQ_FindTheFremen"],
    },
    {
        "id": "vermillius_intro",
        "name": "Skip: Vermillius Gap Tutorials",
        "description": "Completes the Vermillius Gap tutorial roots.",
        "nodes": ["DA_SQ_VermiliusGap", "DA_Dunipedia_Landmarks.VermiliusGap"],
    },
    {
        "id": "deep_desert_intro",
        "name": "Skip: Deep Desert Intro",
        "description": "Completes the Deep Desert intro side-quest root.",
        "nodes": ["DA_SQ_DeepDesert"],
    },
    {
        "id": "taxation_intro",
        "name": "Skip: Taxation / Exchange Tutorial",
        "description": "Completes the exchange/travel tutorial root.",
        "nodes": ["DA_SQ_Taxation"],
    },
    {
        "id": "overland_intro",
        "name": "Skip: Overland Map Intro",
        "description": "Completes the overland map side-quest root.",
        "nodes": ["DA_SQ_OverlandMap"],
    },
    {
        "id": "unlock_all_lore",
        "name": "Unlock All Lore / Dunipedia",
        "description": "Reveals the broad Dunipedia lore roots.",
        "nodes": [
            "DA_Dunipedia_KnownUniverse",
            "DA_Dunipedia_Landmarks",
            "DA_Dunipedia_ManualOfTheFriendlyDesert",
            "DA_Dunipedia_WarForArrakis",
        ],
    },
]

DEFAULT_OVERREPAIR_DURABILITY = "1000"

# Default value for experimental vehicle module durability repair.
# This writes to dune.vehicle_modules stats JSON. Keep this sane until
# more exact per-module max durability values are confirmed.
DEFAULT_VEHICLE_REPAIR_DURABILITY = "3500"

# Live map / teleport instance configuration.
# Put your downloaded Hagga Basin / Arrakis image here:
#
#   ~/dune-admin-web/static/arrakis_hb.webp
#
# These bounds come from the working Dune dashboard calibration.
# The map image is expected to be 8000x8000 for cleanest alignment.
#
# Each entry is a visible map instance in Easy Dune Admin. The "key" is the UI
# value, while "actor_map" is the value written in dune.actors.map. Multiple
# visible instances can share the same actor_map and image but use different
# default_partition_id values once your server has multiple sietches/deserts.
#
# Partition IDs are server/runtime specific. Do not assume another user's
# Survival/Deep Desert partitions match yours; verify them before publishing a
# preset or telling an admin to teleport into a second instance.
DEFAULT_MAP_CONFIGS = {
    "HaggaBasin": {
        "key": "HaggaBasin",
        "label": "Arrakis - Hagga Basin",
        "actor_map": "HaggaBasin",
        "image": "arrakis_hb.webp",
        "width": 8000,
        "height": 8000,
        "min_x": -456752.21,
        "max_x": 354547.46,
        "min_y": -450630.14,
        "max_y": 353821.95,
        "flip_y": False,
        # Server-specific default. Confirm before using on another install.
        "default_partition_id": 1,
    },
    "DeepDesert": {
        "key": "DeepDesert",
        "label": "The Deep Desert",
        "actor_map": "DeepDesert",
        "image": "deep_desert.webp",
        "width": 8000,
        "height": 8000,
        "min_x": -1268624.82,
        "max_x": 1163312.83,
        "min_y": -1266548.17,
        "max_y": 1162416.13,
        "flip_y": False,
        # Server-specific default. Confirm before using on another install.
        "default_partition_id": "8",
    },
}

MAP_CONFIG_REQUIRED_FIELDS = {
    "image",
    "width",
    "height",
    "min_x",
    "max_x",
    "min_y",
    "max_y",
}


def load_map_configs():
    """
    Load map/teleport instances.

    Advanced admins running multiple Survival or Deep Desert instances can set
    EASY_DUNE_MAP_CONFIGS_JSON to a JSON object keyed by UI map key. Start by
    copying DEFAULT_MAP_CONFIGS, then add entries like "HaggaBasinPvP" or
    "DeepDesertPvE" with the same image/bounds and the verified partition id.

    Example shape:
    {
      "HaggaBasin": {"label": "Hagga 1", "actor_map": "HaggaBasin", ...},
      "HaggaBasin2": {"label": "Hagga 2", "actor_map": "HaggaBasin", "default_partition_id": 12, ...}
    }
    """
    raw = os.environ.get("EASY_DUNE_MAP_CONFIGS_JSON", "").strip()
    if not raw:
        return DEFAULT_MAP_CONFIGS

    try:
        loaded = json.loads(raw)
    except Exception:
        return DEFAULT_MAP_CONFIGS

    if not isinstance(loaded, dict):
        return DEFAULT_MAP_CONFIGS

    configs = {}
    for key, cfg in loaded.items():
        if not isinstance(cfg, dict):
            continue

        merged = dict(DEFAULT_MAP_CONFIGS.get(cfg.get("base_key", key), {}))
        merged.update(cfg)
        merged["key"] = key
        merged.setdefault("label", key)
        merged.setdefault("actor_map", merged.get("key", key))
        merged.setdefault("default_partition_id", "")
        merged.setdefault("flip_y", False)

        if MAP_CONFIG_REQUIRED_FIELDS.issubset(merged.keys()):
            configs[key] = merged

    return configs or DEFAULT_MAP_CONFIGS


MAP_CONFIGS = load_map_configs()
DEFAULT_MAP_KEY = "HaggaBasin" if "HaggaBasin" in MAP_CONFIGS else next(iter(MAP_CONFIGS))

# Backward-compatible lookup for older helper code. New code reads the selected
# instance's default_partition_id from MAP_CONFIGS so multi-instance servers can
# use different Survival/Deep Desert partitions.
ORNITHOPTER_PARTITION_DEFAULTS = {
    key: cfg.get("default_partition_id", "")
    for key, cfg in MAP_CONFIGS.items()
}

# Vehicle actor class patterns confirmed from exported dune.actors rows.
# Add newly discovered vehicle blueprint name fragments here before exposing
# them in the admin-only teleport UI. The SQL allow-list deliberately stays
# explicit so unrelated actors with transforms do not appear as movable vehicles.
TELEPORTABLE_VEHICLE_CLASS_PATTERNS = [
    "Ornithopter",
    "Sandbike",
    "Buggy",
    "Tank",
    "TreadWheel",
    "SandCrawler",
    "ContainerVehicle",
]

# Emergency unstuck target.
# This should be a known-safe location in Hagga Basin. It is used by
# the emergency return button and bypasses click-selected coordinates.
SAFE_HAGGA_BASIN_RETURN = {
    "partition_id": 1,
    "x": 23404.83682414103,
    "y": 227266.60099261496,
    "z": 8552.14991713151,
}


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)
app.secret_key = SECRET_KEY

# SocketIO powers the optional browser terminal. async_mode="threading"
# keeps setup simple and avoids forcing eventlet/gevent behavior.
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# Active host shell sessions keyed by SocketIO session id.
SHELL_SESSIONS = {}

# In-process buyback sweep state. This deliberately lives in the webadmin
# daemon rather than cron so admins can start/stop it from the browser. It is
# reset when the webadmin process restarts.
MARKET_BUYBACK_STATE_LOCK = threading.Lock()
MARKET_BUYBACK_RUN_LOCK = threading.Lock()
MARKET_BUYBACK_STOP_EVENT = threading.Event()
MARKET_BUYBACK_THREAD = None
MARKET_BUYBACK_STATE = {
    "enabled": False,
    "price_multiplier": MARKET_PRICE_MULTIPLIER,
    "threshold_percent": MARKET_BUY_THRESHOLD_PERCENT,
    "max_buys": MARKET_BUY_MAX_PER_CLICK,
    "interval_minutes": MARKET_BUYBACK_INTERVAL_MINUTES,
    "last_run": "",
    "last_output": "",
    "last_error": "",
    "next_run": "",
    "runs": 0,
}

MARKET_RESEED_STATE_LOCK = threading.Lock()
MARKET_RESEED_STOP_EVENT = threading.Event()
MARKET_RESEED_THREAD = None
MARKET_RESEED_STATE = {
    "enabled": False,
    "price_multiplier": MARKET_PRICE_MULTIPLIER,
    "exchange_id": MARKET_SEED_EXCHANGE_ID,
    "interval_minutes": MARKET_RESEED_INTERVAL_MINUTES,
    "last_run": "",
    "last_output": "",
    "last_error": "",
    "next_run": "",
    "runs": 0,
}


@app.context_processor
def inject_template_globals():
    return {
        "panel_version": PANEL_VERSION,
        "redblink_stack_version": REDBLINK_STACK_VERSION,
        "maps": MAPS,
        "restart_targets": RESTART_TARGETS,
        "scout_thopter_template": SCOUT_THOPTER_TEMPLATE,
        "medium_bundle": MEDIUM_THOPTER_BUNDLE,
        "lasgun_augment_bundle": LASGUN_AUGMENT_BUNDLE,
        "new_player_starter_kit": NEW_PLAYER_STARTER_KIT,
        "solaris_grant_amounts": SOLARIS_GRANT_AMOUNTS,
        "specialization_xp_tracks": SPECIALIZATION_XP_TRACKS,
        "specialization_max_xp": SPECIALIZATION_MAX_XP,
        "character_max_xp": CHARACTER_MAX_XP,
        "character_max_level": max(CHARACTER_LEVEL_XP),
        "progression_presets": PROGRESSION_PRESETS,
        "default_overrepair_durability": DEFAULT_OVERREPAIR_DURABILITY,
        "default_vehicle_repair_durability": DEFAULT_VEHICLE_REPAIR_DURABILITY,
        "enable_host_command_runner": ENABLE_HOST_COMMAND_RUNNER,
        "enable_host_shell": ENABLE_HOST_SHELL,
        "enable_stack_installer": ENABLE_STACK_INSTALLER,
        "redblink_repo_url": REDBLINK_REPO_URL,
        "redblink_install_dir": str(REDBLINK_INSTALL_DIR),
        "map_configs": MAP_CONFIGS,
        "default_map_key": DEFAULT_MAP_KEY,
        "market_bot_class": MARKET_BOT_CLASS,
        "market_price_multiplier": MARKET_PRICE_MULTIPLIER,
        "market_seed_exchange_id": MARKET_SEED_EXCHANGE_ID,
        "market_resource_stack_size": MARKET_RESOURCE_STACK_SIZE,
        "market_buy_threshold_percent": MARKET_BUY_THRESHOLD_PERCENT,
        "market_buy_max_per_click": MARKET_BUY_MAX_PER_CLICK,
        "market_buyback_interval_minutes": MARKET_BUYBACK_INTERVAL_MINUTES,
        "market_reseed_interval_minutes": MARKET_RESEED_INTERVAL_MINUTES,
        "solari_bank_grant_max": SOLARI_BANK_GRANT_MAX,
        "redblink_vehicle_spawn_templates": REDBLINK_VEHICLE_SPAWN_TEMPLATES,
        "redblink_skill_modules": load_redblink_skill_modules(),
        "default_water_refill_amount": DEFAULT_WATER_REFILL_AMOUNT,
        "installation_modes": INSTALLATION_MODES,
        "default_installation_mode": DEFAULT_INSTALLATION_MODE,
        "current_installation_mode": current_installation_mode(),
        "current_installation_mode_label": current_installation_mode_label(),
        "installation_capabilities": current_installation_capabilities(),
    }


def load_redblink_skill_modules():
    """
    Load RedBlink's MIT-licensed admin skill-module catalog for browser dropdowns.

    The route still validates the selected module id against this same catalog
    before calling `dune admin skill-module`, so a browser cannot submit an
    arbitrary module string when the catalog is present.
    """
    try:
        if not SKILL_MODULES_FILE.exists():
            return []
        rows = json.loads(SKILL_MODULES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    modules = []
    for row in rows if isinstance(rows, list) else []:
        module_id = str(row.get("id", "")).strip()
        if not module_id:
            continue
        try:
            max_level = int(row.get("maxLevel", 1))
        except (TypeError, ValueError):
            max_level = 1
        modules.append(
            {
                "id": module_id,
                "name": str(row.get("name", module_id)).strip() or module_id,
                "category": str(row.get("category", "Uncategorized")).strip() or "Uncategorized",
                "maxLevel": max(0, max_level),
            }
        )

    return sorted(modules, key=lambda item: (item["category"].casefold(), item["name"].casefold(), item["id"].casefold()))


# =========================================================
# DATABASE HELPERS
# =========================================================

def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            character_name TEXT DEFAULT ''
        )
        """
    )
    columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "character_name" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN character_name TEXT DEFAULT ''")
    conn.commit()
    conn.close()


def user_count():
    conn = db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count


def list_users():
    conn = db()
    rows = conn.execute(
        """
        SELECT id, username, role, COALESCE(character_name, '') AS character_name
        FROM users
        ORDER BY username
        """
    ).fetchall()
    conn.close()
    return rows


def footer_online_users():
    """
    Return online game characters matched to local web accounts when possible.

    The web panel does not keep a persistent browser-presence table, so the
    footer uses in-game online characters and colors them by the linked web role
    when an admin has entered the exact character name on the user account.
    """
    users = [
        {
            "username": row["username"],
            "role": row["role"],
            "character_name": (row["character_name"] or "").casefold(),
        }
        for row in list_users()
    ]
    by_character = {
        user["character_name"]: user
        for user in users
        if user["character_name"]
    }

    footer_rows = []
    for character in get_characters(include_offline=False):
        character_name = character.get("character_name", "")
        linked = by_character.get(character_name.casefold())
        footer_rows.append(
            {
                "username": linked["username"] if linked else "",
                "role": linked["role"] if linked else "unlinked",
                "character_name": character_name,
                "online_status": character.get("online_status", ""),
            }
        )

    footer_rows.sort(key=lambda row: (row["role"] == "unlinked", row["username"] or row["character_name"]))
    return footer_rows


init_db()


# =========================================================
# AUTH HELPERS
# =========================================================

def logged_in():
    return "user" in session


def current_role():
    return session.get("role", "")


def is_admin():
    return current_role() == "admin"


def is_operator_or_admin():
    return current_role() in ("operator", "admin")


def is_vip():
    return current_role() == "vip"


def can_use_vip_tools():
    return current_role() in ("vip", "admin")


def require_login():
    if not logged_in():
        return redirect("/login")
    return None


def current_installation_mode():
    """
    Return the active command profile for this browser session.

    The value is selected at login so one deployed copy can target local Linux,
    the Dockerized webadmin layout, or a Hyper-V Linux VM through SSH.
    """
    if has_request_context():
        selected = session.get("installation_mode", DEFAULT_INSTALLATION_MODE)
        if selected in INSTALLATION_MODES:
            return selected
    return DEFAULT_INSTALLATION_MODE


def current_installation_mode_label():
    return INSTALLATION_MODES[current_installation_mode()]["label"]


def current_installation_capabilities():
    """
    Describe which UX blocks are meaningful for the selected install profile.

    Keep these booleans conservative. Command buttons that use RedBlink's dune
    wrapper can run locally or through Hyper-V SSH, but installer and shell
    panels are tied to where the Flask process actually lives.
    """
    mode = current_installation_mode()
    return {
        "is_linux": mode == "linux",
        "is_docker": mode == "docker",
        "is_hyperv": mode == "hyperv",
        "redblink_commands": True,
        "stack_installer": mode == "linux",
        "browser_shell": mode in ("linux", "docker"),
        "host_diagnostics": mode == "linux",
        "container_diagnostics": mode == "docker",
        "interactive_vm_shell": mode == "linux",
    }


# =========================================================
# LOGGING
# =========================================================

def log_action(user, action):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ACTION_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {user}: {action}\n")


def recent_log_lines(limit=250):
    if not ACTION_LOG.exists():
        return []
    return ACTION_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]


# =========================================================
# COMMAND / DATA HELPERS
# =========================================================

def _command_for_current_installation(cmd):
    """
    Convert a local command list into the command that should actually run.

    Linux/Docker modes execute locally. Hyper-V mode wraps the command in SSH
    and maps the local RedBlink script path to EASY_DUNE_HYPERV_DUNE_ROOT so
    the same route code can be reused without hardcoding VM paths everywhere.
    """
    mode = current_installation_mode()
    if mode != "hyperv":
        return cmd, str(DUNE_ROOT)

    if not HYPERV_SSH_TARGET:
        raise RuntimeError(
            "Hyper-V mode is selected, but EASY_DUNE_HYPERV_SSH_TARGET is not configured."
        )

    mapped_cmd = [str(part) for part in cmd]
    local_script = str(DUNE_SCRIPT)
    remote_script = f"{HYPERV_DUNE_ROOT.rstrip('/')}/runtime/scripts/dune"
    mapped_cmd = [
        remote_script if part == local_script else part
        for part in mapped_cmd
    ]
    remote_command = f"cd {shlex.quote(HYPERV_DUNE_ROOT)} && {shlex.join(mapped_cmd)}"
    return ["ssh", HYPERV_SSH_TARGET, remote_command], None


def run_process(cmd, timeout=60, input_text=None):
    """Run a controlled command list through the selected installation profile."""
    actual_cmd, cwd = _command_for_current_installation(cmd)
    return subprocess.run(
        actual_cmd,
        cwd=cwd,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def run_command(cmd, timeout=60, input_text=None):
    """Run controlled command list. Never change this to shell=True."""
    try:
        proc = run_process(cmd, timeout=timeout, input_text=input_text)
    except Exception as exc:
        return "$ " + " ".join(cmd) + f"\n\nERROR:\n{exc}"

    return (
        "$ " + " ".join(cmd)
        + "\n\nSTDOUT:\n" + proc.stdout
        + "\nSTDERR:\n" + proc.stderr
        + f"\nExit code: {proc.returncode}"
    )


def split_redblink_table_row(line):
    """
    Split RedBlink's fixed-width command tables while preserving labels such as
    "Hagga Basin" that contain single spaces. RedBlink tables separate columns
    with two or more spaces.
    """
    columns = re.split(r"\s{2,}", line.strip())
    if columns and columns[0].isdigit():
        columns = columns[1:]
    return columns


def parse_redblink_sietch_list(output):
    """
    Parse `dune sietches list` into a map-name keyed lookup.

    RedBlink v1.3.3 columns:
    MAP, MAX DIMENSIONS, ACTIVE DIMENSIONS, MEMORY, TYPE
    """
    rows = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("MAP "):
            continue
        columns = split_redblink_table_row(line)
        if len(columns) < 5:
            continue
        map_name, max_dimensions, active_dimensions, memory, map_type = columns[:5]
        rows[map_name] = {
            "max_dimensions": max_dimensions,
            "active_dimensions": active_dimensions,
            "sietch_memory": memory,
            "sietch_type": map_type,
        }
    return rows


def parse_redblink_memory_maps(memory_output, sietch_output=""):
    """
    Build dropdown-ready map rows from `dune memory list-maps`, enriched with
    active/max dimensions from `dune sietches list` when available.
    """
    sietches = parse_redblink_sietch_list(sietch_output)
    grouped = {}

    for raw_line in memory_output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("MAP "):
            continue
        columns = split_redblink_table_row(line)
        if len(columns) < 5:
            continue

        map_name, partition, label, map_type, memory = columns[:5]
        row = grouped.setdefault(
            map_name,
            {
                "map_name": map_name,
                "partitions": [],
                "labels": [],
                "types": [],
                "memory": memory,
                "active_dimensions": "",
                "max_dimensions": "",
            },
        )
        if partition and partition not in row["partitions"]:
            row["partitions"].append(partition)
        if label and label not in row["labels"]:
            row["labels"].append(label)
        if map_type and map_type not in row["types"]:
            row["types"].append(map_type)
        if memory and row["memory"] in ("", "default"):
            row["memory"] = memory

    for map_name, details in sietches.items():
        row = grouped.setdefault(
            map_name,
            {
                "map_name": map_name,
                "partitions": [],
                "labels": [],
                "types": [],
                "memory": details.get("sietch_memory", ""),
                "active_dimensions": "",
                "max_dimensions": "",
            },
        )
        row["active_dimensions"] = details.get("active_dimensions", "")
        row["max_dimensions"] = details.get("max_dimensions", "")
        sietch_type = details.get("sietch_type", "")
        if sietch_type and sietch_type not in row["types"]:
            row["types"].append(sietch_type)
        if details.get("sietch_memory") and row["memory"] in ("", "default"):
            row["memory"] = details["sietch_memory"]

    rows = []
    for row in grouped.values():
        dimension_text = ""
        if row.get("active_dimensions") or row.get("max_dimensions"):
            dimension_text = f"{row.get('active_dimensions') or '?'} active / {row.get('max_dimensions') or '?'} max"
        elif row["partitions"]:
            dimension_text = f"partition(s): {', '.join(row['partitions'])}"

        label_parts = [row["map_name"]]
        if row["labels"]:
            label_parts.append("labels: " + ", ".join(row["labels"]))
        if dimension_text:
            label_parts.append(dimension_text)
        if row["types"]:
            label_parts.append("type: " + ", ".join(row["types"]))
        if row["memory"]:
            label_parts.append("memory: " + row["memory"])

        rows.append(
            {
                "map_name": row["map_name"],
                "label": " | ".join(label_parts),
                "partitions": row["partitions"],
                "labels": row["labels"],
                "types": row["types"],
                "memory": row["memory"],
                "active_dimensions": row.get("active_dimensions", ""),
                "max_dimensions": row.get("max_dimensions", ""),
            }
        )

    return sorted(rows, key=lambda item: item["map_name"].casefold())


def run_psql(sql, timeout=60):
    cmd = [
        "docker",
        "exec",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        "dune",
        "-d",
        "dune",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    return run_command(cmd, timeout=timeout)


def run_psql_script(sql, timeout=180):
    """Run a multi-statement SQL script through psql stdin."""
    cmd = [
        "docker",
        "exec",
        "-i",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        "dune",
        "-d",
        "dune",
        "-v",
        "ON_ERROR_STOP=1",
    ]
    return run_command(cmd, timeout=timeout, input_text=sql)


def load_items():
    if not ITEMS_FILE.exists():
        return []
    with open(ITEMS_FILE, encoding="utf-8") as f:
        return json.load(f)


def search_items(query, limit=100):
    items = load_items()
    needle = query.casefold().strip()

    if not needle:
        return []

    results = []

    for item in items:
        fields = [
            str(item.get("id", "")),
            str(item.get("name", "")),
            str(item.get("category", "")),
            str(item.get("source", "")),
        ]

        if any(needle in field.casefold() for field in fields):
            results.append(item)

    return results[:limit]


def market_price_multiplier_from_value(value):
    """
    Validate an admin-entered per-run market price multiplier.

    The environment default stays useful for unattended installs, while this
    helper lets admins tune one seed run from the browser without editing files.
    """
    raw_value = str(value if value not in (None, "") else MARKET_PRICE_MULTIPLIER).strip()
    try:
        multiplier = int(raw_value)
    except ValueError as exc:
        raise ValueError("price multiplier must be a whole number") from exc

    if multiplier < 1:
        raise ValueError("price multiplier must be at least 1")
    if multiplier > 10000:
        raise ValueError("price multiplier must be 10000 or lower")
    return multiplier


def market_buy_threshold_from_value(value):
    raw_value = str(value if value not in (None, "") else MARKET_BUY_THRESHOLD_PERCENT).strip()
    try:
        threshold = int(raw_value)
    except ValueError as exc:
        raise ValueError("buy threshold must be a whole percent") from exc

    if threshold < 1:
        raise ValueError("buy threshold must be at least 1%")
    if threshold > 100:
        raise ValueError("buy threshold must be 100% or lower")
    return threshold


def market_buy_max_from_value(value):
    raw_value = str(value if value not in (None, "") else MARKET_BUY_MAX_PER_CLICK).strip()
    try:
        max_buys = int(raw_value)
    except ValueError as exc:
        raise ValueError("max buys must be a whole number") from exc

    if max_buys < 1:
        raise ValueError("max buys must be at least 1")
    if max_buys > 5000:
        raise ValueError("max buys must be 5000 or lower")
    return max_buys


def market_buyback_interval_from_value(value):
    return market_interval_from_value(value, MARKET_BUYBACK_INTERVAL_MINUTES, "buyback")


def market_reseed_interval_from_value(value):
    return market_interval_from_value(value, MARKET_RESEED_INTERVAL_MINUTES, "reseed")


def market_interval_from_value(value, default_interval, label):
    raw_value = str(value if value not in (None, "") else default_interval).strip()
    try:
        interval = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{label} interval must be whole minutes") from exc

    if interval < 1:
        raise ValueError(f"{label} interval must be at least 1 minute")
    if interval > 1440:
        raise ValueError(f"{label} interval must be 1440 minutes or lower")
    return interval


def market_exchange_id_from_value(value):
    raw_value = str(value if value is not None else MARKET_SEED_EXCHANGE_ID).strip()
    if not raw_value:
        return None
    try:
        exchange_id = int(raw_value)
    except ValueError as exc:
        raise ValueError("exchange id must be blank or a whole number") from exc

    if exchange_id < 1:
        raise ValueError("exchange id must be at least 1")
    return exchange_id


def solari_bank_amount_from_value(value):
    """Validate direct stored SolarisCoin item-stack edits."""
    raw_value = str(value or "").replace(",", "").strip()
    try:
        amount = int(raw_value)
    except ValueError as exc:
        raise ValueError("stored Solari amount must be a whole number") from exc

    if amount <= 0:
        raise ValueError("stored Solari amount must be greater than zero")
    if amount > SOLARI_BANK_GRANT_MAX:
        raise ValueError(f"stored Solari amount must be {SOLARI_BANK_GRANT_MAX} or lower")
    return amount


def solari_bank_balance_from_value(value):
    """Validate exact stored SolarisCoin item-stack corrections."""
    raw_value = str(value or "").replace(",", "").strip()
    try:
        amount = int(raw_value)
    except ValueError as exc:
        raise ValueError("stored Solari balance must be a whole number") from exc

    if amount < 0:
        raise ValueError("stored Solari balance cannot be negative")
    if amount > SOLARI_BANK_GRANT_MAX:
        raise ValueError(f"stored Solari balance must be {SOLARI_BANK_GRANT_MAX} or lower")
    return amount


def get_solari_bank_balance(character_actor_id):
    """
    Return SolarisCoin stacks for one character actor.

    Stored player Solari is represented by SolarisCoin item rows in character
    inventories on observed self-hosted servers. This intentionally sums every
    SolarisCoin stack owned by the selected pawn actor instead of using Dune's
    exchange-user balance helper, which tracks market-bot/exchange state and
    can report 0 for normal player money.
    """
    actor_id = int(character_actor_id)
    sql = f"""
    WITH selected_player AS (
        SELECT
            ps.character_name,
            ps.player_pawn_id AS character_actor_id
        FROM dune.player_state ps
        WHERE ps.player_pawn_id = {actor_id}
        LIMIT 1
    ),
    solari_rows AS (
        SELECT
            i.id AS item_id,
            i.inventory_id,
            COALESCE(i.stack_size, 0)::bigint AS stack_size
        FROM selected_player sp
        JOIN dune.inventories inv
            ON inv.actor_id = sp.character_actor_id
        JOIN dune.items i
            ON i.inventory_id = inv.id
        WHERE i.template_id = '{SOLARIS_COIN_ITEM_ID}'
    )
    SELECT
        sp.character_name,
        sp.character_actor_id::text,
        COALESCE(SUM(sr.stack_size), 0)::text AS solari_balance,
        COUNT(sr.item_id)::text AS stack_count,
        COALESCE(string_agg(sr.inventory_id::text || ':' || sr.item_id::text || ':' || sr.stack_size::text, ', ' ORDER BY sr.inventory_id, sr.item_id), '') AS stacks
    FROM selected_player sp
    LEFT JOIN solari_rows sr
        ON true
    GROUP BY sp.character_name, sp.character_actor_id;
    """

    rows = _run_psql_tsv(sql, timeout=15)
    if not rows:
        raise ValueError("character actor not found")

    parts = rows[0].split("\t")
    if len(parts) < 3:
        raise ValueError("unexpected Solari balance query result")

    return {
        "character_name": parts[0],
        "character_actor_id": parts[1],
        "solari_balance": parts[2],
        "stack_count": parts[3] if len(parts) > 3 else "0",
        "stacks": parts[4] if len(parts) > 4 else "",
    }


def get_exchange_bank_solari_balance(character_actor_id):
    """
    Return the player-visible exchange bank Solari balance.

    Observed schema:
      dune.player_virtual_currency_balances.player_controller_id bigint
      dune.player_virtual_currency_balances.currency_id smallint
      dune.player_virtual_currency_balances.balance bigint

    currency_id 0 is the Solari exchange-bank balance supplied by the project
    owner's live lookup. This is intentionally separate from SolarisCoin item
    stacks in dune.items.
    """
    actor_id = int(character_actor_id)
    sql = f"""
    SELECT
        ps.character_name,
        ps.player_pawn_id::text AS character_actor_id,
        ps.player_controller_id::text,
        COALESCE(pvc.balance, 0)::text AS exchange_bank_solari,
        CASE WHEN pvc.player_controller_id IS NULL THEN 'missing' ELSE 'present' END AS balance_row
    FROM dune.player_state ps
    LEFT JOIN dune.player_virtual_currency_balances pvc
        ON pvc.player_controller_id = ps.player_controller_id
       AND pvc.currency_id = 0
    WHERE ps.player_pawn_id = {actor_id}
    LIMIT 1;
    """

    rows = _run_psql_tsv(sql, timeout=15)
    if not rows:
        raise ValueError("character actor not found")

    parts = rows[0].split("\t")
    if len(parts) < 5:
        raise ValueError("unexpected exchange bank Solari query result")

    return {
        "character_name": parts[0],
        "character_actor_id": parts[1],
        "player_controller_id": parts[2],
        "exchange_bank_solari": parts[3],
        "balance_row": parts[4],
    }


def get_exchange_bank_solari_balance_by_controller(player_controller_id):
    """Return exchange bank Solari using the table's direct controller key."""
    controller_id = int(player_controller_id)
    sql = f"""
    SELECT
        COALESCE(ps.character_name, 'Unknown') AS character_name,
        COALESCE(ps.player_pawn_id::text, '') AS character_actor_id,
        {controller_id}::text AS player_controller_id,
        COALESCE(pvc.balance, 0)::text AS exchange_bank_solari,
        CASE WHEN pvc.player_controller_id IS NULL THEN 'missing' ELSE 'present' END AS balance_row
    FROM (SELECT {controller_id}::bigint AS player_controller_id) target
    LEFT JOIN dune.player_state ps
        ON ps.player_controller_id = target.player_controller_id
    LEFT JOIN dune.player_virtual_currency_balances pvc
        ON pvc.player_controller_id = target.player_controller_id
       AND pvc.currency_id = 0
    LIMIT 1;
    """

    rows = _run_psql_tsv(sql, timeout=15)
    if not rows:
        raise ValueError("player controller not found")

    parts = rows[0].split("\t")
    if len(parts) < 5:
        raise ValueError("unexpected exchange bank Solari query result")

    return {
        "character_name": parts[0],
        "character_actor_id": parts[1],
        "player_controller_id": parts[2],
        "exchange_bank_solari": parts[3],
        "balance_row": parts[4],
    }


def build_add_exchange_bank_solari_by_controller_sql(player_controller_id, amount):
    """Build SQL to add exchange bank Solari by direct player_controller_id."""
    controller_id = int(player_controller_id)
    delta = solari_bank_amount_from_value(amount)

    return f"""
WITH settings AS (
    SELECT
        {controller_id}::bigint AS player_controller_id,
        {delta}::bigint AS solari_delta
),
before_balance AS (
    SELECT
        s.player_controller_id,
        COALESCE(ps.character_name, 'Unknown') AS character_name,
        COALESCE(ps.player_pawn_id, 0)::bigint AS character_actor_id,
        COALESCE(ps.online_status::text, '') AS online_status,
        COALESCE(ps.life_state::text, '') AS life_state,
        COALESCE(pvc.balance, 0)::bigint AS before_solari
    FROM settings s
    LEFT JOIN dune.player_state ps
        ON ps.player_controller_id = s.player_controller_id
    LEFT JOIN dune.player_virtual_currency_balances pvc
        ON pvc.player_controller_id = s.player_controller_id
       AND pvc.currency_id = 0
),
updated AS (
    UPDATE dune.player_virtual_currency_balances pvc
    SET balance = pvc.balance + (SELECT solari_delta FROM settings)
    FROM before_balance bb
    WHERE pvc.player_controller_id = bb.player_controller_id
      AND pvc.currency_id = 0
    RETURNING pvc.player_controller_id, pvc.currency_id, pvc.balance
),
inserted AS (
    INSERT INTO dune.player_virtual_currency_balances (player_controller_id, currency_id, balance)
    SELECT
        bb.player_controller_id,
        0::smallint,
        s.solari_delta
    FROM before_balance bb
    JOIN settings s
        ON s.player_controller_id = bb.player_controller_id
    WHERE NOT EXISTS (SELECT 1 FROM updated)
    RETURNING player_controller_id, currency_id, balance
),
applied AS (
    SELECT * FROM updated
    UNION ALL
    SELECT * FROM inserted
)
SELECT
    bb.character_name,
    bb.character_actor_id,
    bb.player_controller_id,
    bb.online_status,
    bb.life_state,
    bb.before_solari,
    s.solari_delta AS added_solari,
    a.balance AS after_solari
FROM before_balance bb
JOIN settings s
    ON s.player_controller_id = bb.player_controller_id
JOIN applied a
    ON a.player_controller_id = bb.player_controller_id
   AND a.currency_id = 0;
"""


def build_set_exchange_bank_solari_by_controller_sql(player_controller_id, target_balance):
    """Build SQL to set exchange bank Solari by direct player_controller_id."""
    controller_id = int(player_controller_id)
    target = solari_bank_balance_from_value(target_balance)

    return f"""
WITH settings AS (
    SELECT
        {controller_id}::bigint AS player_controller_id,
        {target}::bigint AS target_solari
),
before_balance AS (
    SELECT
        s.player_controller_id,
        COALESCE(ps.character_name, 'Unknown') AS character_name,
        COALESCE(ps.player_pawn_id, 0)::bigint AS character_actor_id,
        COALESCE(ps.online_status::text, '') AS online_status,
        COALESCE(ps.life_state::text, '') AS life_state,
        COALESCE(pvc.balance, 0)::bigint AS before_solari
    FROM settings s
    LEFT JOIN dune.player_state ps
        ON ps.player_controller_id = s.player_controller_id
    LEFT JOIN dune.player_virtual_currency_balances pvc
        ON pvc.player_controller_id = s.player_controller_id
       AND pvc.currency_id = 0
),
updated AS (
    UPDATE dune.player_virtual_currency_balances pvc
    SET balance = (SELECT target_solari FROM settings)
    FROM before_balance bb
    WHERE pvc.player_controller_id = bb.player_controller_id
      AND pvc.currency_id = 0
    RETURNING pvc.player_controller_id, pvc.currency_id, pvc.balance
),
inserted AS (
    INSERT INTO dune.player_virtual_currency_balances (player_controller_id, currency_id, balance)
    SELECT
        bb.player_controller_id,
        0::smallint,
        s.target_solari
    FROM before_balance bb
    JOIN settings s
        ON s.player_controller_id = bb.player_controller_id
    WHERE NOT EXISTS (SELECT 1 FROM updated)
    RETURNING player_controller_id, currency_id, balance
),
applied AS (
    SELECT * FROM updated
    UNION ALL
    SELECT * FROM inserted
)
SELECT
    bb.character_name,
    bb.character_actor_id,
    bb.player_controller_id,
    bb.online_status,
    bb.life_state,
    bb.before_solari,
    (s.target_solari - bb.before_solari)::bigint AS applied_delta,
    s.target_solari,
    a.balance AS after_solari
FROM before_balance bb
JOIN settings s
    ON s.player_controller_id = bb.player_controller_id
JOIN applied a
    ON a.player_controller_id = bb.player_controller_id
   AND a.currency_id = 0;
"""


def build_add_exchange_bank_solari_sql(character_actor_id, amount):
    """
    Build admin-only SQL to add to the exchange bank Solari balance.

    This edits dune.player_virtual_currency_balances for currency_id 0. If the
    selected player has no row yet, the tool creates one using their
    player_controller_id from dune.player_state.
    """
    actor_id = int(character_actor_id)
    delta = solari_bank_amount_from_value(amount)

    return f"""
WITH settings AS (
    SELECT
        {actor_id}::bigint AS character_actor_id,
        {delta}::bigint AS solari_delta
),
selected_player AS (
    SELECT
        ps.character_name,
        ps.player_pawn_id AS character_actor_id,
        ps.player_controller_id,
        ps.online_status,
        ps.life_state
    FROM dune.player_state ps
    JOIN settings s
        ON s.character_actor_id = ps.player_pawn_id
),
before_balance AS (
    SELECT
        sp.*,
        COALESCE(pvc.balance, 0)::bigint AS before_solari
    FROM selected_player sp
    LEFT JOIN dune.player_virtual_currency_balances pvc
        ON pvc.player_controller_id = sp.player_controller_id
       AND pvc.currency_id = 0
),
updated AS (
    UPDATE dune.player_virtual_currency_balances pvc
    SET balance = pvc.balance + (SELECT solari_delta FROM settings)
    FROM before_balance bb
    WHERE pvc.player_controller_id = bb.player_controller_id
      AND pvc.currency_id = 0
    RETURNING pvc.player_controller_id, pvc.currency_id, pvc.balance
),
inserted AS (
    INSERT INTO dune.player_virtual_currency_balances (player_controller_id, currency_id, balance)
    SELECT
        bb.player_controller_id,
        0::smallint,
        s.solari_delta
    FROM before_balance bb
    JOIN settings s
        ON s.character_actor_id = bb.character_actor_id
    WHERE NOT EXISTS (
        SELECT 1
        FROM updated
    )
    RETURNING player_controller_id, currency_id, balance
),
applied AS (
    SELECT * FROM updated
    UNION ALL
    SELECT * FROM inserted
)
SELECT
    bb.character_name,
    bb.character_actor_id,
    bb.player_controller_id,
    bb.online_status,
    bb.life_state,
    bb.before_solari,
    s.solari_delta AS added_solari,
    a.balance AS after_solari
FROM before_balance bb
JOIN settings s
    ON s.character_actor_id = bb.character_actor_id
JOIN applied a
    ON a.player_controller_id = bb.player_controller_id
   AND a.currency_id = 0;
"""


def build_set_exchange_bank_solari_sql(character_actor_id, target_balance):
    """Build admin-only SQL to set exchange bank Solari exactly."""
    actor_id = int(character_actor_id)
    target = solari_bank_balance_from_value(target_balance)

    return f"""
WITH settings AS (
    SELECT
        {actor_id}::bigint AS character_actor_id,
        {target}::bigint AS target_solari
),
selected_player AS (
    SELECT
        ps.character_name,
        ps.player_pawn_id AS character_actor_id,
        ps.player_controller_id,
        ps.online_status,
        ps.life_state
    FROM dune.player_state ps
    JOIN settings s
        ON s.character_actor_id = ps.player_pawn_id
),
before_balance AS (
    SELECT
        sp.*,
        COALESCE(pvc.balance, 0)::bigint AS before_solari
    FROM selected_player sp
    LEFT JOIN dune.player_virtual_currency_balances pvc
        ON pvc.player_controller_id = sp.player_controller_id
       AND pvc.currency_id = 0
),
updated AS (
    UPDATE dune.player_virtual_currency_balances pvc
    SET balance = (SELECT target_solari FROM settings)
    FROM before_balance bb
    WHERE pvc.player_controller_id = bb.player_controller_id
      AND pvc.currency_id = 0
    RETURNING pvc.player_controller_id, pvc.currency_id, pvc.balance
),
inserted AS (
    INSERT INTO dune.player_virtual_currency_balances (player_controller_id, currency_id, balance)
    SELECT
        bb.player_controller_id,
        0::smallint,
        s.target_solari
    FROM before_balance bb
    JOIN settings s
        ON s.character_actor_id = bb.character_actor_id
    WHERE NOT EXISTS (
        SELECT 1
        FROM updated
    )
    RETURNING player_controller_id, currency_id, balance
),
applied AS (
    SELECT * FROM updated
    UNION ALL
    SELECT * FROM inserted
)
SELECT
    bb.character_name,
    bb.character_actor_id,
    bb.player_controller_id,
    bb.online_status,
    bb.life_state,
    bb.before_solari,
    (s.target_solari - bb.before_solari)::bigint AS applied_delta,
    s.target_solari,
    a.balance AS after_solari
FROM before_balance bb
JOIN settings s
    ON s.character_actor_id = bb.character_actor_id
JOIN applied a
    ON a.player_controller_id = bb.player_controller_id
   AND a.currency_id = 0;
"""


def build_add_solari_bank_sql(character_actor_id, amount):
    """
    Build admin-only SQL to add SolarisCoin to a character's stored balance.

    The older project-owner millionaire query directly edited a SolarisCoin
    stack by inventory id. This version discovers the selected character's
    primary inventory and updates an existing SolarisCoin stack, or creates one
    if the character has no SolarisCoin row yet.
    """
    actor_id = int(character_actor_id)
    delta = solari_bank_amount_from_value(amount)

    return f"""
BEGIN;
WITH settings AS (
    SELECT
        {actor_id}::bigint AS character_actor_id,
        {delta}::bigint AS solari_delta
),
selected_player AS (
    SELECT
        ps.character_name,
        ps.player_pawn_id AS character_actor_id,
        ps.online_status,
        ps.life_state
    FROM dune.player_state ps
    JOIN settings s
        ON s.character_actor_id = ps.player_pawn_id
),
primary_inventory AS (
    SELECT
        sp.*,
        inv.id AS inventory_id
    FROM selected_player sp
    JOIN LATERAL (
        SELECT id
        FROM dune.inventories
        WHERE actor_id = sp.character_actor_id
        ORDER BY id
        LIMIT 1
    ) inv ON true
),
solari_rows AS (
    SELECT
        i.id AS item_id,
        i.inventory_id,
        i.stack_size::bigint AS stack_size,
        ROW_NUMBER() OVER (ORDER BY i.inventory_id, i.id) AS row_number
    FROM primary_inventory pi
    JOIN dune.inventories inv
        ON inv.actor_id = pi.character_actor_id
    JOIN dune.items i
        ON i.inventory_id = inv.id
    WHERE i.template_id = '{SOLARIS_COIN_ITEM_ID}'
),
before_balance AS (
    SELECT
        COALESCE(SUM(stack_size), 0)::bigint AS before_solari,
        COUNT(item_id)::bigint AS before_stack_count,
        COALESCE(MIN(item_id) FILTER (WHERE row_number = 1), 0)::bigint AS first_item_id
    FROM solari_rows
),
inserted AS (
    INSERT INTO dune.items (inventory_id, stack_size, position_index, template_id, quality_level, stats)
    SELECT
        pi.inventory_id,
        s.solari_delta,
        COALESCE((SELECT MAX(position_index) + 1 FROM dune.items WHERE inventory_id = pi.inventory_id), 0),
        '{SOLARIS_COIN_ITEM_ID}',
        0,
        '{{}}'
    FROM primary_inventory pi
    CROSS JOIN settings s
    CROSS JOIN before_balance bb
    WHERE bb.first_item_id = 0
    RETURNING id AS item_id
),
updated AS (
    UPDATE dune.items i
    SET stack_size = i.stack_size + (SELECT solari_delta FROM settings)
    WHERE i.id = (SELECT first_item_id FROM before_balance)
      AND (SELECT first_item_id FROM before_balance) <> 0
    RETURNING i.id AS item_id
)
SELECT
    pi.character_name,
    pi.character_actor_id,
    pi.online_status,
    pi.life_state,
    pi.inventory_id,
    bb.before_solari,
    s.solari_delta AS added_solari,
    (bb.before_solari + s.solari_delta)::bigint AS after_solari,
    CASE WHEN bb.first_item_id = 0 THEN 1 ELSE bb.before_stack_count END AS stack_count,
    COALESCE((SELECT item_id FROM updated), (SELECT item_id FROM inserted)) AS touched_item_id
FROM primary_inventory pi
CROSS JOIN settings s
CROSS JOIN before_balance bb;
COMMIT;
"""


def build_set_solari_bank_sql(character_actor_id, target_balance):
    """
    Build admin-only SQL to set one character's stored SolarisCoin balance.

    This is intended for correction work, such as removing duplicated Solari
    after a market exploit. It sets one primary SolarisCoin stack to the target
    amount and zeroes duplicate SolarisCoin stacks owned by the same character.
    """
    actor_id = int(character_actor_id)
    target = solari_bank_balance_from_value(target_balance)

    return f"""
BEGIN;
WITH settings AS (
    SELECT
        {actor_id}::bigint AS character_actor_id,
        {target}::bigint AS target_solari
),
selected_player AS (
    SELECT
        ps.character_name,
        ps.player_pawn_id AS character_actor_id,
        ps.online_status,
        ps.life_state
    FROM dune.player_state ps
    JOIN settings s
        ON s.character_actor_id = ps.player_pawn_id
),
primary_inventory AS (
    SELECT
        sp.*,
        inv.id AS inventory_id
    FROM selected_player sp
    JOIN LATERAL (
        SELECT id
        FROM dune.inventories
        WHERE actor_id = sp.character_actor_id
        ORDER BY id
        LIMIT 1
    ) inv ON true
),
solari_rows AS (
    SELECT
        i.id AS item_id,
        i.inventory_id,
        i.stack_size::bigint AS stack_size,
        ROW_NUMBER() OVER (ORDER BY i.inventory_id, i.id) AS row_number
    FROM primary_inventory pi
    JOIN dune.inventories inv
        ON inv.actor_id = pi.character_actor_id
    JOIN dune.items i
        ON i.inventory_id = inv.id
    WHERE i.template_id = '{SOLARIS_COIN_ITEM_ID}'
),
before_balance AS (
    SELECT
        COALESCE(SUM(stack_size), 0)::bigint AS before_solari,
        COUNT(item_id)::bigint AS before_stack_count,
        COALESCE(MIN(item_id) FILTER (WHERE row_number = 1), 0)::bigint AS first_item_id
    FROM solari_rows
),
inserted AS (
    INSERT INTO dune.items (inventory_id, stack_size, position_index, template_id, quality_level, stats)
    SELECT
        pi.inventory_id,
        s.target_solari,
        COALESCE((SELECT MAX(position_index) + 1 FROM dune.items WHERE inventory_id = pi.inventory_id), 0),
        '{SOLARIS_COIN_ITEM_ID}',
        0,
        '{{}}'
    FROM primary_inventory pi
    CROSS JOIN settings s
    CROSS JOIN before_balance bb
    WHERE bb.first_item_id = 0
    RETURNING id AS item_id
),
updated_primary AS (
    UPDATE dune.items i
    SET stack_size = (SELECT target_solari FROM settings)
    WHERE i.id = (SELECT first_item_id FROM before_balance)
      AND (SELECT first_item_id FROM before_balance) <> 0
    RETURNING i.id AS item_id
),
zeroed_duplicates AS (
    UPDATE dune.items i
    SET stack_size = 0
    WHERE i.id IN (
        SELECT item_id
        FROM solari_rows
        WHERE row_number > 1
    )
    RETURNING i.id AS item_id
)
SELECT
    pi.character_name,
    pi.character_actor_id,
    pi.online_status,
    pi.life_state,
    pi.inventory_id,
    bb.before_solari,
    (s.target_solari - bb.before_solari)::bigint AS applied_delta,
    s.target_solari,
    s.target_solari AS after_solari,
    CASE WHEN bb.first_item_id = 0 THEN 1 ELSE bb.before_stack_count END AS stack_count,
    (SELECT COUNT(*) FROM zeroed_duplicates) AS duplicate_stacks_zeroed,
    COALESCE((SELECT item_id FROM updated_primary), (SELECT item_id FROM inserted)) AS touched_item_id
FROM primary_inventory pi
CROSS JOIN settings s
CROSS JOIN before_balance bb;
COMMIT;
"""


def get_market_exchanges():
    """
    Return exchange ids observed in the Dune exchange database.

    The market seeder can target a specific exchange id because self-hosted
    stacks may expose the visible player market under an id other than the
    game's Global helper. We always include dune.get_dune_exchange_id('Global')
    and then add any ids already present in dune.dune_exchange_orders.
    """
    sql = """
    WITH global_exchange AS (
        SELECT dune.get_dune_exchange_id('Global')::bigint AS exchange_id
    ),
    observed_orders AS (
        SELECT
            exchange_id,
            MIN(access_point_id)::text AS access_point_id,
            COUNT(*) AS order_count,
            COUNT(*) FILTER (WHERE is_npc_order = TRUE) AS npc_order_count,
            COUNT(*) FILTER (WHERE COALESCE(is_npc_order, FALSE) = FALSE) AS player_order_count
        FROM dune.dune_exchange_orders
        GROUP BY exchange_id
    ),
    candidates AS (
        SELECT exchange_id FROM global_exchange
        UNION
        SELECT exchange_id FROM observed_orders
    )
    SELECT
        c.exchange_id::text,
        CASE
            WHEN c.exchange_id = (SELECT exchange_id FROM global_exchange)
                THEN 'Global'
            ELSE 'Exchange ' || c.exchange_id::text
        END AS label,
        COALESCE(o.access_point_id, '') AS access_point_id,
        COALESCE(o.order_count, 0)::text AS order_count,
        COALESCE(o.npc_order_count, 0)::text AS npc_order_count,
        COALESCE(o.player_order_count, 0)::text AS player_order_count
    FROM candidates c
    LEFT JOIN observed_orders o
        ON o.exchange_id = c.exchange_id
    ORDER BY
        CASE WHEN c.exchange_id = (SELECT exchange_id FROM global_exchange) THEN 0 ELSE 1 END,
        c.exchange_id;
    """

    exchanges = []
    for line in _run_psql_tsv(sql, timeout=20):
        parts = line.split("\t")
        if len(parts) < 6:
            continue

        exchanges.append(
            {
                "exchange_id": parts[0],
                "label": parts[1],
                "access_point_id": parts[2],
                "order_count": parts[3],
                "npc_order_count": parts[4],
                "player_order_count": parts[5],
            }
        )

    return exchanges


def build_market_seed_plan(price_multiplier=None):
    multiplier = market_price_multiplier_from_value(price_multiplier)
    return market_seed.build_seed_plan(
        MARKET_ITEM_DATA_FILE,
        multiplier,
        MARKET_EQUIPPABLE_LISTINGS,
        MARKET_SCHEMATIC_LISTINGS,
        MARKET_RESOURCE_STACK_SIZE,
        MARKET_SPECIAL_NAME_TERMS,
        MARKET_SPECIAL_NAME_LISTINGS,
        MARKET_REFINED_RESOURCE_PRICE_MULTIPLIER,
        MARKET_RAW_RESOURCE_PRICE_MULTIPLIER,
        MARKET_RAW_RESOURCE_PRICE_OVERRIDES,
    )


def market_seed_summary(price_multiplier=None):
    multiplier = market_price_multiplier_from_value(price_multiplier)
    plan = build_market_seed_plan(multiplier)
    return market_seed.summary(plan, multiplier)


def seed_market_preset(clear_existing=True, price_multiplier=None, exchange_id=None):
    multiplier = market_price_multiplier_from_value(price_multiplier)
    exchange_id_override = market_exchange_id_from_value(exchange_id)
    plan = build_market_seed_plan(multiplier)
    if not plan:
        raise ValueError(f"market item data not found or empty: {MARKET_ITEM_DATA_FILE}")
    sql = market_seed.build_seed_sql(
        plan,
        MARKET_BOT_CLASS,
        multiplier,
        clear_existing=clear_existing,
        exchange_id_override=exchange_id_override,
    )
    return run_psql_script(sql, timeout=300)


def buy_player_market_listings(price_multiplier=None, threshold_percent=None, max_buys=None):
    multiplier = market_price_multiplier_from_value(price_multiplier)
    threshold = market_buy_threshold_from_value(threshold_percent)
    buy_limit = market_buy_max_from_value(max_buys)
    plan = build_market_seed_plan(multiplier)
    if not plan:
        raise ValueError(f"market item data not found or empty: {MARKET_ITEM_DATA_FILE}")
    sql = market_seed.build_buy_player_listings_sql(
        plan,
        MARKET_BOT_CLASS,
        threshold_percent=threshold,
        max_buys=buy_limit,
    )
    return run_psql_script(sql, timeout=300)


def run_buyback_sweep(price_multiplier=None, threshold_percent=None, max_buys=None):
    """
    Run one buyback sweep with overlap protection.

    Manual buyback, timed buyback, and timed reseed share this lock so two
    long market database jobs cannot run at the same time.
    """
    acquired = MARKET_BUYBACK_RUN_LOCK.acquire(blocking=False)
    if not acquired:
        raise RuntimeError("buyback sweep already running")
    try:
        return buy_player_market_listings(
            price_multiplier=price_multiplier,
            threshold_percent=threshold_percent,
            max_buys=max_buys,
        )
    finally:
        MARKET_BUYBACK_RUN_LOCK.release()


def run_market_reseed(price_multiplier=None, exchange_id=None):
    """
    Clear this bot's NPC listings and reseed the preset market.

    This is intentionally the same operation as clicking Seed Preset Market
    with "clear existing NPC listings" checked.
    """
    acquired = MARKET_BUYBACK_RUN_LOCK.acquire(blocking=False)
    if not acquired:
        raise RuntimeError("market job already running")
    try:
        return seed_market_preset(
            clear_existing=True,
            price_multiplier=price_multiplier,
            exchange_id=exchange_id,
        )
    finally:
        MARKET_BUYBACK_RUN_LOCK.release()


def market_buyback_status():
    with MARKET_BUYBACK_STATE_LOCK:
        return dict(MARKET_BUYBACK_STATE)


def set_market_buyback_state(**updates):
    with MARKET_BUYBACK_STATE_LOCK:
        MARKET_BUYBACK_STATE.update(updates)
        return dict(MARKET_BUYBACK_STATE)


def market_buyback_loop():
    """
    Background timed buyback worker.

    Start runs one immediate sweep, then this loop handles later interval runs.
    """
    while True:
        status = market_buyback_status()
        interval_seconds = max(1, int(status["interval_minutes"])) * 60
        if MARKET_BUYBACK_STOP_EVENT.wait(interval_seconds):
            break

        status = market_buyback_status()
        if not status.get("enabled"):
            continue

        multiplier = status.get("price_multiplier") or MARKET_PRICE_MULTIPLIER
        threshold = status.get("threshold_percent") or MARKET_BUY_THRESHOLD_PERCENT
        max_buys = status.get("max_buys") or MARKET_BUY_MAX_PER_CLICK
        started = datetime.now()
        try:
            output = run_buyback_sweep(
                price_multiplier=multiplier,
                threshold_percent=threshold,
                max_buys=max_buys,
            )
            next_run = datetime.now() + timedelta(minutes=int(status["interval_minutes"]))
            set_market_buyback_state(
                last_run=started.strftime("%Y-%m-%d %H:%M:%S"),
                last_output=output[-4000:],
                last_error="",
                next_run=next_run.strftime("%Y-%m-%d %H:%M:%S"),
                runs=int(status.get("runs") or 0) + 1,
            )
            log_action(
                "system",
                f"automated {MARKET_BOT_CLASS} buyback sweep at {threshold}% threshold using {multiplier}x prices, max {max_buys}",
            )
        except Exception as exc:
            next_run = datetime.now() + timedelta(minutes=int(status["interval_minutes"]))
            set_market_buyback_state(
                last_run=started.strftime("%Y-%m-%d %H:%M:%S"),
                last_error=str(exc),
                next_run=next_run.strftime("%Y-%m-%d %H:%M:%S"),
            )
            log_action("system", f"automated buyback sweep failed: {exc}")


def start_market_buyback_sweep(
    price_multiplier=None,
    threshold_percent=None,
    max_buys=None,
    interval_minutes=None,
    run_now=True,
):
    global MARKET_BUYBACK_THREAD, MARKET_BUYBACK_STOP_EVENT

    multiplier = market_price_multiplier_from_value(price_multiplier)
    threshold = market_buy_threshold_from_value(threshold_percent)
    buy_limit = market_buy_max_from_value(max_buys)
    interval = market_buyback_interval_from_value(interval_minutes)
    next_run = datetime.now() + timedelta(minutes=interval)

    with MARKET_BUYBACK_STATE_LOCK:
        MARKET_BUYBACK_STATE.update(
            {
                "enabled": True,
                "price_multiplier": multiplier,
                "threshold_percent": threshold,
                "max_buys": buy_limit,
                "interval_minutes": interval,
                "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S"),
                "last_error": "",
            }
        )

    if MARKET_BUYBACK_THREAD is None or not MARKET_BUYBACK_THREAD.is_alive():
        MARKET_BUYBACK_STOP_EVENT = threading.Event()
        MARKET_BUYBACK_THREAD = threading.Thread(target=market_buyback_loop, daemon=True)
        MARKET_BUYBACK_THREAD.start()

    if run_now:
        started = datetime.now()
        try:
            output = run_buyback_sweep(
                price_multiplier=multiplier,
                threshold_percent=threshold,
                max_buys=buy_limit,
            )
            next_run = datetime.now() + timedelta(minutes=interval)
            set_market_buyback_state(
                last_run=started.strftime("%Y-%m-%d %H:%M:%S"),
                last_output=output[-4000:],
                last_error="",
                next_run=next_run.strftime("%Y-%m-%d %H:%M:%S"),
                runs=int(market_buyback_status().get("runs") or 0) + 1,
            )
            log_action(
                "system",
                f"started automated {MARKET_BOT_CLASS} buyback with immediate sweep at {threshold}% threshold using {multiplier}x prices, max {buy_limit}",
            )
        except Exception as exc:
            next_run = datetime.now() + timedelta(minutes=interval)
            set_market_buyback_state(
                last_run=started.strftime("%Y-%m-%d %H:%M:%S"),
                last_error=str(exc),
                next_run=next_run.strftime("%Y-%m-%d %H:%M:%S"),
            )
            raise

    return market_buyback_status()


def stop_market_buyback_sweep():
    MARKET_BUYBACK_STOP_EVENT.set()
    return set_market_buyback_state(enabled=False, next_run="")


def market_reseed_status():
    with MARKET_RESEED_STATE_LOCK:
        return dict(MARKET_RESEED_STATE)


def set_market_reseed_state(**updates):
    with MARKET_RESEED_STATE_LOCK:
        MARKET_RESEED_STATE.update(updates)
        return dict(MARKET_RESEED_STATE)


def market_reseed_loop():
    """Background timed reseed worker."""
    while True:
        status = market_reseed_status()
        interval_seconds = max(1, int(status["interval_minutes"])) * 60
        if MARKET_RESEED_STOP_EVENT.wait(interval_seconds):
            break

        status = market_reseed_status()
        if not status.get("enabled"):
            continue

        multiplier = status.get("price_multiplier") or MARKET_PRICE_MULTIPLIER
        exchange_id = status.get("exchange_id") or MARKET_SEED_EXCHANGE_ID
        started = datetime.now()
        try:
            output = run_market_reseed(
                price_multiplier=multiplier,
                exchange_id=exchange_id,
            )
            next_run = datetime.now() + timedelta(minutes=int(status["interval_minutes"]))
            set_market_reseed_state(
                last_run=started.strftime("%Y-%m-%d %H:%M:%S"),
                last_output=output[-4000:],
                last_error="",
                next_run=next_run.strftime("%Y-%m-%d %H:%M:%S"),
                runs=int(status.get("runs") or 0) + 1,
            )
            log_action(
                "system",
                f"automated {MARKET_BOT_CLASS} market reseed using {multiplier}x prices exchange_id={exchange_id or 'Global'}",
            )
        except Exception as exc:
            next_run = datetime.now() + timedelta(minutes=int(status["interval_minutes"]))
            set_market_reseed_state(
                last_run=started.strftime("%Y-%m-%d %H:%M:%S"),
                last_error=str(exc),
                next_run=next_run.strftime("%Y-%m-%d %H:%M:%S"),
            )
            log_action("system", f"automated market reseed failed: {exc}")


def start_market_reseed_sweep(
    price_multiplier=None,
    exchange_id=None,
    interval_minutes=None,
    run_now=True,
):
    global MARKET_RESEED_THREAD, MARKET_RESEED_STOP_EVENT

    multiplier = market_price_multiplier_from_value(price_multiplier)
    target_exchange_id = market_exchange_id_from_value(exchange_id)
    interval = market_reseed_interval_from_value(interval_minutes)
    next_run = datetime.now() + timedelta(minutes=interval)

    with MARKET_RESEED_STATE_LOCK:
        MARKET_RESEED_STATE.update(
            {
                "enabled": True,
                "price_multiplier": multiplier,
                "exchange_id": target_exchange_id,
                "interval_minutes": interval,
                "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S"),
                "last_error": "",
            }
        )

    if MARKET_RESEED_THREAD is None or not MARKET_RESEED_THREAD.is_alive():
        MARKET_RESEED_STOP_EVENT = threading.Event()
        MARKET_RESEED_THREAD = threading.Thread(target=market_reseed_loop, daemon=True)
        MARKET_RESEED_THREAD.start()

    if run_now:
        started = datetime.now()
        try:
            output = run_market_reseed(
                price_multiplier=multiplier,
                exchange_id=target_exchange_id,
            )
            next_run = datetime.now() + timedelta(minutes=interval)
            set_market_reseed_state(
                last_run=started.strftime("%Y-%m-%d %H:%M:%S"),
                last_output=output[-4000:],
                last_error="",
                next_run=next_run.strftime("%Y-%m-%d %H:%M:%S"),
                runs=int(market_reseed_status().get("runs") or 0) + 1,
            )
            log_action(
                "system",
                f"started automated {MARKET_BOT_CLASS} market reseed using {multiplier}x prices exchange_id={target_exchange_id or 'Global'}",
            )
        except Exception as exc:
            next_run = datetime.now() + timedelta(minutes=interval)
            set_market_reseed_state(
                last_run=started.strftime("%Y-%m-%d %H:%M:%S"),
                last_error=str(exc),
                next_run=next_run.strftime("%Y-%m-%d %H:%M:%S"),
            )
            raise

    return market_reseed_status()


def stop_market_reseed_sweep():
    MARKET_RESEED_STOP_EVENT.set()
    return set_market_reseed_state(enabled=False, next_run="")


def build_market_clear_npc_sql():
    """
    Remove only this market bot's NPC exchange listings and their backing items.

    Player listings are protected by both owner_id and is_npc_order = TRUE.
    This is useful while tuning presets because it clears the exchange without
    immediately creating replacement listings.
    """
    bot_class = market_seed.sql_literal(MARKET_BOT_CLASS)
    return f"""
DO $$
DECLARE
    v_owner_id BIGINT;
    v_item_ids BIGINT[];
BEGIN
    SELECT id INTO v_owner_id
    FROM dune.actors
    WHERE class = {bot_class}
    LIMIT 1;

    IF v_owner_id IS NULL THEN
        RAISE NOTICE 'No market bot actor found for class {MARKET_BOT_CLASS}. Nothing to clear.';
        RETURN;
    END IF;

    SELECT ARRAY_AGG(item_id) INTO v_item_ids
    FROM dune.dune_exchange_orders
    WHERE owner_id = v_owner_id
      AND is_npc_order = TRUE
      AND item_id IS NOT NULL;

    DELETE FROM dune.dune_exchange_sell_orders
    WHERE order_id IN (
        SELECT id
        FROM dune.dune_exchange_orders
        WHERE owner_id = v_owner_id
          AND is_npc_order = TRUE
    );

    DELETE FROM dune.dune_exchange_orders
    WHERE owner_id = v_owner_id
      AND is_npc_order = TRUE;

    IF v_item_ids IS NOT NULL THEN
        DELETE FROM dune.items
        WHERE id = ANY(v_item_ids);
    END IF;
END $$;
"""


def clear_market_npc_listings():
    return run_psql_script(build_market_clear_npc_sql(), timeout=120)


def get_characters(include_offline=True):
    """
    Return character rows with IDs needed by the panel.

    include_offline=True is important for overrepair, because overrepair
    should be run while the character is logged off.
    """
    where_clause = "" if include_offline else "WHERE ps.online_status <> 'Offline'"

    sql = f"""
    SELECT
        ps.character_name,
        ps.online_status,
        ps.life_state,
        ps.player_pawn_id,
        ps.player_controller_id,
        ps.player_state_id,
        inv.id,
        acc."user",
        acc.funcom_id,
        COALESCE(a.map, '') AS map,
        COALESCE(a.partition_id::text, '') AS partition_id
    FROM dune.player_state ps
    LEFT JOIN dune.accounts acc
        ON acc.id = ps.account_id
    LEFT JOIN dune.actors a
        ON a.id = ps.player_pawn_id
    LEFT JOIN LATERAL (
        SELECT id
        FROM dune.inventories
        WHERE actor_id = ps.player_pawn_id
        ORDER BY id
        LIMIT 1
    ) inv ON true
    {where_clause}
    ORDER BY
        CASE WHEN ps.online_status = 'Offline' THEN 0 ELSE 1 END,
        ps.character_name,
        inv.id;
    """

    cmd = [
        "docker",
        "exec",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        "dune",
        "-d",
        "dune",
        "-At",
        "-F",
        "\t",
        "-c",
        sql,
    ]

    try:
        proc = run_process(
            cmd,
            timeout=15,
        )

        rows = []

        for line in proc.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 11:
                continue

            rows.append(
                {
                    "character_name": parts[0],
                    "online_status": parts[1],
                    "life_state": parts[2],
                    "character_actor_id": parts[3],
                    "player_controller_id": parts[4],
                    "player_state_id": parts[5],
                    "inventory_id": parts[6],
                    "fls_id": parts[7],
                    "funcom_id": parts[8],
                    "map": parts[9],
                    "partition_id": parts[10],
                }
            )

        return rows

    except Exception:
        return []


def _run_psql_tsv(sql, timeout=15):
    """
    Run a read-only-ish psql query and return tab-separated output rows.

    Keep this helper small and explicit for UI pickers that need live database
    choices but should not expose full SQL output to the browser.
    """
    cmd = [
        "docker",
        "exec",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        "dune",
        "-d",
        "dune",
        "-At",
        "-F",
        "\t",
        "-c",
        sql,
    ]

    proc = run_process(
        cmd,
        timeout=timeout,
    )

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "psql query failed")

    return proc.stdout.strip().splitlines()


def _developer_search_terms(query):
    """
    Convert a loose research query into safe ILIKE terms.

    This is for the hidden developer page only. It keeps future NPC/encounter
    research useful without exposing a raw SQL console or any write path.
    """
    raw = (query or "").strip() or "npc raider sardaukar sandflies ghola encounter spawn ai"
    seen = set()
    terms = []

    for part in re.split(r"[\s,;]+", raw):
        cleaned = re.sub(r"[^A-Za-z0-9_./:-]", "", part).strip()
        folded = cleaned.casefold()
        if cleaned and folded not in seen:
            terms.append(cleaned[:80])
            seen.add(folded)
        if len(terms) >= 8:
            break

    return terms or ["npc"]


def _ilike_any_sql(columns, terms):
    """Build a constrained OR expression against known text-ish columns."""
    clauses = []
    for term in terms:
        safe_term = term.replace("'", "''")
        for column in columns:
            clauses.append(f"{column}::text ILIKE '%{safe_term}%'")
    return " OR ".join(clauses) or "false"


def _tsv_dicts(rows, columns):
    parsed = []
    for row in rows:
        parts = row.split("\t")
        parsed.append({column: parts[idx] if idx < len(parts) else "" for idx, column in enumerate(columns)})
    return parsed


def developer_npc_research(query):
    """
    Read-only NPC/encounter discovery helper for the hidden developer page.

    Current research found no safe NPC spawn command and no persistent combat
    NPC actor pattern. These searches help future testing discover a real
    command or live actor pattern before any spawn UI is considered.
    """
    terms = _developer_search_terms(query)

    sections = [
        (
            "actors",
            ["id", "class", "map", "partition_id", "dimension_index", "transform"],
            f"""
            SELECT id::text, class, map, partition_id::text, dimension_index::text, transform::text
            FROM dune.actors
            WHERE {_ilike_any_sql(["class", "map", "properties", "gas_attributes"], terms)}
            ORDER BY map, class, id
            LIMIT 50;
            """,
        ),
        (
            "actor_audit",
            ["class", "count"],
            f"""
            SELECT class, COUNT(*)::text
            FROM dune.actor_audit
            WHERE {_ilike_any_sql(["class"], terms)}
            GROUP BY class
            ORDER BY COUNT(*) DESC, class
            LIMIT 50;
            """,
        ),
        (
            "actor_spawners",
            ["spawner_id", "map", "name", "dimension_index"],
            f"""
            SELECT id::text, map, name, dimension_index::text
            FROM dune.actor_spawners
            WHERE {_ilike_any_sql(["map", "name"], terms)}
            ORDER BY map, name, id
            LIMIT 50;
            """,
        ),
        (
            "actor_spawner_actors",
            ["spawner_id", "actor_id", "class", "map", "partition_id", "dimension_index"],
            f"""
            SELECT
                asa.spawner_id::text,
                asa.actor_id::text,
                COALESCE(a.class, ''),
                COALESCE(a.map, ''),
                COALESCE(a.partition_id::text, ''),
                COALESCE(a.dimension_index::text, '')
            FROM dune.actor_spawner_actors asa
            LEFT JOIN dune.actors a
                ON a.id = asa.actor_id
            LEFT JOIN dune.actor_spawners s
                ON s.id = asa.spawner_id
            WHERE {_ilike_any_sql(["a.class", "a.map", "s.name", "s.map"], terms)}
            ORDER BY asa.spawner_id, asa.actor_id
            LIMIT 50;
            """,
        ),
        (
            "encounters_static",
            ["map_name", "package_name", "actor_name", "encounter_name", "waiting_for_reset"],
            f"""
            SELECT map_name, package_name, actor_name, encounter_name, waiting_for_reset::text
            FROM dune.encounters_static
            WHERE {_ilike_any_sql(["map_name", "package_name", "actor_name", "encounter_name"], terms)}
            ORDER BY map_name, package_name, actor_name
            LIMIT 50;
            """,
        ),
        (
            "event_log",
            ["id", "category", "function_name", "message", "meta", "event_time"],
            f"""
            SELECT
                id::text,
                category::text,
                function_name::text,
                message::text,
                left(meta::text, 500),
                event_time::text
            FROM dune.event_log
            WHERE {_ilike_any_sql(["category", "function_name", "message", "meta"], terms)}
            ORDER BY event_time DESC
            LIMIT 50;
            """,
        ),
        (
            "game_events",
            ["actor_id", "event_type", "map", "partition_id", "custom_data", "universe_time"],
            f"""
            SELECT
                actor_id::text,
                event_type::text,
                map,
                partition_id::text,
                left(custom_data::text, 500),
                universe_time::text
            FROM dune.game_events
            WHERE {_ilike_any_sql(["map", "custom_data"], terms)}
            ORDER BY universe_time DESC
            LIMIT 50;
            """,
        ),
    ]

    result = {"terms": terms, "sections": {}}
    for key, columns, sql in sections:
        try:
            rows = _run_psql_tsv(sql, timeout=20)
            result["sections"][key] = {"ok": True, "columns": columns, "rows": _tsv_dicts(rows, columns)}
        except Exception as exc:
            result["sections"][key] = {"ok": False, "columns": columns, "rows": [], "error": str(exc)}

    return result


def _sql_literal(value):
    """Quote a simple SQL literal for generated maintenance scripts."""
    return "'" + str(value).replace("'", "''") + "'"


def _cheat_type_enum_values():
    """
    Return known values from dune.cheat_type_enum.

    The only value observed in borrowed/researched routines so far is
    negative_solaris, but querying the enum keeps this tool adaptable if the
    game schema exposes additional ban/cheat categories on a server.
    """
    sql = """
    SELECT e.enumlabel
    FROM pg_enum e
    JOIN pg_type t
        ON t.oid = e.enumtypid
    JOIN pg_namespace n
        ON n.oid = t.typnamespace
    WHERE n.nspname = 'dune'
      AND t.typname = 'cheat_type_enum'
    ORDER BY e.enumsortorder;
    """

    try:
        rows = _run_psql_tsv(sql, timeout=10)
        values = [row.strip() for row in rows if row.strip()]
        return values or ["negative_solaris"]
    except Exception:
        return ["negative_solaris"]


def developer_ban_lookup(query):
    """
    Read cheater-tracking rows for the hidden developer page.

    This is intentionally labeled as ban research instead of a confirmed ban
    list. IceHunter/DB routines show cheater_tracking and log_cheating, but we
    have not yet verified that adding/removing these rows reliably bans/unbans
    a player in every RedBlink/Funcom runtime.
    """
    raw_query = (query or "").strip()
    cleaned_query = re.sub(r"[^A-Za-z0-9_ .@:/#-]", "", raw_query)[:120].strip()
    filter_sql = ""

    if cleaned_query:
        safe_query = cleaned_query.replace("'", "''")
        filter_sql = f"""
        WHERE (
            ct.id::text ILIKE '%{safe_query}%'
            OR ct.fls_id ILIKE '%{safe_query}%'
            OR ct.cheat_type::text ILIKE '%{safe_query}%'
            OR a.id::text ILIKE '%{safe_query}%'
            OR COALESCE(a.funcom_id, '') ILIKE '%{safe_query}%'
            OR COALESCE(ps.character_name, '') ILIKE '%{safe_query}%'
        )
        """

    cheater_columns = [
        "row_id",
        "event_time",
        "fls_id",
        "cheat_type",
        "account_id",
        "funcom_id",
        "character_name",
        "online_status",
    ]
    cheater_sql = f"""
    SELECT
        ct.id::text,
        ct.event_time::text,
        ct.fls_id,
        ct.cheat_type::text,
        COALESCE(a.id::text, ''),
        COALESCE(a.funcom_id, ''),
        COALESCE(ps.character_name, ''),
        COALESCE(ps.online_status::text, '')
    FROM dune.cheater_tracking ct
    LEFT JOIN dune.accounts a
        ON a."user" = ct.fls_id
    LEFT JOIN dune.player_state ps
        ON ps.account_id = a.id
    {filter_sql}
    ORDER BY ct.event_time DESC, ct.id DESC
    LIMIT 100;
    """

    removal_columns = ["row_id", "event_time", "account_id", "fls_id", "reason"]
    removal_filter_sql = ""
    if cleaned_query:
        safe_query = cleaned_query.replace("'", "''")
        removal_filter_sql = f"""
        WHERE (
            id::text ILIKE '%{safe_query}%'
            OR account_id::text ILIKE '%{safe_query}%'
            OR COALESCE(fls_id, '') ILIKE '%{safe_query}%'
            OR COALESCE(reason, '') ILIKE '%{safe_query}%'
        )
        """
    removal_sql = f"""
    SELECT
        id::text,
        event_time::text,
        account_id::text,
        COALESCE(fls_id, ''),
        COALESCE(reason, '')
    FROM dune.account_removal_log
    {removal_filter_sql}
    ORDER BY event_time DESC, id DESC
    LIMIT 25;
    """

    result = {
        "query": cleaned_query,
        "cheat_types": _cheat_type_enum_values(),
        "sections": {},
    }

    for key, columns, sql in (
        ("cheater_tracking", cheater_columns, cheater_sql),
        ("account_removal_log", removal_columns, removal_sql),
    ):
        try:
            rows = _run_psql_tsv(sql, timeout=20)
            result["sections"][key] = {"ok": True, "columns": columns, "rows": _tsv_dicts(rows, columns)}
        except Exception as exc:
            result["sections"][key] = {"ok": False, "columns": columns, "rows": [], "error": str(exc)}

    return result


def build_developer_flag_cheater_sql(fls_id, cheat_type):
    """
    Build developer-only SQL to add a cheater_tracking row.

    This uses dune.log_cheating instead of pretending a verified ban command
    exists. Keep it on the Developer page until live ban behavior is confirmed.
    """
    safe_fls = str(fls_id).strip()
    if not safe_fls:
        raise ValueError("missing FLS ID")

    cheat_types = _cheat_type_enum_values()
    if cheat_type not in cheat_types:
        raise ValueError("unknown cheat type")

    return f"""
BEGIN;
SELECT dune.log_cheating({_sql_literal(safe_fls)}, {_sql_literal(cheat_type)}::dune.cheat_type_enum);

SELECT
    'cheater_tracking_row_added' AS status,
    {_sql_literal(safe_fls)} AS fls_id,
    {_sql_literal(cheat_type)} AS cheat_type,
    'Experimental: this may not be a real ban until verified in game.' AS note;
COMMIT;
"""


def build_developer_unflag_cheater_sql(fls_id="", row_id=""):
    """
    Build developer-only SQL to remove cheater_tracking rows.

    Removing rows is the safest currently known "unban" research path, but it
    only proves the DB row was removed. Game services may cache or enforce bans
    elsewhere, so the UI keeps this marked experimental.
    """
    safe_fls = str(fls_id).strip()
    safe_row_id = str(row_id).strip()

    clauses = []
    if safe_fls:
        clauses.append(f"fls_id = {_sql_literal(safe_fls)}")
    if safe_row_id:
        try:
            clauses.append(f"id = {int(safe_row_id)}")
        except ValueError as exc:
            raise ValueError("cheater row ID must be a whole number") from exc

    if not clauses:
        raise ValueError("enter an FLS ID or cheater row ID to remove")

    where_sql = " OR ".join(clauses)

    return f"""
BEGIN;
WITH deleted AS (
    DELETE FROM dune.cheater_tracking
    WHERE {where_sql}
    RETURNING id, event_time, fls_id, cheat_type
)
SELECT
    COUNT(*)::text AS removed_rows,
    COALESCE(string_agg(id::text, ', ' ORDER BY id), '') AS removed_row_ids,
    'Experimental: removed cheater_tracking rows only; verify in game.' AS note
FROM deleted;
COMMIT;
"""


def get_character_inventories(character_actor_id):
    """
    Return every inventory row owned by a character actor.

    Dune DB builds have not been perfectly consistent about inventory label
    columns, so this uses to_jsonb(inv)->>'column_name' lookups. Those are safe
    even when a possible label column does not exist, unlike direct column
    references such as inv.type.
    """
    actor_id = int(character_actor_id)

    sql = f"""
    SELECT
        inv.id,
        COALESCE(
            NULLIF(to_jsonb(inv)->>'name', ''),
            NULLIF(to_jsonb(inv)->>'inventory_name', ''),
            NULLIF(to_jsonb(inv)->>'display_name', ''),
            NULLIF(to_jsonb(inv)->>'label', ''),
            NULLIF(to_jsonb(inv)->>'inventory_type', ''),
            NULLIF(to_jsonb(inv)->>'type', ''),
            NULLIF(to_jsonb(inv)->>'slot_type', ''),
            NULLIF(to_jsonb(inv)->>'container_type', ''),
            'Inventory ' || inv.id::text
        ) AS inventory_label,
        (
            SELECT COUNT(*)
            FROM dune.items i
            WHERE i.inventory_id = inv.id
        ) AS item_count
    FROM dune.inventories inv
    WHERE inv.actor_id = {actor_id}
    ORDER BY inv.id;
    """

    inventories = []
    for line in _run_psql_tsv(sql):
        parts = line.split("\t")
        if len(parts) < 3:
            continue

        inventories.append(
            {
                "inventory_id": parts[0],
                "inventory_label": parts[1] or f"Inventory {parts[0]}",
                "item_count": parts[2] or "0",
            }
        )

    return inventories


def get_character_inventory_items(character_actor_id, inventory_id):
    """
    Return selectable item rows for one character-owned inventory.

    The item row id is the unique database row we update for single-item
    overrepair. The template id is shown to admins because it is usually the
    most recognizable item identifier available in the server database.
    """
    actor_id = int(character_actor_id)
    inv_id = int(inventory_id)

    sql = f"""
    SELECT
        i.id,
        COALESCE(i.template_id, ''),
        COALESCE(i.position_index::text, ''),
        COALESCE(i.stack_size::text, ''),
        COALESCE(i.quality_level::text, ''),
        COALESCE(i.stats #>> '{{FItemStackAndDurabilityStats,1,CurrentDurability}}', ''),
        COALESCE(i.stats #>> '{{FItemStackAndDurabilityStats,1,DecayedMaxDurability}}', ''),
        COALESCE(i.stats #>> '{{FItemStackAndDurabilityStats,1,MaxDurability}}', '')
    FROM dune.items i
    JOIN dune.inventories inv
        ON inv.id = i.inventory_id
    WHERE inv.actor_id = {actor_id}
      AND inv.id = {inv_id}
    ORDER BY
        i.position_index NULLS LAST,
        i.id;
    """

    items = []
    for line in _run_psql_tsv(sql):
        parts = line.split("\t")
        if len(parts) < 8:
            continue

        items.append(
            {
                "item_row_id": parts[0],
                "template_id": parts[1],
                "position_index": parts[2],
                "stack_size": parts[3],
                "quality_level": parts[4],
                "current_durability": parts[5],
                "decayed_max_durability": parts[6],
                "max_durability": parts[7],
            }
        )

    return items


def get_user_character_name(username):
    """
    Return the exact in-game character name bound to a local web account.

    VIP self-service authorization depends on this local binding. Admins should
    enter the character name verbatim when creating/updating VIP accounts.
    """
    conn = db()
    row = conn.execute(
        "SELECT COALESCE(character_name, '') AS character_name FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()
    return (row["character_name"] if row else "").strip()


def get_self_character_for_user(username):
    """
    Resolve a VIP account to its own character actor, FLS/account id, and
    primary character inventory.

    The character name comes from the local users table and is never accepted
    from the browser during VIP actions.
    """
    character_name = get_user_character_name(username)
    if not character_name:
        raise ValueError("No in-game character name is linked to this web account.")

    safe_name = character_name.replace("'", "''")
    sql = f"""
    SELECT
        ps.character_name,
        ps.online_status,
        ps.life_state,
        ps.player_pawn_id,
        inv.id,
        acc."user",
        acc.funcom_id
    FROM dune.player_state ps
    LEFT JOIN dune.accounts acc
        ON acc.id = ps.account_id
    LEFT JOIN LATERAL (
        SELECT id
        FROM dune.inventories
        WHERE actor_id = ps.player_pawn_id
        ORDER BY id
        LIMIT 1
    ) inv ON true
    WHERE ps.character_name = '{safe_name}'
    ORDER BY inv.id
    LIMIT 1;
    """

    cmd = [
        "docker",
        "exec",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        "dune",
        "-d",
        "dune",
        "-At",
        "-F",
        "\t",
        "-c",
        sql,
    ]

    proc = run_process(
        cmd,
        timeout=15,
    )

    if proc.returncode != 0:
        raise ValueError(proc.stderr.strip() or "failed to query linked character")

    line = proc.stdout.strip()
    if not line:
        raise ValueError(f"Linked character not found: {character_name}")

    parts = line.split("\t")
    if len(parts) < 7:
        raise ValueError("unexpected linked character query result")

    return {
        "character_name": parts[0],
        "online_status": parts[1],
        "life_state": parts[2],
        "character_actor_id": parts[3],
        "inventory_id": parts[4],
        "fls_id": parts[5],
        "funcom_id": parts[6],
    }



def get_vehicles():
    """
    Return vehicles that have module rows.

    In observed data, the vehicle actor id matches vehicle_modules.vehicle_id.
    This query intentionally joins actors to vehicle_modules so the selector
    only shows vehicles with repairable module data.
    """
    sql = r"""
    SELECT
        a.id AS vehicle_id,
        a.class AS vehicle_class,
        COUNT(vm.id) AS module_count,
        MIN((vm.stats #>> '{FVehicleModuleDurabilityStats,1,CurrentDurability}')::numeric) AS min_durability,
        MAX((vm.stats #>> '{FVehicleModuleDurabilityStats,1,CurrentDurability}')::numeric) AS max_durability
    FROM dune.actors a
    JOIN dune.vehicle_modules vm
        ON vm.vehicle_id = a.id
    WHERE a.class ILIKE '%Vehicle%'
       OR a.class ILIKE '%Ornithopter%'
       OR a.class ILIKE '%Sandbike%'
       OR a.class ILIKE '%Buggy%'
       OR a.class ILIKE '%TreadWheel%'
       OR a.class ILIKE '%SandCrawler%'
    GROUP BY a.id, a.class
    ORDER BY a.id;
    """

    cmd = [
        "docker",
        "exec",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        "dune",
        "-d",
        "dune",
        "-At",
        "-F",
        "\t",
        "-c",
        sql,
    ]

    try:
        proc = run_process(
            cmd,
            timeout=15,
        )

        vehicles = []

        for line in proc.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 5:
                continue

            vehicles.append(
                {
                    "vehicle_id": parts[0],
                    "vehicle_class": parts[1],
                    "module_count": parts[2],
                    "min_durability": parts[3],
                    "max_durability": parts[4],
                }
            )

        return vehicles

    except Exception:
        return []


def build_vehicle_repair_sql(vehicle_id, durability_value):
    """
    Build SQL to set durability for every module on one vehicle.

    This updates the observed vehicle module durability path:
        FVehicleModuleDurabilityStats -> 1 -> CurrentDurability

    It also writes:
        FVehicleModuleDurabilityStats -> 1 -> MaxDurability

    That second key may be created if absent. This is intentional for the
    overrepair behavior, but this remains an admin-only experimental tool.
    """
    veh_id = int(vehicle_id)
    durability = float(durability_value)

    return f"""
WITH settings AS (
    SELECT
        {veh_id}::bigint AS target_vehicle_id,
        {durability}::numeric AS durability_value
),
updated_modules AS (
    UPDATE dune.vehicle_modules vm
    SET stats =
        jsonb_set(
            jsonb_set(
                vm.stats,
                '{{FVehicleModuleDurabilityStats,1,CurrentDurability}}',
                to_jsonb(s.durability_value),
                true
            ),
            '{{FVehicleModuleDurabilityStats,1,MaxDurability}}',
            to_jsonb(s.durability_value),
            true
        )
    FROM settings s
    WHERE vm.vehicle_id = s.target_vehicle_id
      AND vm.stats #> '{{FVehicleModuleDurabilityStats,1,CurrentDurability}}' IS NOT NULL
    RETURNING
        vm.id AS module_id,
        vm.vehicle_id,
        vm.template_id,
        vm.stats #> '{{FVehicleModuleDurabilityStats,1,CurrentDurability}}'
            AS current_durability,
        vm.stats #> '{{FVehicleModuleDurabilityStats,1,MaxDurability}}'
            AS max_durability
)
SELECT
    module_id,
    vehicle_id,
    template_id,
    current_durability,
    max_durability
FROM updated_modules
ORDER BY module_id;
"""

def build_overrepair_sql(character_actor_id, inventory_id, durability_value):
    """
    Build SQL to overrepair every durability-bearing item in one inventory.

    Some unique tools/weapons have CurrentDurability but no MaxDurability key
    until we create it. CurrentDurability is still required so stackables and
    utility items without durability are not accidentally converted.
    """
    actor_id = int(character_actor_id)
    inv_id = int(inventory_id)
    durability = float(durability_value)

    return f"""
WITH settings AS (
    SELECT
        {actor_id}::bigint AS character_actor_id,
        {inv_id}::bigint AS target_inventory_id,
        {durability}::numeric AS durability_value
),
updated_items AS (
    UPDATE dune.items i
    SET stats =
        jsonb_set(
            jsonb_set(
                jsonb_set(
                    i.stats,
                    '{{FItemStackAndDurabilityStats,1,CurrentDurability}}',
                    to_jsonb(s.durability_value),
                    true
                ),
                '{{FItemStackAndDurabilityStats,1,DecayedMaxDurability}}',
                to_jsonb(s.durability_value),
                true
            ),
            '{{FItemStackAndDurabilityStats,1,MaxDurability}}',
            to_jsonb(s.durability_value),
            true
        )
    FROM dune.inventories inv
    CROSS JOIN settings s
    WHERE i.inventory_id = inv.id
      AND inv.id = s.target_inventory_id
      AND inv.actor_id = s.character_actor_id
      AND i.stats #> '{{FItemStackAndDurabilityStats,1,CurrentDurability}}' IS NOT NULL
    RETURNING
        i.inventory_id,
        i.id AS item_id,
        i.template_id,
        i.position_index,
        i.quality_level,
        i.stats #> '{{FItemStackAndDurabilityStats,1,CurrentDurability}}'
            AS current_durability,
        i.stats #> '{{FItemStackAndDurabilityStats,1,DecayedMaxDurability}}'
            AS decayed_max_durability,
        i.stats #> '{{FItemStackAndDurabilityStats,1,MaxDurability}}'
            AS max_durability
)
SELECT
    inventory_id,
    item_id,
    template_id,
    position_index,
    quality_level,
    current_durability,
    decayed_max_durability,
    max_durability
FROM updated_items
ORDER BY inventory_id, position_index, item_id;
"""


def build_overrepair_all_inventories_sql(character_actor_id, durability_value):
    """
    Build SQL to overrepair all durability-bearing items owned by one character.

    This is used for VIP self-repair so equipped/hotbar inventories and main
    bag inventories are covered together. CurrentDurability remains required;
    items without current durability are intentionally ignored.
    """
    actor_id = int(character_actor_id)
    durability = float(durability_value)

    return f"""
WITH settings AS (
    SELECT
        {actor_id}::bigint AS character_actor_id,
        {durability}::numeric AS durability_value
),
updated_items AS (
    UPDATE dune.items i
    SET stats =
        jsonb_set(
            jsonb_set(
                jsonb_set(
                    i.stats,
                    '{{FItemStackAndDurabilityStats,1,CurrentDurability}}',
                    to_jsonb(s.durability_value),
                    true
                ),
                '{{FItemStackAndDurabilityStats,1,DecayedMaxDurability}}',
                to_jsonb(s.durability_value),
                true
            ),
            '{{FItemStackAndDurabilityStats,1,MaxDurability}}',
            to_jsonb(s.durability_value),
            true
        )
    FROM dune.inventories inv
    CROSS JOIN settings s
    WHERE i.inventory_id = inv.id
      AND inv.actor_id = s.character_actor_id
      AND i.stats #> '{{FItemStackAndDurabilityStats,1,CurrentDurability}}' IS NOT NULL
    RETURNING
        i.inventory_id,
        i.id AS item_id,
        i.template_id,
        i.position_index,
        i.quality_level,
        i.stats #> '{{FItemStackAndDurabilityStats,1,CurrentDurability}}'
            AS current_durability,
        i.stats #> '{{FItemStackAndDurabilityStats,1,DecayedMaxDurability}}'
            AS decayed_max_durability,
        i.stats #> '{{FItemStackAndDurabilityStats,1,MaxDurability}}'
            AS max_durability
)
SELECT
    inventory_id,
    item_id,
    template_id,
    position_index,
    quality_level,
    current_durability,
    decayed_max_durability,
    max_durability
FROM updated_items
ORDER BY inventory_id, position_index, item_id;
"""


def build_overrepair_item_sql(character_actor_id, inventory_id, item_row_id, durability_value):
    """
    Build admin-only SQL for repairing exactly one item row.

    The character actor and inventory checks are intentionally kept in the
    UPDATE, not just in the browser picker, so a stale or hand-edited form
    cannot overrepair an item belonging to another character.

    Some uniques expose CurrentDurability while MaxDurability is missing. This
    still treats the item as repairable and creates the missing max keys, but
    CurrentDurability remains required.
    """
    actor_id = int(character_actor_id)
    inv_id = int(inventory_id)
    row_id = int(item_row_id)
    durability = float(durability_value)

    return f"""
WITH settings AS (
    SELECT
        {actor_id}::bigint AS character_actor_id,
        {inv_id}::bigint AS target_inventory_id,
        {row_id}::bigint AS target_item_row_id,
        {durability}::numeric AS durability_value
),
updated_items AS (
    UPDATE dune.items i
    SET stats =
        jsonb_set(
            jsonb_set(
                jsonb_set(
                    i.stats,
                    '{{FItemStackAndDurabilityStats,1,CurrentDurability}}',
                    to_jsonb(s.durability_value),
                    true
                ),
                '{{FItemStackAndDurabilityStats,1,DecayedMaxDurability}}',
                to_jsonb(s.durability_value),
                true
            ),
            '{{FItemStackAndDurabilityStats,1,MaxDurability}}',
            to_jsonb(s.durability_value),
            true
        )
    FROM dune.inventories inv
    CROSS JOIN settings s
    WHERE i.inventory_id = inv.id
      AND i.id = s.target_item_row_id
      AND inv.id = s.target_inventory_id
      AND inv.actor_id = s.character_actor_id
      AND i.stats #> '{{FItemStackAndDurabilityStats,1,CurrentDurability}}' IS NOT NULL
    RETURNING
        i.inventory_id,
        i.id AS item_id,
        i.template_id,
        i.position_index,
        i.quality_level,
        i.stats #> '{{FItemStackAndDurabilityStats,1,CurrentDurability}}'
            AS current_durability,
        i.stats #> '{{FItemStackAndDurabilityStats,1,DecayedMaxDurability}}'
            AS decayed_max_durability,
        i.stats #> '{{FItemStackAndDurabilityStats,1,MaxDurability}}'
            AS max_durability
)
SELECT
    inventory_id,
    item_id,
    template_id,
    position_index,
    quality_level,
    current_durability,
    decayed_max_durability,
    max_durability
FROM updated_items
ORDER BY inventory_id, position_index, item_id;
"""


def build_set_research_points_sql(character_actor_id, research_points):
    """
    Build admin-only SQL to set one character's available research points.

    This is intentionally a fresh implementation inspired by the provided
    reference query. The browser supplies only the character actor id and the
    desired point value; validation is done against dune.player_state before
    the actor JSON is updated.
    """
    actor_id = int(character_actor_id)
    points = int(research_points)

    if points < 0:
        raise ValueError("research points cannot be negative")

    return f"""
WITH settings AS (
    SELECT
        {actor_id}::bigint AS character_actor_id,
        {points}::integer AS research_points
),
selected_player AS (
    SELECT
        ps.character_name,
        ps.player_pawn_id AS character_actor_id,
        ps.online_status,
        ps.life_state
    FROM dune.player_state ps
    JOIN settings s
        ON s.character_actor_id = ps.player_pawn_id
),
original_value AS (
    SELECT
        a.id AS character_actor_id,
        a.class AS actor_class,
        a.properties #> '{{TechKnowledgePlayerComponent,m_TechKnowledgePoints}}'
            AS before_research_points
    FROM dune.actors a
    JOIN selected_player sp
        ON sp.character_actor_id = a.id
),
updated_actor AS (
    UPDATE dune.actors a
    SET properties = jsonb_set(
        a.properties,
        '{{TechKnowledgePlayerComponent,m_TechKnowledgePoints}}',
        to_jsonb(s.research_points),
        true
    )
    FROM settings s
    JOIN selected_player sp
        ON sp.character_actor_id = s.character_actor_id
    WHERE a.id = sp.character_actor_id
    RETURNING
        a.id AS character_actor_id,
        a.properties #> '{{TechKnowledgePlayerComponent,m_TechKnowledgePoints}}'
            AS after_research_points
)
SELECT
    sp.character_name,
    sp.character_actor_id,
    sp.online_status,
    sp.life_state,
    ov.actor_class,
    ov.before_research_points,
    ua.after_research_points
FROM selected_player sp
JOIN original_value ov
    ON ov.character_actor_id = sp.character_actor_id
JOIN updated_actor ua
    ON ua.character_actor_id = sp.character_actor_id;
"""


def build_give_specialization_xp_sql(character_actor_id, track_type, xp_amount):
    """
    Build admin-only SQL to add XP to one specialization track.

    This follows the table/function behavior observed in IceHunter's
    MIT-licensed dune-admin project, but keeps our implementation narrow:
    selected track only, additive XP only, and capped to SPECIALIZATION_MAX_XP.
    The specialization_tracks.player_id value is the pawn actor id, which is
    exposed in this panel as Character Actor ID.
    """
    actor_id = int(character_actor_id)
    amount = int(xp_amount)
    track = str(track_type).strip()

    if track not in SPECIALIZATION_XP_TRACKS:
        raise ValueError("unsupported XP track")
    if amount <= 0:
        raise ValueError("XP amount must be greater than zero")

    safe_track = track.replace("'", "''")

    return f"""
WITH settings AS (
    SELECT
        {actor_id}::bigint AS character_actor_id,
        '{safe_track}'::dune.specializationtracktype AS track_type,
        LEAST({amount}::integer, {SPECIALIZATION_MAX_XP}::integer) AS xp_delta,
        {SPECIALIZATION_MAX_XP}::integer AS max_xp
),
selected_player AS (
    SELECT
        ps.character_name,
        ps.player_pawn_id AS character_actor_id,
        ps.player_controller_id,
        ps.online_status,
        ps.life_state
    FROM dune.player_state ps
    JOIN settings s
        ON s.character_actor_id = ps.player_pawn_id
),
original_value AS (
    SELECT
        sp.character_name,
        sp.character_actor_id,
        sp.player_controller_id,
        sp.online_status,
        sp.life_state,
        s.track_type,
        COALESCE(st.xp_amount, 0) AS before_xp,
        COALESCE(st.level, 0) AS before_level
    FROM selected_player sp
    CROSS JOIN settings s
    LEFT JOIN dune.specialization_tracks st
        ON st.player_id = sp.character_actor_id
       AND st.track_type = s.track_type
),
upserted_track AS (
    INSERT INTO dune.specialization_tracks (player_id, track_type, xp_amount, level)
    SELECT
        s.character_actor_id,
        s.track_type,
        s.xp_delta,
        ov.before_level
    FROM settings s
    JOIN original_value ov
        ON ov.character_actor_id = s.character_actor_id
    ON CONFLICT (player_id, track_type)
    DO UPDATE SET xp_amount = GREATEST(LEAST(
        dune.specialization_tracks.xp_amount + EXCLUDED.xp_amount,
        (SELECT max_xp FROM settings)
    ), 0)
    RETURNING
        player_id,
        track_type,
        xp_amount AS after_xp,
        level AS after_level
)
SELECT
    ov.character_name,
    ov.character_actor_id,
    ov.player_controller_id,
    ov.online_status,
    ov.life_state,
    ov.track_type::text,
    ov.before_xp,
    ut.after_xp,
    (ut.after_xp - ov.before_xp) AS xp_added,
    ov.before_level,
    ut.after_level
FROM original_value ov
JOIN upserted_track ut
    ON ut.player_id = ov.character_actor_id
   AND ut.track_type = ov.track_type;
"""


def build_max_specialization_sql(character_actor_id):
    """
    Build admin-only SQL to max every specialization track and grant keystones.

    This uses pawn actor id for specialization state, matching the public query
    screenshots supplied by the project owner. Keystones are granted from
    dune.specialization_keystones_map so future game-data additions are picked
    up without maintaining a separate hard-coded list.
    """
    actor_id = int(character_actor_id)

    tracks_sql = sql_text_array(SPECIALIZATION_XP_TRACKS).replace("::text[]", "::dune.specializationtracktype[]")

    return f"""
BEGIN;
WITH selected_player AS (
    SELECT
        ps.character_name,
        ps.player_pawn_id AS character_actor_id,
        ps.player_controller_id,
        ps.online_status,
        ps.life_state
    FROM dune.player_state ps
    WHERE ps.player_pawn_id = {actor_id}::bigint
),
upserted_tracks AS (
    INSERT INTO dune.specialization_tracks (player_id, track_type, xp_amount, level)
    SELECT
        sp.character_actor_id,
        unnest({tracks_sql}),
        {SPECIALIZATION_MAX_XP}::integer,
        100::integer
    FROM selected_player sp
    ON CONFLICT (player_id, track_type)
    DO UPDATE SET
        xp_amount = {SPECIALIZATION_MAX_XP}::integer,
        level = 100::integer
    RETURNING player_id, track_type
),
upserted_keystones AS (
    INSERT INTO dune.purchased_specialization_keystones (player_id, keystone_id)
    SELECT
        sp.character_actor_id,
        skm.id
    FROM selected_player sp
    CROSS JOIN dune.specialization_keystones_map skm
    ON CONFLICT DO NOTHING
    RETURNING player_id, keystone_id
)
SELECT
    sp.character_name,
    sp.character_actor_id,
    sp.player_controller_id,
    sp.online_status,
    sp.life_state,
    COUNT(DISTINCT ut.track_type) AS tracks_maxed,
    (SELECT COUNT(*) FROM upserted_keystones) AS keystones_granted,
    {SPECIALIZATION_MAX_XP}::integer AS xp_amount,
    100::integer AS level
FROM selected_player sp
LEFT JOIN upserted_tracks ut
    ON ut.player_id = sp.character_actor_id
GROUP BY
    sp.character_name,
    sp.character_actor_id,
    sp.player_controller_id,
    sp.online_status,
    sp.life_state;
COMMIT;
"""


def build_grant_all_specialization_tracks_sql(character_actor_id):
    """
    Build admin-only SQL to create every specialization track row without maxing.

    This is intentionally gentle for testing: it inserts missing track rows at
    0 XP / level 0 and leaves existing track progress untouched. It does not
    grant keystones.
    """
    actor_id = int(character_actor_id)
    tracks_sql = sql_text_array(SPECIALIZATION_XP_TRACKS).replace("::text[]", "::dune.specializationtracktype[]")

    return f"""
WITH selected_player AS (
    SELECT
        ps.character_name,
        ps.player_pawn_id AS character_actor_id,
        ps.player_controller_id,
        ps.online_status,
        ps.life_state
    FROM dune.player_state ps
    WHERE ps.player_pawn_id = {actor_id}::bigint
),
inserted_tracks AS (
    INSERT INTO dune.specialization_tracks (player_id, track_type, xp_amount, level)
    SELECT
        sp.character_actor_id,
        unnest({tracks_sql}),
        0::integer,
        0::integer
    FROM selected_player sp
    ON CONFLICT (player_id, track_type) DO NOTHING
    RETURNING player_id, track_type
)
SELECT
    sp.character_name,
    sp.character_actor_id,
    sp.player_controller_id,
    sp.online_status,
    sp.life_state,
    COUNT(it.track_type) AS tracks_created,
    {len(SPECIALIZATION_XP_TRACKS)}::integer AS expected_track_count,
    'existing track rows were left unchanged; keystones were not granted' AS note
FROM selected_player sp
LEFT JOIN inserted_tracks it
    ON it.player_id = sp.character_actor_id
GROUP BY
    sp.character_name,
    sp.character_actor_id,
    sp.player_controller_id,
    sp.online_status,
    sp.life_state;
"""


def sql_literal(value):
    """Quote a local string for SQL generated from trusted panel controls."""
    return "'" + str(value).replace("'", "''") + "'"


def sql_text_array(values):
    """Build a PostgreSQL text[] literal from a trusted local list."""
    return "ARRAY[" + ", ".join(sql_literal(value) for value in values) + "]::text[]"


def progression_preset_by_id(preset_id):
    for preset in PROGRESSION_PRESETS:
        if preset["id"] == preset_id:
            return preset
    return None


def build_reset_specialization_sql(character_actor_id, track_type):
    """
    Build admin-only SQL to reset specialization state.

    Resetting one track deletes that track's XP row. Resetting "all" deletes
    specialization tracks and purchased keystones for the pawn actor id.
    """
    actor_id = int(character_actor_id)
    track = str(track_type).strip()

    if track.lower() == "all":
        return f"""
BEGIN;
WITH deleted_tracks AS (
    DELETE FROM dune.specialization_tracks
    WHERE player_id = {actor_id}::bigint
    RETURNING player_id
),
deleted_keystones AS (
    DELETE FROM dune.purchased_specialization_keystones
    WHERE player_id = {actor_id}::bigint
    RETURNING player_id
)
SELECT
    'reset_all' AS status,
    {actor_id}::bigint AS character_actor_id,
    (SELECT COUNT(*) FROM deleted_tracks) AS track_rows_deleted,
    (SELECT COUNT(*) FROM deleted_keystones) AS keystones_deleted;
COMMIT;
"""

    if track not in SPECIALIZATION_XP_TRACKS:
        raise ValueError("unsupported XP track")

    safe_track = track.replace("'", "''")

    return f"""
WITH deleted AS (
    DELETE FROM dune.specialization_tracks
    WHERE player_id = {actor_id}::bigint
      AND track_type::text = '{safe_track}'
    RETURNING player_id, track_type::text AS track_type, xp_amount, level
)
SELECT
    {actor_id}::bigint AS character_actor_id,
    '{safe_track}' AS reset_scope,
    COUNT(*) AS rows_deleted
FROM deleted;
"""


# Class progression presets are account-level tag bundles discovered from live
# before/after testing. Keep this list deliberately explicit so server owners
# can audit or adjust the exact tags before exposing an unlock to admins.
CLASS_PROGRESSION_PRESETS = {
    "planetologist_base": {
        "label": "Unlock Planetologist",
        "tags": [
            "DialogueFlags.Contracts.PlanetologistT1Complete",
            "Contract.Target.Dialogue.Planetologist1.Contract1.Delivery",
            "Contract.Tracking.Completed.Trainer_Planetologist1_01",
        ],
    },
    "trooper_base": {
        "label": "Unlock Trooper",
        "tags": [
            "DialogueFlags.Contracts.TrooperT1Complete",
            "Contract.Target.Dialogue.Ghavouri.Contract1Report",
            "Contract.Tracking.Completed.Trainer_Trooper1_01A",
        ],
    },
    "bene_gesserit_advanced": {
        "label": "Unlock Bene Gesserit Advanced (Level 2 Skills)",
        "tags": [
            "Contract.Tracking.Completed.AdvancedBeneGesseritTrainer.Contract1",
            "DunipediaFlags.StoneSentinel",
        ],
    },
}


def has_developer_access():
    """Return True only after an admin opens the hidden developer panel key gate."""
    return is_admin() and bool(session.get("developer_unlocked"))


def build_class_progression_sql(character_actor_id, preset_id, action="apply"):
    """
    Build developer-only SQL to apply or remove one class progression tag bundle.

    These presets do not grant XP, specialization rows, or items. They only add
    the account-level player_tags rows we have captured from live progression.
    The remove action deletes the same observed tags so broken presets can be
    cleaned off a test account after they block normal class pickup.
    """
    actor_id = int(character_actor_id)
    preset_key = str(preset_id or "").strip()
    preset = CLASS_PROGRESSION_PRESETS.get(preset_key)
    if not preset:
        raise ValueError("unknown class progression preset")

    action_key = str(action or "apply").strip().lower()
    if action_key not in ("apply", "remove"):
        raise ValueError("unknown class progression action")

    tags = preset["tags"]
    tag_values_sql = ",\n            ".join(f"({sql_literal(tag)})" for tag in tags)
    tags_csv = ", ".join(tags)
    mutation_cte = """
mutated AS (
    INSERT INTO dune.player_tags (account_id, tag)
    SELECT
        sp.account_id,
        et.tag_value
    FROM selected_player sp
    CROSS JOIN expected_tags et
    WHERE NOT EXISTS (
        SELECT 1
        FROM dune.player_tags existing
        WHERE existing.account_id = sp.account_id
          AND existing.tag = et.tag_value
    )
    ON CONFLICT DO NOTHING
    RETURNING account_id, tag
)
"""
    if action_key == "remove":
        mutation_cte = """
mutated AS (
    DELETE FROM dune.player_tags pt
    USING selected_player sp, expected_tags et
    WHERE pt.account_id = sp.account_id
      AND pt.tag = et.tag_value
    RETURNING pt.account_id, pt.tag
)
"""

    return f"""
WITH selected_player AS (
    SELECT
        ps.character_name,
        ps.player_pawn_id AS character_actor_id,
        ps.account_id,
        ps.online_status,
        ps.life_state
    FROM dune.player_state ps
    WHERE ps.player_pawn_id = {actor_id}::bigint
),
expected_tags AS (
    SELECT tag_value
    FROM (
        VALUES
            {tag_values_sql}
    ) AS tags(tag_value)
),
{mutation_cte},
present_after AS (
    SELECT
        sp.account_id,
        et.tag_value AS tag
    FROM selected_player sp
    CROSS JOIN expected_tags et
    JOIN dune.player_tags pt
      ON pt.account_id = sp.account_id
     AND pt.tag = et.tag_value
),
missing_after AS (
    SELECT
        sp.account_id,
        et.tag_value AS tag
    FROM selected_player sp
    CROSS JOIN expected_tags et
    WHERE NOT EXISTS (
        SELECT 1
        FROM dune.player_tags pt
        WHERE pt.account_id = sp.account_id
          AND pt.tag = et.tag_value
    )
)
SELECT
    sp.character_name,
    sp.character_actor_id,
    sp.account_id,
    sp.online_status,
    sp.life_state,
    {sql_literal(preset_key)} AS preset_id,
    {sql_literal(preset["label"])} AS preset_label,
    {sql_literal(action_key)} AS preset_action,
    {sql_literal(tags_csv)} AS preset_tags,
    (SELECT COUNT(*) FROM mutated) AS tags_changed,
    COALESCE((SELECT string_agg(tag, ', ' ORDER BY tag) FROM mutated), '') AS changed_tags,
    (SELECT COUNT(*) FROM present_after) AS tags_present_after,
    COALESCE((SELECT string_agg(tag, ', ' ORDER BY tag) FROM present_after), '') AS present_tags_after,
    (SELECT COUNT(*) FROM missing_after) AS tags_missing_after,
    COALESCE((SELECT string_agg(tag, ', ' ORDER BY tag) FROM missing_after), '') AS missing_tags_after
FROM selected_player sp
"""


def build_class_progression_unlock_sql(character_actor_id, preset_id):
    """Backward-compatible wrapper for the apply action."""
    return build_class_progression_sql(character_actor_id, preset_id, "apply")


def build_unlock_advanced_bene_gesserit_sql(character_actor_id):
    """Backward-compatible wrapper for older route callers."""
    return build_class_progression_unlock_sql(character_actor_id, "bene_gesserit_advanced")


def build_progression_preset_sql(fls_id, preset_id, action):
    """
    Build admin-only SQL to apply or reset a curated journey-node preset.

    This intentionally uses journey_story_node state only. IceHunter's richer
    tool also applies tag side effects from game-data catalogs; we do not ship
    that catalog here, so the UI labels this as experimental and reversible.
    """
    preset = progression_preset_by_id(preset_id)
    if not preset:
        raise ValueError("unknown progression preset")

    requested_action = str(action).strip().lower()
    if requested_action not in ("apply", "reset"):
        raise ValueError("unsupported progression action")

    safe_fls = sql_literal(str(fls_id).strip())
    nodes_sql = sql_text_array(preset["nodes"])
    safe_preset_id = sql_literal(preset["id"])
    safe_preset_name = sql_literal(preset["name"])

    if requested_action == "apply":
        # Complete root nodes plus existing child nodes one row at a time. A
        # single broad UPDATE can collide with journey_story_node triggers, and
        # the game's bulk routine only touches the root ids we pass in.
        return f"""
BEGIN;
DO $$
DECLARE
    v_fls_id text := {safe_fls}::text;
    v_root_nodes text[] := {nodes_sql};
    v_account_id bigint;
    v_node text;
    v_rows integer := 0;
BEGIN
    IF NOT dune.is_player_offline(v_fls_id) THEN
        RAISE EXCEPTION 'Cannot update progression because the player is online.';
    END IF;

    SELECT id INTO v_account_id
    FROM dune.accounts
    WHERE "user" = v_fls_id;

    IF v_account_id IS NULL THEN
        RAISE EXCEPTION 'No account found for FLS id %', v_fls_id;
    END IF;

    CREATE TEMP TABLE IF NOT EXISTS eda_progression_result (
        action text,
        preset_id text,
        preset_name text,
        root_nodes integer,
        touched_rows integer,
        note text
    ) ON COMMIT DROP;
    TRUNCATE eda_progression_result;

    FOR v_node IN
        SELECT DISTINCT node_id
        FROM (
            SELECT unnest(v_root_nodes) AS node_id
            UNION
            SELECT jsn.story_node_id AS node_id
            FROM dune.journey_story_node jsn
            WHERE jsn.account_id = v_account_id
              AND EXISTS (
                  SELECT 1
                  FROM unnest(v_root_nodes) AS root_node
                  WHERE jsn.story_node_id = root_node
                     OR jsn.story_node_id LIKE root_node || '.%'
              )
        ) target_nodes
        ORDER BY node_id
    LOOP
        UPDATE dune.journey_story_node
        SET
            complete_condition_state = 'true'::jsonb,
            reveal_condition_state = 'true'::jsonb
        WHERE account_id = v_account_id
          AND story_node_id = v_node;

        IF NOT FOUND THEN
            INSERT INTO dune.journey_story_node (
                account_id,
                story_node_id,
                override_reward_block,
                has_pending_reward,
                complete_condition_state,
                reveal_condition_state,
                fail_condition_state,
                metadata_state,
                reset_group
            )
            VALUES (
                v_account_id,
                v_node,
                false,
                false,
                'true'::jsonb,
                'true'::jsonb,
                '{{}}'::jsonb,
                '{{}}'::jsonb,
                'Default'::dune.JourneyStoryResetGroup
            )
            ON CONFLICT ON CONSTRAINT journey_story_node_pkey
            DO UPDATE SET
                complete_condition_state = EXCLUDED.complete_condition_state,
                reveal_condition_state = EXCLUDED.reveal_condition_state,
                fail_condition_state = EXCLUDED.fail_condition_state,
                metadata_state = EXCLUDED.metadata_state;
        END IF;

        v_rows := v_rows + 1;
    END LOOP;

    INSERT INTO eda_progression_result
    VALUES (
        'applied',
        {safe_preset_id}::text,
        {safe_preset_name}::text,
        array_length(v_root_nodes, 1),
        v_rows,
        'Completed root nodes plus existing child rows one at a time. Relog after applying.'
    );
END $$;
SELECT
    action,
    preset_id,
    preset_name,
    root_nodes,
    touched_rows,
    note
FROM eda_progression_result;
COMMIT;
"""

    return f"""
BEGIN;
DO $$
DECLARE
    v_fls_id text := {safe_fls}::text;
    v_root_nodes text[] := {nodes_sql};
    v_account_id bigint;
    v_node text;
    v_rows integer := 0;
BEGIN
    IF NOT dune.is_player_offline(v_fls_id) THEN
        RAISE EXCEPTION 'Cannot reset progression because the player is online.';
    END IF;

    SELECT id INTO v_account_id
    FROM dune.accounts
    WHERE "user" = v_fls_id;

    IF v_account_id IS NULL THEN
        RAISE EXCEPTION 'No account found for FLS id %', v_fls_id;
    END IF;

    CREATE TEMP TABLE IF NOT EXISTS eda_progression_result (
        action text,
        preset_id text,
        preset_name text,
        root_nodes integer,
        touched_rows integer,
        note text
    ) ON COMMIT DROP;
    TRUNCATE eda_progression_result;

    FOR v_node IN
        SELECT DISTINCT jsn.story_node_id
        FROM dune.journey_story_node jsn
        WHERE jsn.account_id = v_account_id
          AND EXISTS (
              SELECT 1
              FROM unnest(v_root_nodes) AS root_node
              WHERE jsn.story_node_id = root_node
                 OR jsn.story_node_id LIKE root_node || '.%'
          )
        ORDER BY jsn.story_node_id
    LOOP
        UPDATE dune.journey_story_node
        SET complete_condition_state = '{{}}'::jsonb
        WHERE account_id = v_account_id
          AND story_node_id = v_node;

        DELETE FROM dune.journey_story_node_cooldown
        WHERE account_id = v_account_id
          AND story_node_id = v_node;

        v_rows := v_rows + 1;
    END LOOP;

    INSERT INTO eda_progression_result
    VALUES (
        'reset',
        {safe_preset_id}::text,
        {safe_preset_name}::text,
        array_length(v_root_nodes, 1),
        v_rows,
        'Reset root nodes plus existing child rows one at a time. Relog after resetting.'
    );
END $$;
SELECT
    action,
    preset_id,
    preset_name,
    root_nodes,
    touched_rows,
    note
FROM eda_progression_result;
COMMIT;
"""


def build_give_character_xp_sql(character_actor_id, xp_amount):
    """
    Build admin-only SQL to add character-level XP.

    Character XP is the displayed level pool on FLevelComponent.TotalXPEarned.
    When XP changes, the related total/unspent skill-point fields and research
    point/intel value are recalculated to match the new level. The XP curve and
    formulas are adapted from IceHunter's MIT-licensed dune-admin research.
    """
    actor_id = int(character_actor_id)
    amount = int(xp_amount)

    if amount <= 0:
        raise ValueError("XP amount must be greater than zero")

    return f"""
WITH settings AS (
    SELECT
        {actor_id}::bigint AS character_actor_id,
        LEAST({amount}::bigint, {CHARACTER_MAX_XP}::bigint) AS xp_delta,
        {CHARACTER_MAX_XP}::bigint AS max_xp
),
selected_player AS (
    SELECT
        ps.character_name,
        ps.player_pawn_id AS character_actor_id,
        ps.player_controller_id,
        ps.online_status,
        ps.life_state
    FROM dune.player_state ps
    JOIN settings s
        ON s.character_actor_id = ps.player_pawn_id
),
current_state AS (
    SELECT
        sp.character_name,
        sp.character_actor_id,
        sp.player_controller_id,
        sp.online_status,
        sp.life_state,
        fe.entity_id,
        COALESCE((fe.components #>> '{{FLevelComponent,1,TotalXPEarned}}')::bigint, 0) AS before_xp,
        COALESCE((fe.components #>> '{{FLevelComponent,1,TotalSkillPoints}}')::bigint, 0) AS before_total_skill_points,
        COALESCE((fe.components #>> '{{FLevelComponent,1,UnspentSkillPoints}}')::bigint, 0) AS before_unspent_skill_points,
        COALESCE((
            SELECT SUM((v->>'SkillPointsSpent')::int)
            FROM jsonb_each(fe.components->'FLevelComponent'->1->'ModuleData') AS kv(k, v)
            WHERE k != format(
                '(TagName="%s")',
                fe.components->'FLevelComponent'->1->'StarterSkillTreeTag'->>'TagName'
            )
        ), 0) AS spent_skill_points
    FROM selected_player sp
    JOIN dune.actor_fgl_entities afe
        ON afe.actor_id = sp.character_actor_id
       AND afe.slot_name = 'DuneCharacter'
    JOIN dune.fgl_entities fe
        ON fe.entity_id = afe.entity_id
),
keystone_bonus AS (
    SELECT
        cs.character_actor_id,
        COALESCE(SUM(
            CASE
                WHEN psk.keystone_id IN (1,3,6,9,12,15,18,21,24,27) THEN 3
                WHEN psk.keystone_id = 30 THEN 5
                WHEN psk.keystone_id BETWEEN 1 AND 29 THEN 1
                ELSE 0
            END
        ), 0)::bigint AS bonus_skill_points
    FROM current_state cs
    LEFT JOIN dune.purchased_specialization_keystones psk
        ON psk.player_id = cs.character_actor_id
    GROUP BY cs.character_actor_id
),
computed AS (
    SELECT
        cs.*,
        kb.bonus_skill_points,
        LEAST(cs.before_xp + s.xp_delta, s.max_xp) AS after_xp
    FROM current_state cs
    JOIN settings s
        ON s.character_actor_id = cs.character_actor_id
    JOIN keystone_bonus kb
        ON kb.character_actor_id = cs.character_actor_id
),
leveled AS (
    SELECT
        c.*,
        COALESCE((
            SELECT MAX(level_value)
            FROM (VALUES
                (0,0),(1,40),(2,215),(3,440),(4,740),(5,1240),(6,1790),(7,2390),(8,2990),(9,3590),(10,4190),
                (11,4790),(12,5390),(13,5990),(14,6590),(15,7190),(16,7790),(17,8390),(18,8990),(19,9590),(20,10190),
                (21,10790),(22,11390),(23,11990),(24,12590),(25,13190),(26,13790),(27,14390),(28,14990),(29,15590),(30,16190),
                (31,16790),(32,17390),(33,17990),(34,18590),(35,19190),(36,19790),(37,20390),(38,20990),(39,21590),(40,22190),
                (41,22790),(42,23390),(43,23990),(44,24590),(45,25190),(46,25790),(47,26390),(48,26990),(49,27590),(50,28190),
                (51,28790),(52,29390),(53,29990),(54,30590),(55,31190),(56,31790),(57,32390),(58,32990),(59,33590),(60,34190),
                (61,34790),(62,35390),(63,35990),(64,36590),(65,37190),(66,37790),(67,38390),(68,38990),(69,39590),(70,40190),
                (71,40790),(72,41390),(73,41990),(74,42590),(75,43190),(76,43790),(77,44390),(78,44990),(79,45590),(80,46190),
                (81,46790),(82,47390),(83,47990),(84,48590),(85,49190),(86,49790),(87,50390),(88,50990),(89,51590),(90,52190),
                (91,52790),(92,53390),(93,53990),(94,54590),(95,55190),(96,55790),(97,56390),(98,56990),(99,57590),(100,58190),
                (101,58840),(102,59490),(103,60140),(104,60790),(105,61440),(106,62090),(107,62740),(108,63390),(109,64040),(110,64690),
                (111,65340),(112,65990),(113,66640),(114,67290),(115,67940),(116,68590),(117,69240),(118,69890),(119,70540),(120,71190),
                (121,71840),(122,72490),(123,73140),(124,73790),(125,74440),(126,75090),(127,75740),(128,76391),(129,77044),(130,77699),
                (131,78357),(132,79018),(133,79683),(134,80353),(135,81030),(136,81714),(137,82407),(138,83110),(139,83825),(140,84554),
                (141,85298),(142,86060),(143,86842),(144,87646),(145,88475),(146,89332),(147,90220),(148,91141),(149,92100),(150,93099),
                (151,94143),(152,95235),(153,96380),(154,97582),(155,98845),(156,100175),(157,101576),(158,103054),(159,104614),(160,106263),
                (161,108006),(162,109849),(163,111799),(164,113862),(165,116046),(166,118358),(167,120806),(168,123397),(169,126139),(170,129041),
                (171,132112),(172,135360),(173,138795),(174,142426),(175,146263),(176,150316),(177,154596),(178,159114),(179,163880),(180,168906),
                (181,174203),(182,179784),(183,185661),(184,191846),(185,198353),(186,205195),(187,212385),(188,219938),(189,227868),(190,236190),
                (191,244918),(192,254069),(193,263657),(194,273700),(195,284213),(196,295214),(197,306719),(198,318746),(199,331314),(200,344440)
            ) AS curve(level_value, xp_required)
            WHERE xp_required <= c.after_xp
        ), 0)::bigint AS after_level
    FROM computed c
),
final_values AS (
    SELECT
        l.*,
        (l.after_level + l.bonus_skill_points) AS after_total_skill_points,
        GREATEST((l.after_level + l.bonus_skill_points) - l.spent_skill_points - 1, 0)::bigint AS after_unspent_skill_points,
        CASE
            WHEN l.after_level <= 0 THEN 0
            WHEN l.after_level = 1 THEN 4
            WHEN l.after_level <= 3 THEN 4 + (l.after_level - 1) * 2
            WHEN l.after_level <= 15 THEN 8 + (l.after_level - 3) * 3
            WHEN l.after_level <= 30 THEN 44 + (l.after_level - 15) * 5
            WHEN l.after_level <= 50 THEN 119 + (l.after_level - 30) * 10
            WHEN l.after_level <= 69 THEN 319 + (l.after_level - 50) * 20
            WHEN l.after_level <= 85 THEN 699 + (l.after_level - 69) * 30
            WHEN l.after_level <= 125 THEN 1179 + (l.after_level - 85) * 40
            ELSE 2779
        END::bigint AS after_research_points
    FROM leveled l
),
updated_fgl AS (
    UPDATE dune.fgl_entities fe
    SET components = jsonb_set(
        jsonb_set(
            jsonb_set(
                fe.components,
                '{{FLevelComponent,1,TotalXPEarned}}',
                to_jsonb(fv.after_xp),
                true
            ),
            '{{FLevelComponent,1,TotalSkillPoints}}',
            to_jsonb(fv.after_total_skill_points),
            true
        ),
        '{{FLevelComponent,1,UnspentSkillPoints}}',
        to_jsonb(fv.after_unspent_skill_points),
        true
    )
    FROM final_values fv
    WHERE fe.entity_id = fv.entity_id
    RETURNING fe.entity_id
),
updated_actor AS (
    UPDATE dune.actors a
    SET properties = jsonb_set(
        a.properties,
        '{{TechKnowledgePlayerComponent,m_TechKnowledgePoints}}',
        to_jsonb(fv.after_research_points),
        true
    )
    FROM final_values fv
    WHERE a.id = fv.character_actor_id
    RETURNING a.id
)
SELECT
    fv.character_name,
    fv.character_actor_id,
    fv.online_status,
    fv.life_state,
    fv.before_xp,
    fv.after_xp,
    (fv.after_xp - fv.before_xp) AS xp_added,
    fv.after_level,
    fv.before_total_skill_points,
    fv.after_total_skill_points,
    fv.before_unspent_skill_points,
    fv.after_unspent_skill_points,
    fv.spent_skill_points,
    fv.bonus_skill_points,
    fv.after_research_points,
    CASE WHEN fv.after_xp >= (SELECT max_xp FROM settings) THEN true ELSE false END AS xp_capped
FROM final_values fv
JOIN updated_fgl uf
    ON uf.entity_id = fv.entity_id
JOIN updated_actor ua
    ON ua.id = fv.character_actor_id;
"""


def build_set_character_level_sql(character_actor_id, target_level):
    """
    Build admin-only SQL to set the displayed character level exactly.

    This reuses the character-XP recalculation SQL so skill points and research
    points stay aligned with the level curve. The resulting output still shows
    the before/after XP delta, which may be negative when lowering a level.
    """
    level = int(target_level)
    if level not in CHARACTER_LEVEL_XP or level <= 0:
        raise ValueError("target level must be between 1 and 200")

    target_xp = CHARACTER_LEVEL_XP[level]
    sql = build_give_character_xp_sql(character_actor_id, target_xp)

    return sql.replace(
        "LEAST(cs.before_xp + s.xp_delta, s.max_xp) AS after_xp",
        f"{target_xp}::bigint AS after_xp",
    )


def build_give_skill_points_sql(character_actor_id, skill_points):
    """
    Build admin-only SQL to add usable character skill points.

    Skill points live on the same DuneCharacter FGL entity as character XP.
    Adding to both TotalSkillPoints and UnspentSkillPoints gives the character
    new spendable points without disturbing points already spent in skill trees.
    """
    actor_id = int(character_actor_id)
    amount = int(skill_points)

    if amount <= 0:
        raise ValueError("skill point amount must be greater than zero")
    if amount > 1000:
        raise ValueError("skill point amount must be 1000 or lower")

    return f"""
WITH settings AS (
    SELECT
        {actor_id}::bigint AS character_actor_id,
        {amount}::bigint AS skill_points_delta
),
selected_player AS (
    SELECT
        ps.character_name,
        ps.player_pawn_id AS character_actor_id,
        ps.online_status,
        ps.life_state
    FROM dune.player_state ps
    JOIN settings s
        ON s.character_actor_id = ps.player_pawn_id
),
current_state AS (
    SELECT
        sp.character_name,
        sp.character_actor_id,
        sp.online_status,
        sp.life_state,
        fe.entity_id,
        COALESCE((fe.components #>> '{{FLevelComponent,1,TotalSkillPoints}}')::bigint, 0) AS before_total_skill_points,
        COALESCE((fe.components #>> '{{FLevelComponent,1,UnspentSkillPoints}}')::bigint, 0) AS before_unspent_skill_points
    FROM selected_player sp
    JOIN dune.actor_fgl_entities afe
        ON afe.actor_id = sp.character_actor_id
       AND afe.slot_name = 'DuneCharacter'
    JOIN dune.fgl_entities fe
        ON fe.entity_id = afe.entity_id
),
updated_fgl AS (
    UPDATE dune.fgl_entities fe
    SET components = jsonb_set(
        jsonb_set(
            fe.components,
            '{{FLevelComponent,1,TotalSkillPoints}}',
            to_jsonb(cs.before_total_skill_points + s.skill_points_delta),
            true
        ),
        '{{FLevelComponent,1,UnspentSkillPoints}}',
        to_jsonb(cs.before_unspent_skill_points + s.skill_points_delta),
        true
    )
    FROM current_state cs
    JOIN settings s
        ON s.character_actor_id = cs.character_actor_id
    WHERE fe.entity_id = cs.entity_id
    RETURNING fe.entity_id
)
SELECT
    cs.character_name,
    cs.character_actor_id,
    cs.online_status,
    cs.life_state,
    cs.before_total_skill_points,
    (cs.before_total_skill_points + s.skill_points_delta) AS after_total_skill_points,
    cs.before_unspent_skill_points,
    (cs.before_unspent_skill_points + s.skill_points_delta) AS after_unspent_skill_points,
    s.skill_points_delta AS skill_points_added
FROM current_state cs
JOIN settings s
    ON s.character_actor_id = cs.character_actor_id
JOIN updated_fgl uf
    ON uf.entity_id = cs.entity_id;
"""


def grant_item(player_id, item_id, quantity, durability="1.0"):
    cmd = [
        str(DUNE_SCRIPT),
        "admin",
        "grant-item-id",
        player_id,
        item_id,
        str(quantity),
        str(durability),
    ]
    return run_command(cmd, timeout=60)



# =========================================================
# LIVE MAP HELPERS
# =========================================================

def parse_transform(transform_value):
    """
    Parse Dune transform text.

    Observed format:
        ("(X,Y,Z)","(QX,QY,QZ,QW)")

    We only need X/Y/Z for map plotting.
    """
    if not transform_value:
        return None

    match = re.search(
        r'\(([0-9.eE+\-]+),([0-9.eE+\-]+),([0-9.eE+\-]+)\)',
        str(transform_value),
    )

    if not match:
        return None

    return {
        "x": float(match.group(1)),
        "y": float(match.group(2)),
        "z": float(match.group(3)),
    }


def parse_transform_rotation(transform_value):
    """
    Return the rotation tuple text from an actor transform.

    Observed format:
        ("(X,Y,Z)","(QX,QY,QZ,QW)")

    Vehicle relocation preserves rotation and only changes position.
    """
    if not transform_value:
        return None

    matches = re.findall(
        r'\(([0-9.eE+\-]+),([0-9.eE+\-]+),([0-9.eE+\-]+)(?:,([0-9.eE+\-]+))?\)',
        str(transform_value),
    )

    for match in matches:
        if match[3]:
            return f"({match[0]},{match[1]},{match[2]},{match[3]})"

    return None


def build_transform_literal(existing_transform, x, y, z):
    rotation = parse_transform_rotation(existing_transform)

    if not rotation:
        raise ValueError("could not parse existing actor rotation")

    return f'("({float(x)},{float(y)},{float(z)})","{rotation}")'


def teleportable_vehicle_class_where(column_name="class"):
    """
    Build the SQL allow-list for movable vehicle actor classes.

    column_name is kept as a small escape hatch because some queries use
    dune.actors directly while others alias it as "a". Only pass trusted local
    column names here; do not pass user input.
    """
    return " OR ".join(
        f"{column_name} ILIKE '%{pattern}%'"
        for pattern in TELEPORTABLE_VEHICLE_CLASS_PATTERNS
    )


def get_teleportable_vehicles():
    """
    Return confirmed vehicle actor rows for admin-only relocation.

    Ownership is not trusted yet. owner_account_id is exposed only to admins
    as a clue, not as an authorization boundary.
    """
    # The class allow-list is intentionally explicit. It currently covers the
    # confirmed actor classes for light/medium/transport ornithopters, sandbike,
    # buggy, treadwheel, and sandcrawler.
    vehicle_where = teleportable_vehicle_class_where("class")
    sql = f"""
    SELECT
        id,
        class,
        COALESCE(map, '') AS map,
        COALESCE(partition_id::text, '') AS partition_id,
        transform::text,
        COALESCE(owner_account_id::text, '') AS owner_account_id
    FROM dune.actors
    WHERE ({vehicle_where})
      AND transform IS NOT NULL
    ORDER BY id;
    """

    cmd = [
        "docker",
        "exec",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        "dune",
        "-d",
        "dune",
        "-At",
        "-F",
        "\t",
        "-c",
        sql,
    ]

    try:
        proc = run_process(
            cmd,
            timeout=15,
        )

        vehicles = []

        for line in proc.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 6:
                continue

            coords = parse_transform(parts[4]) or {}
            short_class = parts[1].split("/")[-1] if parts[1] else "Vehicle"

            vehicles.append(
                {
                    "actor_id": parts[0],
                    "class": parts[1],
                    "short_class": short_class,
                    "map": parts[2],
                    "partition_id": parts[3],
                    "transform": parts[4],
                    "owner_account_id": parts[5],
                    "x": coords.get("x", ""),
                    "y": coords.get("y", ""),
                    "z": coords.get("z", ""),
                }
            )

        return vehicles

    except Exception:
        return []


def get_teleportable_vehicle_actor(actor_id):
    actor_id = int(actor_id)
    vehicle_where = teleportable_vehicle_class_where("class")
    sql = f"""
    SELECT
        id,
        class,
        COALESCE(map, '') AS map,
        COALESCE(partition_id::text, '') AS partition_id,
        transform::text
    FROM dune.actors
    WHERE id = {actor_id}
      AND ({vehicle_where})
      AND transform IS NOT NULL
    LIMIT 1;
    """

    cmd = [
        "docker",
        "exec",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        "dune",
        "-d",
        "dune",
        "-At",
        "-F",
        "\t",
        "-c",
        sql,
    ]

    proc = run_process(
        cmd,
        timeout=15,
    )

    if proc.returncode != 0:
        raise ValueError(proc.stderr.strip() or "failed to query vehicle actor")

    line = proc.stdout.strip()
    if not line:
        raise ValueError("vehicle actor not found")

    parts = line.split("\t")
    if len(parts) < 5:
        raise ValueError("unexpected vehicle actor query result")

    return {
        "actor_id": parts[0],
        "class": parts[1],
        "map": parts[2],
        "partition_id": parts[3],
        "transform": parts[4],
    }


def build_vehicle_teleport_sql(actor_id, existing_transform, map_key, partition_id, x, y, z):
    actor_id = int(actor_id)
    partition_id = int(partition_id)
    x = float(x)
    y = float(y)
    z = float(z)
    safe_map_key = str(map_key).replace("'", "''")
    # Preserve the actor's existing rotation quaternion and replace only the
    # position vector. This avoids turning the vehicle while relocating it.
    safe_transform = build_transform_literal(existing_transform, x, y, z).replace("'", "''")
    vehicle_where = teleportable_vehicle_class_where("class")

    return f"""
UPDATE dune.actors
SET
    map = '{safe_map_key}',
    partition_id = {partition_id},
    transform = '{safe_transform}'
WHERE id = {actor_id}
  AND ({vehicle_where})
  AND transform IS NOT NULL
RETURNING
    id,
    class,
    map,
    partition_id,
    transform::text;
"""


def build_vehicle_delete_sql(actor_id):
    """
    Build admin-only cleanup SQL for a spawned/stuck vehicle actor.

    This removes the common vehicle rows observed in the self-host database:
    - dune.vehicle_modules rows keyed by vehicle_id
    - dune.vehicles row keyed by id
    - dune.actors row keyed by id

    The actor class allow-list is reused from vehicle teleport so this cannot
    delete arbitrary non-vehicle actors through the browser.
    """
    actor_id = int(actor_id)
    vehicle_where = teleportable_vehicle_class_where("a.class")

    return f"""
WITH target AS (
    SELECT
        a.id,
        a.class,
        COALESCE(a.map, '') AS map,
        COALESCE(a.partition_id::text, '') AS partition_id,
        a.transform::text AS transform
    FROM dune.actors a
    WHERE a.id = {actor_id}
      AND ({vehicle_where})
    LIMIT 1
),
deleted_modules AS (
    DELETE FROM dune.vehicle_modules vm
    USING target t
    WHERE vm.vehicle_id = t.id
    RETURNING vm.vehicle_id
),
deleted_vehicle AS (
    DELETE FROM dune.vehicles v
    USING target t
    WHERE v.id = t.id
    RETURNING v.id
),
deleted_actor AS (
    DELETE FROM dune.actors a
    USING target t
    WHERE a.id = t.id
    RETURNING a.id, a.class, COALESCE(a.map, '') AS map, COALESCE(a.partition_id::text, '') AS partition_id
)
SELECT
    COALESCE((SELECT id::text FROM target), '{actor_id}') AS requested_actor_id,
    COALESCE((SELECT class FROM target), 'not found or not an allowed vehicle actor') AS vehicle_class,
    COALESCE((SELECT map FROM target), '') AS map,
    COALESCE((SELECT partition_id FROM target), '') AS partition_id,
    (SELECT COUNT(*) FROM deleted_modules) AS module_rows_deleted,
    (SELECT COUNT(*) FROM deleted_vehicle) AS vehicle_rows_deleted,
    (SELECT COUNT(*) FROM deleted_actor) AS actor_rows_deleted;
"""


def world_to_map_pixels(x, y, map_cfg):
    """
    Convert world coordinates to image pixel coordinates using the
    calibrated Hagga Basin map bounds.

    Marker rendering uses percentages, so the display still scales
    correctly if the browser resizes the map image.
    """
    min_x = map_cfg["min_x"]
    max_x = map_cfg["max_x"]
    min_y = map_cfg["min_y"]
    max_y = map_cfg["max_y"]
    width = map_cfg["width"]
    height = map_cfg["height"]

    if max_x == min_x or max_y == min_y:
        return None

    px = ((x - min_x) / (max_x - min_x)) * width
    py = ((y - min_y) / (max_y - min_y)) * height

    if map_cfg.get("flip_y"):
        py = height - py

    return {
        "px": px,
        "py": py,
        "in_bounds": 0 <= px <= width and 0 <= py <= height,
    }


def get_map_markers(map_key=None, partition_id_override=None):
    """
    Pull player, vehicle, and base markers with transform data for the selected map.

    Player markers prefer actor.transform, but also check transform-like
    player_state fields so offline characters can still appear if this server
    build stores their last location outside the actor row.
    """
    map_key = map_key or DEFAULT_MAP_KEY
    map_cfg = MAP_CONFIGS.get(map_key, MAP_CONFIGS[DEFAULT_MAP_KEY])
    actor_map = str(map_cfg.get("actor_map", map_cfg["key"])).replace("'", "''")
    partition_id = str(
        partition_id_override
        if partition_id_override not in (None, "")
        else map_cfg.get("default_partition_id", "")
    ).strip()
    partition_filter = ""
    player_partition_filter = ""
    if partition_id:
        try:
            safe_partition_id = int(partition_id)
            partition_filter = f"AND a.partition_id = {safe_partition_id}"
            player_partition_filter = f"AND partition_id = '{safe_partition_id}'"
        except ValueError:
            partition_filter = ""
            player_partition_filter = ""

    players_sql = f"""
    WITH player_locations AS (
        SELECT
            COALESCE(ps.player_pawn_id::text, a.id::text, ps.player_state_id::text) AS marker_id,
            COALESCE(NULLIF(ps.character_name, ''), 'Unknown') AS name,
            COALESCE(ps.online_status::text, 'Unknown') AS online_status,
            COALESCE(acc."user", '') AS fls_id,
            COALESCE(
                NULLIF(a.map, ''),
                NULLIF(to_jsonb(ps)->>'map', ''),
                NULLIF(to_jsonb(ps)->>'current_map', ''),
                NULLIF(to_jsonb(ps)->>'last_map', '')
            ) AS map,
            COALESCE(
                NULLIF(a.partition_id::text, ''),
                NULLIF(to_jsonb(ps)->>'partition_id', ''),
                NULLIF(to_jsonb(ps)->>'current_partition_id', ''),
                NULLIF(to_jsonb(ps)->>'last_partition_id', '')
            ) AS partition_id,
            COALESCE(
                NULLIF(a.transform::text, ''),
                NULLIF(to_jsonb(ps)->>'transform', ''),
                NULLIF(to_jsonb(ps)->>'current_transform', ''),
                NULLIF(to_jsonb(ps)->>'last_transform', ''),
                NULLIF(to_jsonb(ps)->>'last_known_transform', '')
            ) AS transform
        FROM dune.player_state ps
        LEFT JOIN dune.actors a
            ON a.id = ps.player_pawn_id
        LEFT JOIN dune.accounts acc
            ON ps.account_id = acc.id
    )
    SELECT
        marker_id,
        name,
        online_status,
        fls_id,
        map,
        COALESCE(partition_id, '') AS partition_id,
        transform
    FROM player_locations
    WHERE transform IS NOT NULL
      AND map = '{actor_map}'
      {player_partition_filter}
    ORDER BY
        CASE WHEN online_status = 'Offline' THEN 0 ELSE 1 END,
        name;
    """

    vehicles_sql = f"""
    SELECT
        v.id,
        a.class,
        a.map,
        COALESCE(a.partition_id::text, '') AS partition_id,
        a.transform::text
    FROM dune.vehicles v
    JOIN dune.actors a
        ON v.id = a.id
    WHERE a.transform IS NOT NULL
      AND a.map = '{actor_map}'
      {partition_filter}
    ORDER BY a.class;
    """

    buildings_sql = f"""
    SELECT
        b.id,
        a.class,
        a.map,
        COALESCE(a.partition_id::text, '') AS partition_id,
        a.transform::text
    FROM dune.buildings b
    JOIN dune.actors a
        ON b.id = a.id
    WHERE a.transform IS NOT NULL
      AND a.map = '{actor_map}'
      {partition_filter}
    ORDER BY b.id
    LIMIT 500;
    """

    def run_tab_query(sql):
        cmd = [
            "docker", "exec", POSTGRES_CONTAINER,
            "psql", "-U", "dune", "-d", "dune",
            "-At", "-F", "\t", "-c", sql,
        ]

        proc = run_process(
            cmd,
            timeout=20,
        )

        if proc.returncode != 0:
            return []

        return proc.stdout.strip().splitlines()

    markers = []

    # Players
    for line in run_tab_query(players_sql):
        parts = line.split("\t")
        if len(parts) < 7:
            continue

        coords = parse_transform(parts[6])
        if not coords:
            continue

        pixel = world_to_map_pixels(coords["x"], coords["y"], map_cfg)
        if not pixel:
            continue

        markers.append({
            "id": parts[0],
            "name": parts[1],
            "online_status": parts[2],
            "fls_id": parts[3],
            "map": parts[4],
            "partition_id": parts[5],
            "type": "player",
            **coords,
            **pixel,
        })

    # Vehicles
    for line in run_tab_query(vehicles_sql):
        parts = line.split("\t")
        if len(parts) < 5:
            continue

        coords = parse_transform(parts[4])
        if not coords:
            continue

        pixel = world_to_map_pixels(coords["x"], coords["y"], map_cfg)
        if not pixel:
            continue

        short_class = parts[1].split("/")[-1] if parts[1] else "Vehicle"

        markers.append({
            "id": parts[0],
            "name": short_class,
            "map": parts[2],
            "partition_id": parts[3],
            "type": "vehicle",
            **coords,
            **pixel,
        })

    # Bases/buildings. If the table is not present or the query fails,
    # run_tab_query returns no rows and the map still works.
    for line in run_tab_query(buildings_sql):
        parts = line.split("\t")
        if len(parts) < 5:
            continue

        coords = parse_transform(parts[4])
        if not coords:
            continue

        pixel = world_to_map_pixels(coords["x"], coords["y"], map_cfg)
        if not pixel:
            continue

        short_class = parts[1].split("/")[-1] if parts[1] else "Base"

        markers.append({
            "id": parts[0],
            "name": short_class,
            "map": parts[2],
            "partition_id": parts[3],
            "type": "base",
            **coords,
            **pixel,
        })

    return markers


def get_map_partition_candidates():
    """
    Summarize observed actor map/partition pairs for multi-instance setup.

    Use this after starting extra Survival or Deep Desert instances to discover
    which partition ids the server actually assigned. Partition ids are not
    portable between users or servers.
    """
    sql = """
    SELECT
        COALESCE(a.map, '') AS map,
        COALESCE(a.partition_id::text, '') AS partition_id,
        COUNT(*) AS actor_count,
        COUNT(*) FILTER (WHERE ps.player_pawn_id IS NOT NULL) AS player_count,
        COUNT(*) FILTER (WHERE v.id IS NOT NULL) AS vehicle_count,
        COUNT(*) FILTER (WHERE b.id IS NOT NULL) AS base_count
    FROM dune.actors a
    LEFT JOIN dune.player_state ps
        ON ps.player_pawn_id = a.id
    LEFT JOIN dune.vehicles v
        ON v.id = a.id
    LEFT JOIN dune.buildings b
        ON b.id = a.id
    WHERE a.transform IS NOT NULL
      AND COALESCE(a.map, '') <> ''
    GROUP BY a.map, a.partition_id
    ORDER BY a.map, a.partition_id;
    """

    rows = []
    for line in _run_psql_tsv(sql, timeout=20):
        parts = line.split("\t")
        if len(parts) < 6:
            continue

        rows.append(
            {
                "map": parts[0],
                "partition_id": parts[1],
                "label": f"{parts[0]} - Partition {parts[1]}",
                "actor_count": parts[2],
                "player_count": parts[3],
                "vehicle_count": parts[4],
                "base_count": parts[5],
            }
        )

    return rows


def teleport_offline_player(fls_id, partition_id, x, y, z):
    """
    Teleport an offline player through RedBlink/Funcom's DB function.

    IMPORTANT:
    This is intended for offline characters. Online teleporting may not
    apply cleanly because the live server owns the actor state.
    """
    safe_fls = str(fls_id).replace("'", "''")

    sql = f"""
    SELECT dune.admin_move_offline_player_to_partition(
        '{safe_fls}',
        {int(partition_id)},
        ROW({float(x)}, {float(y)}, {float(z)})::dune.vector
    );
    """

    return run_psql(sql, timeout=60)



def emergency_return_to_hagga_basin(fls_id):
    """
    Move an offline character to the configured safe Hagga Basin point.

    This is meant as an operator/admin unstuck tool.
    """
    cfg = SAFE_HAGGA_BASIN_RETURN

    return teleport_offline_player(
        fls_id,
        cfg["partition_id"],
        cfg["x"],
        cfg["y"],
        cfg["z"],
    )



# =========================================================
# INFRASTRUCTURE HELPERS
# =========================================================

def run_infra_command(cmd, timeout=60, cwd=None):
    """
    Run an infrastructure command from a fixed argument list.

    This is for predefined installer/diagnostic commands. It should not be
    used with raw user command text.
    """
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    return (
        "$ " + " ".join(cmd)
        + "\n\nSTDOUT:\n" + proc.stdout
        + "\nSTDERR:\n" + proc.stderr
        + f"\nExit code: {proc.returncode}"
    )


def prereq_report():
    """
    Build a simple prereq report for RedBlink's stack.

    This checks the obvious local host requirements without mutating anything.
    """
    checks = [
        ("OS / kernel", ["bash", "-lc", "uname -a"]),
        ("Memory", ["bash", "-lc", "free -h"]),
        ("Disk /", ["bash", "-lc", "df -h /"]),
        ("CPU AVX/AVX2", ["bash", "-lc", "lscpu | grep -i 'flags' | head -1 | grep -oE 'avx2|avx' | sort -u | tr '\\n' ' ' || true"]),
        ("Docker", ["bash", "-lc", "docker --version || true"]),
        ("Docker Compose", ["bash", "-lc", "docker compose version || true"]),
        ("Git", ["bash", "-lc", "git --version || true"]),
        ("Dune command", ["bash", "-lc", "command -v dune || true"]),
    ]

    output = []

    for label, cmd in checks:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
            output.append(f"## {label}\n{proc.stdout.strip() or proc.stderr.strip() or '(no output)'}")
        except Exception as exc:
            output.append(f"## {label}\nERROR: {exc}")

    return "\n\n".join(output)


def installer_step_command(step):
    """
    Return a predefined installer command.

    The installer is intentionally step-based instead of one giant root script.
    That makes it easier to inspect, safer to demo, and easier to recover.
    """
    install_dir = shlex.quote(str(REDBLINK_INSTALL_DIR))
    parent_dir = shlex.quote(str(REDBLINK_INSTALL_DIR.parent))
    repo_url = shlex.quote(REDBLINK_REPO_URL)

    commands = {
        "prereq": {
            "cmd": None,
            "timeout": 30,
            "custom": prereq_report,
        },

        "install_base_packages": {
            "cmd": [
                "bash",
                "-lc",
                "sudo -n apt update && sudo -n apt install -y git curl ca-certificates apt-transport-https software-properties-common"
            ],
            "timeout": 300,
        },

        "install_docker": {
            "cmd": [
                "bash",
                "-lc",
                "curl -fsSL https://get.docker.com | sudo -n sh"
            ],
            "timeout": 900,
        },

        "install_docker_fallback": {
            "cmd": [
                "bash",
                "-lc",
                "sudo -n apt update && sudo -n apt install -y docker.io docker-compose-plugin && sudo -n systemctl enable --now docker"
            ],
            "timeout": 900,
        },

        "install_docker_compose_plugin": {
            "cmd": [
                "bash",
                "-lc",
                "sudo -n apt update && sudo -n apt install -y docker-compose-plugin"
            ],
            "timeout": 300,
        },

        "add_user_to_docker_group": {
            "cmd": [
                "bash",
                "-lc",
                "sudo -n usermod -aG docker $USER && echo 'User added to docker group. Logout/login or reboot may be required.'"
            ],
            "timeout": 60,
        },

        "enable_docker_service": {
            "cmd": [
                "bash",
                "-lc",
                "sudo -n systemctl enable --now docker && systemctl status docker --no-pager || true"
            ],
            "timeout": 60,
        },

        "clone_or_pull": {
            "cmd": [
                "bash",
                "-lc",
                f"mkdir -p {parent_dir} && if [ -d {install_dir}/.git ]; then cd {install_dir} && git pull; else git clone {repo_url} {install_dir}; fi"
            ],
            "timeout": 300,
        },

        "install_dune_command": {
            "cmd": [
                "bash",
                "-lc",
                f"cd {install_dir} && sudo -n runtime/scripts/install-command.sh"
            ],
            "timeout": 300,
        },

        "dune_init": {
            "cmd": [
                "bash",
                "-lc",
                f"cd {install_dir} && dune init"
            ],
            "timeout": 600,
        },

        "docker_ps": {
            "cmd": [
                "bash",
                "-lc",
                "docker ps"
            ],
            "timeout": 30,
        },
    }
    return commands.get(step)


def start_shell_session(sid):
    """
    Start a login shell attached to a pseudo-terminal.

    This is powerful. It is admin-only and disabled by default.
    """
    if sid in SHELL_SESSIONS:
        return

    shell = os.environ.get("SHELL", "/bin/bash")
    pid, fd = pty.fork()

    if pid == 0:
        dune_script_dir = str(DUNE_SCRIPT.parent)
        os.environ["PATH"] = dune_script_dir + os.pathsep + os.environ.get("PATH", "")
        if DUNE_ROOT.exists():
            os.chdir(str(DUNE_ROOT))
        os.execv(shell, [shell])

    SHELL_SESSIONS[sid] = {
        "pid": pid,
        "fd": fd,
    }

    def reader():
        while sid in SHELL_SESSIONS:
            try:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if fd in ready:
                    data = os.read(fd, 4096)
                    if not data:
                        break
                    socketio.emit("shell_output", {"data": data.decode(errors="replace")}, to=sid)
            except OSError:
                break
            except Exception as exc:
                socketio.emit("shell_output", {"data": f"\n[terminal error: {exc}]\n"}, to=sid)
                break

        stop_shell_session(sid)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()


def stop_shell_session(sid):
    session_obj = SHELL_SESSIONS.pop(sid, None)

    if not session_obj:
        return

    try:
        os.close(session_obj["fd"])
    except Exception:
        pass

    try:
        os.kill(session_obj["pid"], signal.SIGHUP)
    except Exception:
        pass





# =========================================================
# DASHBOARD RESOURCE HELPERS
# =========================================================

_LAST_NET_SAMPLE = {
    "timestamp": None,
    "bytes_sent": None,
    "bytes_recv": None,
}

def bytes_to_human(value):
    try:
        value = float(value)
    except Exception:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = 0

    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1

    return f"{value:.1f} {units[idx]}"


def duration_to_human(seconds):
    """
    Format a host uptime duration compactly for the dashboard.

    Keep this display short so the metric card remains readable on narrow
    screens and in the Dockerized build's smaller browser windows.
    """
    try:
        seconds = max(int(seconds), 0)
    except Exception:
        return "--"

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def get_system_resource_summary():
    """
    Return host-level resource metrics for the dashboard.

    Network totals are reported since boot. RX/TX rates are estimated from
    the previous API sample and become meaningful after the second refresh.
    """
    global _LAST_NET_SAMPLE

    try:
        now = time.time()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        boot_time = psutil.boot_time()
        load_1m, load_5m, load_15m = os.getloadavg() if hasattr(os, "getloadavg") else (None, None, None)

        rx_rate = 0
        tx_rate = 0

        if (
            _LAST_NET_SAMPLE["timestamp"] is not None
            and _LAST_NET_SAMPLE["bytes_recv"] is not None
            and _LAST_NET_SAMPLE["bytes_sent"] is not None
        ):
            elapsed = max(now - _LAST_NET_SAMPLE["timestamp"], 0.001)
            rx_rate = max((net.bytes_recv - _LAST_NET_SAMPLE["bytes_recv"]) / elapsed, 0)
            tx_rate = max((net.bytes_sent - _LAST_NET_SAMPLE["bytes_sent"]) / elapsed, 0)

        _LAST_NET_SAMPLE = {
            "timestamp": now,
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
        }

        return {
            "ok": True,
            "cpu_percent": round(cpu_percent, 1),
            "memory_percent": round(memory.percent, 1),
            "memory_used": bytes_to_human(memory.used),
            "memory_total": bytes_to_human(memory.total),
            "disk_percent": round(disk.percent, 1),
            "disk_used": bytes_to_human(disk.used),
            "disk_total": bytes_to_human(disk.total),
            "load_1m": "--" if load_1m is None else round(load_1m, 2),
            "load_5m": "--" if load_5m is None else round(load_5m, 2),
            "load_15m": "--" if load_15m is None else round(load_15m, 2),
            "host_uptime": duration_to_human(now - boot_time),
            "updated_at": datetime.now().strftime("%I:%M:%S %p").lstrip("0"),
            "net_sent": bytes_to_human(net.bytes_sent),
            "net_recv": bytes_to_human(net.bytes_recv),
            "net_rx_rate": bytes_to_human(rx_rate) + "/s",
            "net_tx_rate": bytes_to_human(tx_rate) + "/s",
        }

    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }


def get_world_summary_counts():
    """
    Return basic world/server counts for the dashboard.

    Fails gracefully if the RedBlink stack/Postgres container is not running.
    """
    sql = r"""
    WITH player_counts AS (
        SELECT
            COUNT(*) AS total_players,
            COUNT(*) AS known_players,
            COUNT(*) FILTER (WHERE ps.online_status::text <> 'Offline') AS online_players,
            COUNT(*) FILTER (
                WHERE ps.online_status::text <> 'Offline'
                  AND fs.server_id IS NOT NULL
            ) AS live_players
        FROM dune.player_state ps
        LEFT JOIN dune.farm_state fs
            ON fs.server_id = ps.server_id
    ),
    vehicle_counts AS (
        SELECT
            COUNT(*) FILTER (WHERE a.map = 'HaggaBasin') AS vehicles_hagga_basin,
            COUNT(*) FILTER (WHERE a.map = 'DeepDesert') AS vehicles_deep_desert,
            COUNT(*) AS total_vehicles
        FROM dune.vehicles v
        JOIN dune.actors a
            ON a.id = v.id
    ),
    base_counts AS (
        SELECT
            COUNT(*) FILTER (WHERE a.map = 'HaggaBasin') AS bases_hagga_basin,
            COUNT(*) FILTER (WHERE a.map = 'DeepDesert') AS bases_deep_desert
        FROM dune.buildings b
        JOIN dune.actors a
            ON a.id = b.id
    ),
    partition_counts AS (
        SELECT
            COUNT(*) AS world_partitions,
            COUNT(*) FILTER (WHERE COALESCE(server_id, '') <> '') AS active_servers
        FROM dune.world_partition
    )
    SELECT
        pc.total_players,
        pc.known_players,
        pc.online_players,
        pc.live_players,
        vc.total_vehicles,
        vc.vehicles_hagga_basin,
        vc.vehicles_deep_desert,
        bc.bases_hagga_basin,
        bc.bases_deep_desert,
        pcnt.world_partitions,
        pcnt.active_servers
    FROM player_counts pc
    CROSS JOIN vehicle_counts vc
    CROSS JOIN base_counts bc
    CROSS JOIN partition_counts pcnt;
    """

    cmd = [
        "docker", "exec", POSTGRES_CONTAINER,
        "psql", "-U", "dune", "-d", "dune",
        "-At", "-F", "\t", "-c", sql,
    ]

    try:
        proc = run_process(
            cmd,
            timeout=10,
        )

        if proc.returncode != 0:
            return {
                "ok": False,
                "error": proc.stderr.strip() or "world count query failed",
            }

        line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
        parts = line.split("\t")

        if len(parts) < 11:
            return {
                "ok": False,
                "error": "unexpected world count output",
            }

        return {
            "ok": True,
            "total_players": parts[0],
            "known_players": parts[1],
            "online_players": parts[2],
            "live_players": parts[3],
            "total_vehicles": parts[4],
            "vehicles_hagga_basin": parts[5],
            "vehicles_deep_desert": parts[6],
            "bases_hagga_basin": parts[7],
            "bases_deep_desert": parts[8],
            "world_partitions": parts[9],
            "active_servers": parts[10],
        }

    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }


def build_dashboard_metrics_payload():
    return {
        "ok": True,
        "system": get_system_resource_summary(),
        "world": get_world_summary_counts(),
    }
