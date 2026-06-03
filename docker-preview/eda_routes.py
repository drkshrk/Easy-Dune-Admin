"""
Easy Dune Admin route registrations.

Importing this module attaches all Flask routes and Socket.IO handlers to the
shared app/socketio objects from eda_core. Keep route handlers here and shared
business logic in eda_core or future service modules.
"""

from eda_core import *  # noqa: F401,F403 - route module intentionally shares app context

# =========================================================
# SETUP / LOGIN / ACCOUNT
# =========================================================

@app.route("/setup", methods=["GET", "POST"])
def setup():
    if user_count() > 0:
        return redirect("/login")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username and password:
            conn = db()
            conn.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), "admin"),
            )
            conn.commit()
            conn.close()

            log_action(username, "created first admin account")
            return redirect("/login")

    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if user_count() == 0:
        return redirect("/setup")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        installation_mode = request.form.get("installation_mode", DEFAULT_INSTALLATION_MODE).strip().casefold()
        if installation_mode not in INSTALLATION_MODES:
            installation_mode = DEFAULT_INSTALLATION_MODE

        conn = db()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if row and check_password_hash(row["password"], password):
            session["user"] = row["username"]
            session["role"] = row["role"]
            session["installation_mode"] = installation_mode
            log_action(username, f"logged in using {INSTALLATION_MODES[installation_mode]['label']} mode")
            return redirect("/")

    return render_template("login.html")


@app.route("/logout")
def logout():
    if "user" in session:
        log_action(session["user"], "logged out")
    session.clear()
    return redirect("/login")


@app.route("/account", methods=["GET", "POST"])
def account():
    if not logged_in():
        return redirect("/login")

    message = ""

    if request.method == "POST":
        new_username = request.form.get("username", "").strip()
        new_password = request.form.get("password", "").strip()

        conn = db()

        if new_username:
            conn.execute(
                "UPDATE users SET username = ? WHERE username = ?",
                (new_username, session["user"]),
            )
            log_action(session["user"], f"changed username to {new_username}")
            session["user"] = new_username
            message = "Username updated."

        if new_password:
            conn.execute(
                "UPDATE users SET password = ? WHERE username = ?",
                (generate_password_hash(new_password), session["user"]),
            )
            log_action(session["user"], "changed own password")
            message = "Password updated."

        conn.commit()
        conn.close()

    return render_template("account.html", message=message)


# =========================================================
# PAGES
# =========================================================

@app.route("/")
def dashboard():
    if not logged_in():
        return redirect("/login")

    metrics = build_dashboard_metrics_payload()

    return render_template(
        "dashboard.html",
        system_summary=metrics["system"],
        world_summary=metrics["world"],
    )


@app.route("/online")
def online_page():
    if not logged_in():
        return redirect("/login")
    return render_template("online.html")


@app.route("/map")
def map_page():
    if not logged_in():
        return redirect("/login")
    return render_template("map.html")


@app.route("/grants")
def grants_page():
    if not logged_in():
        return redirect("/login")
    if not is_operator_or_admin():
        return "Forbidden", 403
    return render_template("grants.html")


@app.route("/server")
def server_page():
    if not logged_in():
        return redirect("/login")
    if not is_operator_or_admin():
        return "Forbidden", 403
    return render_template("server.html")


@app.route("/vip")
def vip_page():
    if not logged_in():
        return redirect("/login")
    if not can_use_vip_tools():
        return "Forbidden", 403
    return render_template("vip.html")


@app.route("/admin")
def admin_page():
    if not logged_in():
        return redirect("/login")
    if not is_admin():
        return "Forbidden", 403
    return render_template("admin.html")


@app.route("/developer", methods=["GET", "POST"])
def developer_page():
    if not logged_in():
        return redirect("/login")
    if not is_admin():
        return "Forbidden", 403

    error = ""
    if request.method == "POST":
        developer_key = request.form.get("developer_key", "")
        if check_password_hash(DEVELOPER_KEY_HASH, developer_key):
            session["developer_unlocked"] = True
            log_action(session["user"], "unlocked developer panel")
            return redirect("/developer")
        error = "Developer key rejected."
        log_action(session["user"], "failed developer panel key check")

    return render_template("developer.html", developer_unlocked=has_developer_access(), error=error)


@app.route("/developer/lock", methods=["POST"])
def developer_lock():
    if not logged_in():
        return redirect("/login")
    if not is_admin():
        return "Forbidden", 403
    session.pop("developer_unlocked", None)
    log_action(session["user"], "locked developer panel")
    return redirect("/admin")


@app.route("/infrastructure")
def infrastructure_page():
    if not logged_in():
        return redirect("/login")
    if not is_admin():
        return "Forbidden", 403
    return render_template("infrastructure.html")


@app.route("/users")
def users_page():
    if not logged_in():
        return redirect("/login")
    if not is_admin():
        return "Forbidden", 403
    return render_template("users.html", users=list_users())


@app.route("/logs")
def logs_page():
    if not logged_in():
        return redirect("/login")
    if not is_admin():
        return "Forbidden", 403
    return render_template("logs.html", lines=recent_log_lines())


# =========================================================
# USER MANAGEMENT ROUTES
# =========================================================

@app.route("/users/add", methods=["POST"])
def add_user():
    if not logged_in() or not is_admin():
        return "Forbidden", 403

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    role = request.form.get("role", "viewer").strip()
    character_name = request.form.get("character_name", "").strip()

    if role not in ("viewer", "vip", "operator", "admin"):
        role = "viewer"

    if username and password:
        conn = db()
        conn.execute(
            "INSERT INTO users (username, password, role, character_name) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), role, character_name),
        )
        conn.commit()
        conn.close()
        log_action(session["user"], f"created user {username} ({role})")

    return redirect("/users")


@app.route("/users/role", methods=["POST"])
def change_user_role():
    if not logged_in() or not is_admin():
        return "Forbidden", 403

    user_id = request.form.get("user_id", "").strip()
    role = request.form.get("role", "viewer").strip()

    if role not in ("viewer", "vip", "operator", "admin"):
        role = "viewer"

    conn = db()
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    conn.commit()
    conn.close()

    log_action(session["user"], f"changed user id {user_id} role to {role}")
    return redirect("/users")


@app.route("/users/character", methods=["POST"])
def change_user_character():
    if not logged_in() or not is_admin():
        return "Forbidden", 403

    user_id = request.form.get("user_id", "").strip()
    character_name = request.form.get("character_name", "").strip()

    conn = db()
    conn.execute(
        "UPDATE users SET character_name = ? WHERE id = ?",
        (character_name, user_id),
    )
    conn.commit()
    conn.close()

    log_action(session["user"], f"changed user id {user_id} character link to {character_name}")
    return redirect("/users")


@app.route("/users/password", methods=["POST"])
def reset_user_password():
    if not logged_in() or not is_admin():
        return "Forbidden", 403

    user_id = request.form.get("user_id", "").strip()
    password = request.form.get("password", "").strip()

    if password:
        conn = db()
        conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (generate_password_hash(password), user_id),
        )
        conn.commit()
        conn.close()
        log_action(session["user"], f"reset password for user id {user_id}")

    return redirect("/users")


@app.route("/users/delete", methods=["POST"])
def delete_user():
    if not logged_in() or not is_admin():
        return "Forbidden", 403

    user_id = request.form.get("user_id", "").strip()

    conn = db()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    log_action(session["user"], f"deleted user id {user_id}")
    return redirect("/users")


# =========================================================
# AJAX API ROUTES
# =========================================================

@app.route("/api/characters")
def api_characters():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    include_offline = request.args.get("include_offline", "1") != "0"
    chars = get_characters(include_offline=include_offline)

    # Viewer/VIP privacy: broad character APIs do not expose IDs to lower roles.
    # VIP self-service receives its own IDs through /api/vip-character only.
    if current_role() in ("viewer", "vip"):
        chars = [
            {
                "character_name": c.get("character_name", ""),
                "online_status": c.get("online_status", ""),
                "life_state": c.get("life_state", ""),
            }
            for c in chars
        ]

    return jsonify({"ok": True, "characters": chars})


@app.route("/api/character-inventories")
def api_character_inventories():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.args.get("character_actor_id", "").strip()
    if not character_actor_id:
        return jsonify({"ok": False, "error": "missing character actor ID"}), 400

    try:
        inventories = get_character_inventories(character_actor_id)
        return jsonify({"ok": True, "inventories": inventories})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Inventory lookup failed: {exc}"}), 500


@app.route("/api/character-inventory-items")
def api_character_inventory_items():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.args.get("character_actor_id", "").strip()
    inventory_id = request.args.get("inventory_id", "").strip()
    if not character_actor_id or not inventory_id:
        return jsonify({"ok": False, "error": "missing character actor ID or inventory ID"}), 400

    try:
        items = get_character_inventory_items(character_actor_id, inventory_id)
        return jsonify({"ok": True, "items": items})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Inventory item lookup failed: {exc}"}), 500


@app.route("/api/online-players")
def api_online_players():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    players = get_characters(include_offline=False)

    if current_role() in ("viewer", "vip"):
        players = [
            {
                "character_name": p.get("character_name", ""),
                "online_status": p.get("online_status", ""),
                "life_state": p.get("life_state", ""),
                "funcom_id": p.get("funcom_id", ""),
                "map": p.get("map", ""),
                "partition_id": p.get("partition_id", ""),
            }
            for p in players
        ]
    else:
        # The online player UI intentionally omits FLS/account IDs. Keep them
        # available to more targeted admin APIs, not this broad status widget.
        players = [
            {
                "character_name": p.get("character_name", ""),
                "online_status": p.get("online_status", ""),
                "life_state": p.get("life_state", ""),
                "funcom_id": p.get("funcom_id", ""),
                "map": p.get("map", ""),
                "partition_id": p.get("partition_id", ""),
            }
            for p in players
        ]

    return jsonify({"ok": True, "players": players})


@app.route("/api/developer-npc-research")
def api_developer_npc_research():
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    query = request.args.get("q", "").strip()

    try:
        return jsonify({"ok": True, "research": developer_npc_research(query)})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"NPC research lookup failed: {exc}"}), 500


@app.route("/api/developer-ban-lookup")
def api_developer_ban_lookup():
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    query = request.args.get("q", "").strip()

    try:
        return jsonify({"ok": True, "research": developer_ban_lookup(query)})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Ban lookup failed: {exc}"}), 500


@app.route("/api/developer-flag-cheater", methods=["POST"])
def api_developer_flag_cheater():
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    fls_id = request.form.get("fls_id", "").strip()
    cheat_type = request.form.get("cheat_type", "").strip()

    try:
        sql = build_developer_flag_cheater_sql(fls_id, cheat_type)
        output = run_psql_script(sql, timeout=60)
        log_action(session["user"], f"developer experimental cheater flag {cheat_type} for {fls_id}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Experimental cheater flag failed: {exc}"}), 500


@app.route("/api/developer-unflag-cheater", methods=["POST"])
def api_developer_unflag_cheater():
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    fls_id = request.form.get("fls_id", "").strip()
    row_id = request.form.get("row_id", "").strip()

    try:
        sql = build_developer_unflag_cheater_sql(fls_id=fls_id, row_id=row_id)
        output = run_psql_script(sql, timeout=60)
        log_action(session["user"], f"developer experimental cheater unflag fls={fls_id} row={row_id}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Experimental cheater unflag failed: {exc}"}), 500


@app.route("/api/footer-online-users")
def api_footer_online_users():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    return jsonify({"ok": True, "users": footer_online_users()})


@app.route("/api/item-search")
def api_item_search():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    query = request.args.get("q", "").strip()
    return jsonify({"ok": True, "items": search_items(query)})


@app.route("/api/map-markers")
def api_map_markers():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    requested_map = request.args.get("map", DEFAULT_MAP_KEY).strip()
    requested_partition = request.args.get("partition_id", "").strip()
    map_cfg = MAP_CONFIGS.get(requested_map, MAP_CONFIGS[DEFAULT_MAP_KEY])
    markers = get_map_markers(map_cfg["key"], requested_partition)

    # Viewer/VIP privacy: map markers may show names/dots, but not FLS IDs.
    if current_role() in ("viewer", "vip"):
        for marker in markers:
            marker.pop("fls_id", None)

    return jsonify({
        "ok": True,
        "map": map_cfg,
        "maps": MAP_CONFIGS,
        "default_map": DEFAULT_MAP_KEY,
        "markers": markers,
    })


@app.route("/api/map-partitions")
def api_map_partitions():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not (is_operator_or_admin() or can_use_vip_tools()):
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        return jsonify({"ok": True, "partitions": get_map_partition_candidates()})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Map partition lookup failed: {exc}"}), 500


@app.route("/api/teleport-offline", methods=["POST"])
def api_teleport_offline():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    fls_id = request.form.get("fls_id", "").strip()
    map_key = request.form.get("map_key", DEFAULT_MAP_KEY).strip()
    map_cfg = MAP_CONFIGS.get(map_key, MAP_CONFIGS[DEFAULT_MAP_KEY])
    partition_default = map_cfg.get("default_partition_id", "")
    partition_id = request.form.get("partition_id", str(partition_default)).strip()
    x = request.form.get("x", "0").strip()
    y = request.form.get("y", "0").strip()
    z = request.form.get("z", "0").strip()

    if not fls_id:
        return jsonify({"ok": False, "error": "missing FLS ID"}), 400

    if not partition_id:
        return jsonify({"ok": False, "error": "missing partition ID for selected map"}), 400

    try:
        output = teleport_offline_player(fls_id, partition_id, x, y, z)

        log_action(
            session["user"],
            f"teleport offline fls {fls_id} partition {partition_id} to ({x}, {y}, {z})",
        )

        return jsonify({"ok": True, "output": output})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"Teleport failed: {exc}"}), 500


@app.route("/api/vip-character")
def api_vip_character():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not can_use_vip_tools():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        character = get_self_character_for_user(session["user"])
        # This endpoint is self-only. It intentionally returns the user's own
        # actor/inventory/FLS IDs so the VIP page can display useful diagnostics.
        return jsonify({"ok": True, "character": character})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@app.route("/api/vip-overrepair", methods=["POST"])
def api_vip_overrepair():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not can_use_vip_tools():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    durability = request.form.get("durability", DEFAULT_OVERREPAIR_DURABILITY).strip()

    try:
        character = get_self_character_for_user(session["user"])
        if not character.get("character_actor_id"):
            return jsonify({"ok": False, "error": "linked character actor not found"}), 400

        sql = build_overrepair_all_inventories_sql(
            character["character_actor_id"],
            durability,
        )
        output = run_psql(sql, timeout=60)

        log_action(
            session["user"],
            f"vip overrepair all inventories for own character {character['character_name']} durability {durability}",
        )

        return jsonify({"ok": True, "output": output})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"VIP overrepair failed: {exc}"}), 500


@app.route("/api/vip-teleport-offline", methods=["POST"])
def api_vip_teleport_offline():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not can_use_vip_tools():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    map_key = request.form.get("map_key", DEFAULT_MAP_KEY).strip()
    map_cfg = MAP_CONFIGS.get(map_key, MAP_CONFIGS[DEFAULT_MAP_KEY])
    partition_default = map_cfg.get("default_partition_id", "")
    partition_id = request.form.get("partition_id", str(partition_default)).strip()
    x = request.form.get("x", "0").strip()
    y = request.form.get("y", "0").strip()
    z = request.form.get("z", "1000").strip()

    if not partition_id:
        return jsonify({"ok": False, "error": "missing partition ID for selected map"}), 400

    try:
        character = get_self_character_for_user(session["user"])
        if not character.get("fls_id"):
            return jsonify({"ok": False, "error": "linked character FLS/account ID not found"}), 400

        output = teleport_offline_player(character["fls_id"], partition_id, x, y, z)

        log_action(
            session["user"],
            f"vip teleport own character {character['character_name']} partition {partition_id} to ({x}, {y}, {z})",
        )

        return jsonify({"ok": True, "output": output})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"VIP teleport failed: {exc}"}), 500


@app.route("/api/vip-emergency-return", methods=["POST"])
def api_vip_emergency_return():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not can_use_vip_tools():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        character = get_self_character_for_user(session["user"])
        if not character.get("fls_id"):
            return jsonify({"ok": False, "error": "linked character FLS/account ID not found"}), 400

        output = emergency_return_to_hagga_basin(character["fls_id"])

        log_action(
            session["user"],
            f"vip emergency return own character {character['character_name']} to Hagga Basin safe point",
        )

        return jsonify({"ok": True, "output": output})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"VIP emergency return failed: {exc}"}), 500


@app.route("/api/vip-give-scout-thopter", methods=["POST"])
def api_vip_give_scout_thopter():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not can_use_vip_tools():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        character = get_self_character_for_user(session["user"])
        if not character.get("fls_id"):
            return jsonify({"ok": False, "error": "linked character FLS/account ID not found"}), 400

        cmd = [
            str(DUNE_SCRIPT),
            "admin",
            "grant-template",
            character["fls_id"],
            SCOUT_THOPTER_TEMPLATE,
        ]
        output = run_command(cmd, timeout=60, input_text="y\n")

        log_action(
            session["user"],
            f"vip grant template {SCOUT_THOPTER_TEMPLATE} to own character {character['character_name']}",
        )

        return jsonify({"ok": True, "output": output})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"VIP scout thopter grant failed: {exc}"}), 500


@app.route("/api/vip-give-medium-thopter", methods=["POST"])
def api_vip_give_medium_thopter():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not can_use_vip_tools():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        character = get_self_character_for_user(session["user"])
        if not character.get("fls_id"):
            return jsonify({"ok": False, "error": "linked character FLS/account ID not found"}), 400

        outputs = []
        for item_id, qty in MEDIUM_THOPTER_BUNDLE:
            outputs.append(grant_item(character["fls_id"], item_id, qty, "1.0"))

        log_action(
            session["user"],
            f"vip grant Mk6 Medium thopter bundle to own character {character['character_name']}",
        )

        return jsonify({"ok": True, "output": "\n\n---\n\n".join(outputs)})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"VIP medium thopter grant failed: {exc}"}), 500


@app.route("/api/vip-refill-water", methods=["POST"])
def api_vip_refill_water():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not can_use_vip_tools():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    amount = request.form.get("amount", str(DEFAULT_WATER_REFILL_AMOUNT)).strip()

    try:
        refill_amount = int(amount)
        if refill_amount <= 0:
            return jsonify({"ok": False, "error": "water refill amount must be positive"}), 400

        character = get_self_character_for_user(session["user"])
        if not character.get("fls_id"):
            return jsonify({"ok": False, "error": "linked character FLS/account ID not found"}), 400

        cmd = [
            "env",
            "DUNE_ADMIN_ASSUME_YES=1",
            str(DUNE_SCRIPT),
            "admin",
            "refill-water",
            character["fls_id"],
            str(refill_amount),
        ]
        output = run_command(cmd, timeout=60)

        log_action(
            session["user"],
            f"vip refill water for own character {character['character_name']} amount {refill_amount}",
        )

        return jsonify({"ok": True, "output": output})

    except ValueError:
        return jsonify({"ok": False, "error": "water refill amount must be a whole number"}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"VIP refill water failed: {exc}"}), 500


@app.route("/api/emergency-return", methods=["POST"])
def api_emergency_return():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    fls_id = request.form.get("fls_id", "").strip()

    if not fls_id:
        return jsonify({"ok": False, "error": "missing FLS ID"}), 400

    try:
        output = emergency_return_to_hagga_basin(fls_id)

        log_action(
            session["user"],
            f"emergency return to Hagga Basin safe point for {fls_id}",
        )

        return jsonify({"ok": True, "output": output})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"Emergency return failed: {exc}"}), 500


@app.route("/api/market-preset-preview")
def api_market_preset_preview():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        summary = market_seed_summary(request.args.get("price_multiplier"))
        return jsonify({"ok": True, "summary": summary})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Market preset preview failed: {exc}"}), 500


@app.route("/api/market-exchanges")
def api_market_exchanges():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        return jsonify({"ok": True, "exchanges": get_market_exchanges()})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Market exchange lookup failed: {exc}"}), 500


@app.route("/api/market-seed-preset", methods=["POST"])
def api_market_seed_preset():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    clear_existing = request.form.get("clear_existing", "0") == "1"
    price_multiplier = market_price_multiplier_from_value(request.form.get("price_multiplier"))
    exchange_id = market_exchange_id_from_value(request.form.get("exchange_id"))

    try:
        output = seed_market_preset(
            clear_existing=clear_existing,
            price_multiplier=price_multiplier,
            exchange_id=exchange_id,
        )
        log_action(
            session["user"],
            f"seeded market preset with {price_multiplier}x prices exchange_id={exchange_id or 'Global'} clear_existing={clear_existing}",
        )
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Market preset seed failed: {exc}"}), 500


@app.route("/api/market-clear-npc", methods=["POST"])
def api_market_clear_npc():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        output = clear_market_npc_listings()
        log_action(session["user"], f"cleared {MARKET_BOT_CLASS} NPC market listings")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Market NPC clear failed: {exc}"}), 500


@app.route("/api/market-buy-player-listings", methods=["POST"])
def api_market_buy_player_listings():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    price_multiplier = market_price_multiplier_from_value(request.form.get("price_multiplier"))
    threshold_percent = market_buy_threshold_from_value(request.form.get("threshold_percent"))
    max_buys = market_buy_max_from_value(request.form.get("max_buys"))

    try:
        output = run_buyback_sweep(
            price_multiplier=price_multiplier,
            threshold_percent=threshold_percent,
            max_buys=max_buys,
        )
        log_action(
            session["user"],
            f"{MARKET_BOT_CLASS} bought player listings at {threshold_percent}% threshold using {price_multiplier}x prices, max {max_buys}",
        )
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Market buy failed: {exc}"}), 500


@app.route("/api/market-buyback-status")
def api_market_buyback_status():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    return jsonify({"ok": True, "status": market_buyback_status()})


@app.route("/api/market-buyback-start", methods=["POST"])
def api_market_buyback_start():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    price_multiplier = market_price_multiplier_from_value(request.form.get("price_multiplier"))
    threshold_percent = market_buy_threshold_from_value(request.form.get("threshold_percent"))
    max_buys = market_buy_max_from_value(request.form.get("max_buys"))
    interval_minutes = market_buyback_interval_from_value(request.form.get("interval_minutes"))

    try:
        status = start_market_buyback_sweep(
            price_multiplier=price_multiplier,
            threshold_percent=threshold_percent,
            max_buys=max_buys,
            interval_minutes=interval_minutes,
        )
        log_action(
            session["user"],
            f"started automated {MARKET_BOT_CLASS} buyback every {status['interval_minutes']} minutes at {threshold_percent}% using {price_multiplier}x prices, max {max_buys}",
        )
        return jsonify({"ok": True, "status": status, "output": "Automated buyback sweep started."})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Market buyback start failed: {exc}"}), 500


@app.route("/api/market-buyback-stop", methods=["POST"])
def api_market_buyback_stop():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        status = stop_market_buyback_sweep()
        log_action(session["user"], f"stopped automated {MARKET_BOT_CLASS} buyback")
        return jsonify({"ok": True, "status": status, "output": "Automated buyback sweep stopped."})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Market buyback stop failed: {exc}"}), 500


@app.route("/api/market-reseed-status")
def api_market_reseed_status():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    return jsonify({"ok": True, "status": market_reseed_status()})


@app.route("/api/market-reseed-start", methods=["POST"])
def api_market_reseed_start():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    price_multiplier = market_price_multiplier_from_value(request.form.get("price_multiplier"))
    exchange_id = market_exchange_id_from_value(request.form.get("exchange_id"))
    interval_minutes = market_reseed_interval_from_value(request.form.get("interval_minutes"))

    try:
        status = start_market_reseed_sweep(
            price_multiplier=price_multiplier,
            exchange_id=exchange_id,
            interval_minutes=interval_minutes,
        )
        log_action(
            session["user"],
            f"started automated {MARKET_BOT_CLASS} reseed every {status['interval_minutes']} minutes using {price_multiplier}x prices exchange_id={exchange_id or 'Global'}",
        )
        return jsonify({"ok": True, "status": status, "output": "Automated market reseed started."})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Market reseed start failed: {exc}"}), 500


@app.route("/api/market-reseed-stop", methods=["POST"])
def api_market_reseed_stop():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        status = stop_market_reseed_sweep()
        log_action(session["user"], f"stopped automated {MARKET_BOT_CLASS} reseed")
        return jsonify({"ok": True, "status": status, "output": "Automated market reseed stopped."})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Market reseed stop failed: {exc}"}), 500



@app.route("/api/infra-command", methods=["POST"])
def api_infra_command():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    if current_installation_capabilities()["is_hyperv"]:
        return jsonify({"ok": False, "error": "infrastructure diagnostics are hidden in Hyper-V mode; use SSH to the VM"}), 403

    if not ENABLE_HOST_COMMAND_RUNNER:
        return jsonify({"ok": False, "error": "host command runner disabled; set ENABLE_HOST_COMMAND_RUNNER=1"}), 403

    command_key = request.form.get("command", "").strip()
    entry = ALLOWED_INFRA_COMMANDS.get(command_key)

    if not entry:
        return jsonify({"ok": False, "error": "unknown command"}), 400

    try:
        output = run_infra_command(entry["cmd"], timeout=entry.get("timeout", 60))
        log_action(session["user"], f"ran infra command {command_key}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Command failed: {exc}"}), 500


@app.route("/api/installer-step", methods=["POST"])
def api_installer_step():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    if not current_installation_capabilities()["stack_installer"]:
        return jsonify({"ok": False, "error": "stack installer is available only in Linux Host mode"}), 403

    if not ENABLE_STACK_INSTALLER:
        return jsonify({"ok": False, "error": "stack installer disabled; set ENABLE_STACK_INSTALLER=1"}), 403

    step = request.form.get("step", "").strip()
    entry = installer_step_command(step)

    if not entry:
        return jsonify({"ok": False, "error": "unknown installer step"}), 400

    try:
        if entry.get("custom"):
            output = entry["custom"]()
        else:
            output = run_infra_command(entry["cmd"], timeout=entry.get("timeout", 60))

        log_action(session["user"], f"ran installer step {step}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Installer step failed: {exc}"}), 500




@app.route("/api/dashboard-metrics")
def api_dashboard_metrics():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    return jsonify(build_dashboard_metrics_payload())


@app.route("/api/logs")
def api_logs():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403
    return jsonify({"ok": True, "lines": recent_log_lines()})


@app.route("/api/grant", methods=["POST"])
def api_grant():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    player_id = request.form.get("player_id", "").strip()
    item_id = request.form.get("item_id", "").strip()
    quantity = request.form.get("quantity", "1").strip()
    durability = request.form.get("durability", "1.0").strip()

    try:
        output = grant_item(player_id, item_id, quantity, durability)
        log_action(session["user"], f"grant {item_id} x{quantity} to {player_id}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Grant failed: {exc}"}), 500


@app.route("/api/grant-lasgun-augment-bundle", methods=["POST"])
def api_grant_lasgun_augment_bundle():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    player_id = request.form.get("player_id", "").strip()
    if not player_id:
        return jsonify({"ok": False, "error": "missing player/FLS id"}), 400

    outputs = []
    try:
        for item_id, qty in LASGUN_AUGMENT_BUNDLE:
            outputs.append(grant_item(player_id, item_id, qty, "1.0"))

        log_action(session["user"], f"grant lasgun augment bundle to {player_id}")
        return jsonify({"ok": True, "output": "\n\n---\n\n".join(outputs)})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Lasgun bundle grant failed: {exc}"}), 500


@app.route("/api/grant-new-player-kit", methods=["POST"])
def api_grant_new_player_kit():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    player_id = request.form.get("player_id", "").strip()
    if not player_id:
        return jsonify({"ok": False, "error": "missing player/FLS id"}), 400

    outputs = []
    try:
        for item_id, qty in NEW_PLAYER_STARTER_KIT:
            outputs.append(grant_item(player_id, item_id, qty, "1.0"))

        log_action(session["user"], f"grant new player starter kit to {player_id}")
        return jsonify({"ok": True, "output": "\n\n---\n\n".join(outputs)})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"New player starter kit grant failed: {exc}"}), 500


@app.route("/api/grant-solari", methods=["POST"])
def api_grant_solari():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    player_id = request.form.get("player_id", "").strip()
    amount_text = request.form.get("amount", "").strip()

    if not player_id:
        return jsonify({"ok": False, "error": "missing player/FLS id"}), 400

    try:
        amount = int(amount_text)
        if amount not in SOLARIS_GRANT_AMOUNTS:
            return jsonify({"ok": False, "error": "unsupported Solari amount"}), 400

        output = grant_item(player_id, SOLARIS_COIN_ITEM_ID, amount, "1.0")
        log_action(session["user"], f"grant {amount} SolarisCoin to {player_id}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Solari grant failed: {exc}"}), 500


@app.route("/api/solari-bank-balance")
def api_solari_bank_balance():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.args.get("character_actor_id", "").strip()
    if not character_actor_id:
        return jsonify({"ok": False, "error": "missing character actor ID"}), 400

    try:
        return jsonify({"ok": True, "balance": get_solari_bank_balance(character_actor_id)})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Solari Coin lookup failed: {exc}"}), 500


@app.route("/api/exchange-bank-solari-balance")
def api_exchange_bank_solari_balance():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.args.get("character_actor_id", "").strip()
    player_controller_id = request.args.get("player_controller_id", "").strip()
    if not character_actor_id and not player_controller_id:
        return jsonify({"ok": False, "error": "missing character actor ID or player controller ID"}), 400

    try:
        if player_controller_id:
            balance = get_exchange_bank_solari_balance_by_controller(player_controller_id)
        else:
            balance = get_exchange_bank_solari_balance(character_actor_id)
        return jsonify({"ok": True, "balance": balance})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Solari Credit lookup failed: {exc}"}), 500


@app.route("/api/add-solari-bank", methods=["POST"])
def api_add_solari_bank():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    amount = request.form.get("amount", "").strip()
    if not character_actor_id:
        return jsonify({"ok": False, "error": "missing character actor ID"}), 400

    try:
        parsed_amount = solari_bank_amount_from_value(amount)
        sql = build_add_solari_bank_sql(character_actor_id, parsed_amount)
        output = run_psql_script(sql, timeout=60)
        log_action(session["user"], f"added {parsed_amount} Solari Coin to actor {character_actor_id}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Solari Coin add failed: {exc}"}), 500


@app.route("/api/add-exchange-bank-solari", methods=["POST"])
def api_add_exchange_bank_solari():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    player_controller_id = request.form.get("player_controller_id", "").strip()
    amount = request.form.get("amount", "").strip()
    if not character_actor_id and not player_controller_id:
        return jsonify({"ok": False, "error": "missing character actor ID or player controller ID"}), 400

    try:
        parsed_amount = solari_bank_amount_from_value(amount)
        if player_controller_id:
            sql = build_add_exchange_bank_solari_by_controller_sql(player_controller_id, parsed_amount)
            log_target = f"controller {player_controller_id}"
        else:
            sql = build_add_exchange_bank_solari_sql(character_actor_id, parsed_amount)
            log_target = f"actor {character_actor_id}"
        output = run_psql(sql, timeout=60)
        log_action(session["user"], f"added {parsed_amount} Solari Credit to {log_target}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Solari Credit add failed: {exc}"}), 500


@app.route("/api/set-solari-bank", methods=["POST"])
def api_set_solari_bank():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    target_balance = request.form.get("target_balance", "").strip()
    if not character_actor_id:
        return jsonify({"ok": False, "error": "missing character actor ID"}), 400

    try:
        parsed_target = solari_bank_balance_from_value(target_balance)
        sql = build_set_solari_bank_sql(character_actor_id, parsed_target)
        output = run_psql_script(sql, timeout=60)
        log_action(session["user"], f"set Solari Coin for actor {character_actor_id} to {parsed_target}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Solari Coin set failed: {exc}"}), 500


@app.route("/api/set-exchange-bank-solari", methods=["POST"])
def api_set_exchange_bank_solari():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    player_controller_id = request.form.get("player_controller_id", "").strip()
    target_balance = request.form.get("target_balance", "").strip()
    if not character_actor_id and not player_controller_id:
        return jsonify({"ok": False, "error": "missing character actor ID or player controller ID"}), 400

    try:
        parsed_target = solari_bank_balance_from_value(target_balance)
        if player_controller_id:
            sql = build_set_exchange_bank_solari_by_controller_sql(player_controller_id, parsed_target)
            log_target = f"controller {player_controller_id}"
        else:
            sql = build_set_exchange_bank_solari_sql(character_actor_id, parsed_target)
            log_target = f"actor {character_actor_id}"
        output = run_psql(sql, timeout=60)
        log_action(session["user"], f"set Solari Credit for {log_target} to {parsed_target}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Solari Credit set failed: {exc}"}), 500


@app.route("/api/set-research-points", methods=["POST"])
def api_set_research_points():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    research_points = request.form.get("research_points", "").strip()

    try:
        sql = build_set_research_points_sql(character_actor_id, research_points)
        output = run_psql(sql, timeout=60)
        log_action(
            session["user"],
            f"set research points actor {character_actor_id} to {research_points}",
        )
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Research point update failed: {exc}"}), 500


@app.route("/api/give-specialization-xp", methods=["POST"])
def api_give_specialization_xp():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    track_type = request.form.get("track_type", "").strip()
    xp_amount = request.form.get("xp_amount", "").strip()

    try:
        sql = build_give_specialization_xp_sql(character_actor_id, track_type, xp_amount)
        output = run_psql(sql, timeout=60)
        log_action(
            session["user"],
            f"give {xp_amount} {track_type} XP to actor {character_actor_id}",
        )
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"XP grant failed: {exc}"}), 500


@app.route("/api/max-specialization", methods=["POST"])
def api_max_specialization():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()

    try:
        sql = build_max_specialization_sql(character_actor_id)
        output = run_psql_script(sql, timeout=60)
        log_action(session["user"], f"max specialization tracks and keystones for actor {character_actor_id}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Specialization max failed: {exc}"}), 500


@app.route("/api/grant-all-specialization-tracks", methods=["POST"])
def api_grant_all_specialization_tracks():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()

    try:
        sql = build_grant_all_specialization_tracks_sql(character_actor_id)
        output = run_psql(sql, timeout=60)
        log_action(session["user"], f"grant all specialization track rows for actor {character_actor_id}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Specialization track grant failed: {exc}"}), 500


@app.route("/api/reset-specialization", methods=["POST"])
def api_reset_specialization():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    track_type = request.form.get("track_type", "").strip()

    try:
        sql = build_reset_specialization_sql(character_actor_id, track_type)
        output = run_psql_script(sql, timeout=60)
        log_action(
            session["user"],
            f"reset specialization {track_type} for actor {character_actor_id}",
        )
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Specialization reset failed: {exc}"}), 500


@app.route("/api/class-progression-unlock", methods=["POST"])
def api_class_progression_unlock():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    preset_value = request.form.get("preset_id", "").strip()
    action = request.form.get("action", "").strip().lower() or "apply"
    preset_id = preset_value
    if ":" in preset_value:
        action, preset_id = preset_value.split(":", 1)

    try:
        sql = build_class_progression_sql(character_actor_id, preset_id, action)
        output = run_psql(sql, timeout=60)
        log_action(session["user"], f"{action} class progression preset {preset_id} for actor {character_actor_id}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Class progression unlock failed: {exc}"}), 500


@app.route("/api/unlock-advanced-bene-gesserit", methods=["POST"])
def api_unlock_advanced_bene_gesserit():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()

    try:
        sql = build_unlock_advanced_bene_gesserit_sql(character_actor_id)
        output = run_psql(sql, timeout=60)
        log_action(session["user"], f"unlock advanced Bene Gesserit progression for actor {character_actor_id}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Advanced Bene Gesserit unlock failed: {exc}"}), 500


@app.route("/api/give-character-xp", methods=["POST"])
def api_give_character_xp():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    xp_amount = request.form.get("xp_amount", "").strip()

    try:
        sql = build_give_character_xp_sql(character_actor_id, xp_amount)
        output = run_psql(sql, timeout=60)
        log_action(
            session["user"],
            f"give {xp_amount} character XP to actor {character_actor_id}",
        )
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Character XP grant failed: {exc}"}), 500


@app.route("/api/set-character-level", methods=["POST"])
def api_set_character_level():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    target_level = request.form.get("target_level", "").strip()

    try:
        sql = build_set_character_level_sql(character_actor_id, target_level)
        output = run_psql(sql, timeout=60)
        log_action(
            session["user"],
            f"set character level actor {character_actor_id} to {target_level}",
        )
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Character level update failed: {exc}"}), 500


@app.route("/api/give-skill-points", methods=["POST"])
def api_give_skill_points():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    skill_points = request.form.get("skill_points", "").strip()

    try:
        sql = build_give_skill_points_sql(character_actor_id, skill_points)
        output = run_psql(sql, timeout=60)
        log_action(
            session["user"],
            f"give {skill_points} skill points to actor {character_actor_id}",
        )
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Skill point grant failed: {exc}"}), 500


@app.route("/api/progression-preset", methods=["POST"])
def api_progression_preset():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not has_developer_access():
        return jsonify({"ok": False, "error": "developer key required"}), 403

    fls_id = request.form.get("fls_id", "").strip()
    preset_id = request.form.get("preset_id", "").strip()
    action = request.form.get("action", "").strip()

    if not fls_id:
        return jsonify({"ok": False, "error": "missing player/FLS id"}), 400

    try:
        sql = build_progression_preset_sql(fls_id, preset_id, action)
        output = run_psql_script(sql, timeout=90)
        log_action(
            session["user"],
            f"{action} progression preset {preset_id} for {fls_id}",
        )
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Progression preset failed: {exc}"}), 500


@app.route("/api/give-scout-thopter", methods=["POST"])
def api_give_scout_thopter():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    player_id = request.form.get("player_id", "").strip()

    cmd = [
        str(DUNE_SCRIPT),
        "admin",
        "grant-template",
        player_id,
        SCOUT_THOPTER_TEMPLATE,
    ]

    try:
        output = run_command(cmd, timeout=60)
        log_action(session["user"], f"grant template {SCOUT_THOPTER_TEMPLATE} to {player_id}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Scout thopter grant failed: {exc}"}), 500


@app.route("/api/give-medium-thopter", methods=["POST"])
def api_give_medium_thopter():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    player_id = request.form.get("player_id", "").strip()

    outputs = []
    try:
        for item_id, qty in MEDIUM_THOPTER_BUNDLE:
            outputs.append(grant_item(player_id, item_id, qty, "1.0"))

        log_action(session["user"], f"grant Mk6 Medium thopter bundle to {player_id}")
        return jsonify({"ok": True, "output": "\n\n---\n\n".join(outputs)})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Medium thopter grant failed: {exc}"}), 500



@app.route("/api/vehicles")
def api_vehicles():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    return jsonify({"ok": True, "vehicles": get_vehicles()})


@app.route("/api/teleportable-vehicles")
def api_teleportable_vehicles():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    return jsonify({"ok": True, "vehicles": get_teleportable_vehicles()})


@app.route("/api/ornithopters")
def api_ornithopters():
    """
    Backward-compatible alias for browsers that still have older admin JS cached.
    New code should use /api/teleportable-vehicles.
    """
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    vehicles = get_teleportable_vehicles()
    return jsonify({"ok": True, "ornithopters": vehicles, "vehicles": vehicles})


@app.route("/api/repair-vehicle", methods=["POST"])
def api_repair_vehicle():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    # Direct vehicle module SQL mutation is admin-only.
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    vehicle_id = request.form.get("vehicle_id", "").strip()
    durability = request.form.get("durability", DEFAULT_VEHICLE_REPAIR_DURABILITY).strip()

    try:
        sql = build_vehicle_repair_sql(vehicle_id, durability)
        output = run_psql(sql, timeout=60)

        log_action(
            session["user"],
            f"repair vehicle {vehicle_id} module durability {durability}",
        )

        return jsonify({"ok": True, "output": output})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"Vehicle repair failed: {exc}"}), 500



@app.route("/api/teleport-vehicle", methods=["POST"])
def api_teleport_vehicle():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    # Vehicle ownership is not confirmed in the current schema. Even though
    # dune.actors has owner_account_id, observed vehicle rows may be null,
    # so this tool remains admin-only and must not be exposed to operators/VIPs.
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    actor_id = request.form.get("actor_id", "").strip()
    map_key = request.form.get("map_key", DEFAULT_MAP_KEY).strip()
    map_cfg = MAP_CONFIGS.get(map_key, MAP_CONFIGS[DEFAULT_MAP_KEY])
    partition_id = request.form.get("partition_id", str(map_cfg.get("default_partition_id", ""))).strip()
    x = request.form.get("x", "0").strip()
    y = request.form.get("y", "0").strip()
    z = request.form.get("z", "1000").strip()

    if not actor_id:
        return jsonify({"ok": False, "error": "missing vehicle actor ID"}), 400

    if not partition_id:
        return jsonify({"ok": False, "error": "missing partition ID"}), 400

    try:
        actor = get_teleportable_vehicle_actor(actor_id)
        sql = build_vehicle_teleport_sql(
            actor_id,
            actor["transform"],
            map_cfg.get("actor_map", map_cfg["key"]),
            partition_id,
            x,
            y,
            z,
        )
        output = run_psql(sql, timeout=60)

        log_action(
            session["user"],
            f"teleport vehicle actor {actor_id} map {map_cfg['key']} partition {partition_id} to ({x}, {y}, {z})",
        )

        return jsonify({"ok": True, "output": output})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"Vehicle teleport failed: {exc}"}), 500


@app.route("/api/delete-vehicle", methods=["POST"])
def api_delete_vehicle():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401

    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    actor_id = request.form.get("actor_id", "").strip()

    if not actor_id:
        return jsonify({"ok": False, "error": "missing vehicle actor ID"}), 400

    try:
        sql = build_vehicle_delete_sql(actor_id)
        output = run_psql(sql, timeout=60)

        log_action(session["user"], f"delete vehicle actor {actor_id}")

        return jsonify({"ok": True, "output": output})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"Vehicle delete failed: {exc}"}), 500


@app.route("/api/teleport-ornithopter", methods=["POST"])
def api_teleport_ornithopter():
    """
    Backward-compatible alias for cached admin pages from the thopter-only build.
    New code should use /api/teleport-vehicle.
    """
    return api_teleport_vehicle()


@app.route("/api/overrepair", methods=["POST"])
def api_overrepair():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    inventory_id = request.form.get("inventory_id", "").strip()
    durability = request.form.get("durability", DEFAULT_OVERREPAIR_DURABILITY).strip()

    try:
        sql = build_overrepair_sql(character_actor_id, inventory_id, durability)
        output = run_psql(sql, timeout=60)
        log_action(
            session["user"],
            f"overrepair actor {character_actor_id} inventory {inventory_id} durability {durability}",
        )
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Overrepair failed: {exc}"}), 500


@app.route("/api/overrepair-item", methods=["POST"])
def api_overrepair_item():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    character_actor_id = request.form.get("character_actor_id", "").strip()
    inventory_id = request.form.get("inventory_id", "").strip()
    item_row_id = request.form.get("item_row_id", "").strip()
    durability = request.form.get("durability", DEFAULT_OVERREPAIR_DURABILITY).strip()

    try:
        sql = build_overrepair_item_sql(
            character_actor_id,
            inventory_id,
            item_row_id,
            durability,
        )
        output = run_psql(sql, timeout=60)
        log_action(
            session["user"],
            f"overrepair one item actor {character_actor_id} inventory {inventory_id} item row {item_row_id} durability {durability}",
        )
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Single item overrepair failed: {exc}"}), 500


@app.route("/api/spawn-map", methods=["POST"])
def api_spawn_map():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    map_name = request.form.get("map_name", "").strip()
    if map_name not in MAPS:
        return jsonify({"ok": False, "error": "unknown map"}), 400

    try:
        output = run_command([str(DUNE_SCRIPT), "spawn", map_name], timeout=120)
        log_action(session["user"], f"spawn map {map_name}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Spawn failed: {exc}"}), 500


@app.route("/api/restart-target", methods=["POST"])
def api_restart_target():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    target = request.form.get("target", "").strip()
    if target not in RESTART_TARGETS:
        return jsonify({"ok": False, "error": "unknown restart target"}), 400

    if target in INFRASTRUCTURE_RESTART_TARGETS and not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        output = run_command([str(DUNE_SCRIPT), "restart", target], timeout=180)
        log_action(session["user"], f"restart target {target}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Restart failed: {exc}"}), 500



@app.route("/api/restart-map", methods=["POST"])
def api_restart_map():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    map_name = request.form.get("map_name", "").strip()
    allowed_maps = {"DeepDesert_1", "SH_Arrakeen", "SH_HarkoVillage"}

    if map_name not in allowed_maps:
        return jsonify({"ok": False, "error": "map restart not allowed"}), 400

    try:
        stop_output = run_command([str(DUNE_SCRIPT), "despawn", map_name, "--force"], timeout=180)
        start_output = run_command([str(DUNE_SCRIPT), "spawn", map_name], timeout=300)
        log_action(session["user"], f"restart map {map_name}")
        return jsonify({
            "ok": True,
            "output": "DESPAWN OUTPUT:\\n" + stop_output + "\\n\\nSPAWN OUTPUT:\\n" + start_output
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Map restart failed: {exc}"}), 500


@app.route("/api/db-command", methods=["POST"])
def api_db_command():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    action = request.form.get("action", "").strip()

    allowed = {
        "health": [str(DUNE_SCRIPT), "db", "health"],
        "status": [str(DUNE_SCRIPT), "db", "status"],
        "list": [str(DUNE_SCRIPT), "db", "list"],
        "backup": [str(DUNE_SCRIPT), "db", "backup"],
    }

    cmd = allowed.get(action)
    if not cmd:
        return jsonify({"ok": False, "error": "invalid database action"}), 400

    try:
        output = run_command(cmd, timeout=600)
        log_action(session["user"], f"dune db {action}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Database command failed: {exc}"}), 500


@app.route("/api/battlegroup-command", methods=["POST"])
def api_battlegroup_command():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    action = request.form.get("action", "").strip()
    allowed = {
        "status": {
            "cmd": [str(DUNE_SCRIPT), "status"],
            "timeout": 60,
            "admin": False,
        },
        "ready": {
            "cmd": [str(DUNE_SCRIPT), "ready"],
            "timeout": 60,
            "admin": False,
        },
        "version": {
            "cmd": [str(DUNE_SCRIPT), "version"],
            "timeout": 60,
            "admin": False,
        },
        "ports": {
            "cmd": [str(DUNE_SCRIPT), "ports"],
            "timeout": 60,
            "admin": False,
        },
        "ps": {
            "cmd": [str(DUNE_SCRIPT), "ps"],
            "timeout": 60,
            "admin": False,
        },
        "servers": {
            "cmd": [str(DUNE_SCRIPT), "servers"],
            "timeout": 60,
            "admin": False,
        },
        "doctor": {
            "cmd": [str(DUNE_SCRIPT), "doctor"],
            "timeout": 180,
            "admin": True,
        },
    }

    spec = allowed.get(action)
    if not spec:
        return jsonify({"ok": False, "error": "invalid battlegroup action"}), 400
    if spec["admin"] and not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        output = run_command(spec["cmd"], timeout=spec["timeout"])
        log_action(session["user"], f"dune {action}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Battlegroup command failed: {exc}"}), 500


@app.route("/api/autoscaler-command", methods=["POST"])
def api_autoscaler_command():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    action = request.form.get("action", "").strip()
    allowed = {
        "status": {"cmd": [str(DUNE_SCRIPT), "autoscaler", "status"], "timeout": 60, "admin": False},
        "logs": {"cmd": [str(DUNE_SCRIPT), "autoscaler", "logs"], "timeout": 60, "admin": False},
        "start": {"cmd": [str(DUNE_SCRIPT), "autoscaler", "start"], "timeout": 120, "admin": True},
        "stop": {"cmd": [str(DUNE_SCRIPT), "autoscaler", "stop"], "timeout": 120, "admin": True},
        "restart": {"cmd": [str(DUNE_SCRIPT), "autoscaler", "restart"], "timeout": 180, "admin": True},
    }

    spec = allowed.get(action)
    if not spec:
        return jsonify({"ok": False, "error": "invalid autoscaler action"}), 400
    if spec["admin"] and not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        output = run_command(spec["cmd"], timeout=spec["timeout"])
        log_action(session["user"], f"dune autoscaler {action}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Autoscaler command failed: {exc}"}), 500


@app.route("/api/sietches-command", methods=["POST"])
def api_sietches_command():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    action = request.form.get("action", "").strip()
    map_name = request.form.get("map_name", "").strip()

    if action == "list":
        cmd = [str(DUNE_SCRIPT), "sietches", "list"]
        timeout = 60
    elif action in ("show", "dimensions"):
        if not map_name:
            return jsonify({"ok": False, "error": "missing map name"}), 400
        cmd = [str(DUNE_SCRIPT), "sietches", action, map_name]
        timeout = 60
    elif action in ("sync", "validate"):
        if not is_admin():
            return jsonify({"ok": False, "error": "permission denied"}), 403
        cmd = [str(DUNE_SCRIPT), "sietches", action]
        timeout = 180
    else:
        return jsonify({"ok": False, "error": "invalid sietches action"}), 400

    try:
        output = run_command(cmd, timeout=timeout)
        log_action(session["user"], f"dune sietches {action} {map_name}".strip())
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Sietches command failed: {exc}"}), 500


@app.route("/api/memory-command", methods=["POST"])
def api_memory_command():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    action = request.form.get("action", "").strip()
    map_name = request.form.get("map_name", "").strip()
    memory_value = request.form.get("memory", "").strip()

    if action == "status":
        cmd = [str(DUNE_SCRIPT), "memory", "status"]
        timeout = 60
    elif action == "list-maps":
        cmd = [str(DUNE_SCRIPT), "memory", "list-maps"]
        timeout = 60
    elif action == "set":
        if not is_admin():
            return jsonify({"ok": False, "error": "permission denied"}), 403
        if not map_name or not memory_value:
            return jsonify({"ok": False, "error": "missing map name or memory"}), 400
        cmd = ["env", "DUNE_MEMORY_ASSUME_YES=1", str(DUNE_SCRIPT), "memory", "set", map_name, memory_value]
        timeout = 120
    elif action == "unset":
        if not is_admin():
            return jsonify({"ok": False, "error": "permission denied"}), 403
        if not map_name:
            return jsonify({"ok": False, "error": "missing map name"}), 400
        cmd = ["env", "DUNE_MEMORY_ASSUME_YES=1", str(DUNE_SCRIPT), "memory", "unset", map_name]
        timeout = 120
    else:
        return jsonify({"ok": False, "error": "invalid memory action"}), 400

    try:
        output = run_command(cmd, timeout=timeout)
        log_action(session["user"], f"dune memory {action} {map_name} {memory_value}".strip())
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Memory command failed: {exc}"}), 500


@app.route("/api/memory-maps")
def api_memory_maps():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        memory_output = run_command([str(DUNE_SCRIPT), "memory", "list-maps"], timeout=60)
        try:
            sietch_output = run_command([str(DUNE_SCRIPT), "sietches", "list"], timeout=60)
        except Exception:
            sietch_output = ""

        rows = parse_redblink_memory_maps(memory_output, sietch_output)
        return jsonify({"ok": True, "maps": rows, "raw_output": memory_output})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"Memory map discovery failed: {exc}"}), 500


@app.route("/api/update-command", methods=["POST"])
def api_update_command():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    action = request.form.get("action", "").strip()
    allowed = {
        "stack_check": ([str(DUNE_SCRIPT), "self-update", "check"], 180),
        "stack_list": ([str(DUNE_SCRIPT), "self-update", "list"], 180),
        "game_check": ([str(DUNE_SCRIPT), "update", "check"], 180),
        "game_auto_status": ([str(DUNE_SCRIPT), "update", "auto", "status"], 60),
        "restart_schedule_status": ([str(DUNE_SCRIPT), "restart-schedule", "status"], 60),
    }

    spec = allowed.get(action)
    if not spec:
        return jsonify({"ok": False, "error": "invalid update action"}), 400

    try:
        output = run_command(spec[0], timeout=spec[1])
        log_action(session["user"], f"dune update helper {action}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Update command failed: {exc}"}), 500


@app.route("/api/redblink-admin-command", methods=["POST"])
def api_redblink_admin_command():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    action = request.form.get("action", "").strip()
    player_id = request.form.get("player_id", "").strip()
    amount = request.form.get("amount", "").strip()
    query = request.form.get("query", "").strip()
    vehicle_id = request.form.get("vehicle_id", "").strip()
    template_name = request.form.get("template_name", "").strip()
    offset = request.form.get("offset", "400").strip()
    x = request.form.get("x", "").strip()
    y = request.form.get("y", "").strip()
    z = request.form.get("z", "").strip()
    rotation = request.form.get("rotation", "0").strip()
    module_id = request.form.get("module_id", "").strip()
    skill_level = request.form.get("skill_level", "").strip()
    kick_scope = request.form.get("kick_scope", "single").strip()
    force_kick = request.form.get("force", "").strip() == "1"

    def validate_float_value(raw_value, label):
        try:
            float(raw_value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number") from exc
        return raw_value

    if action == "players":
        cmd = [str(DUNE_SCRIPT), "admin", "players"]
    elif action == "players_online":
        cmd = [str(DUNE_SCRIPT), "admin", "players", "--online"]
    elif action == "vehicle_list":
        cmd = [str(DUNE_SCRIPT), "admin", "vehicle-list"]
    elif action == "history":
        cmd = [str(DUNE_SCRIPT), "admin", "history"]
    elif action == "player_location":
        if not player_id:
            return jsonify({"ok": False, "error": "missing player/FLS id"}), 400
        cmd = [str(DUNE_SCRIPT), "admin", "player-location", player_id]
    elif action == "refill_water":
        if not player_id:
            return jsonify({"ok": False, "error": "missing player/FLS id"}), 400
        cmd = ["env", "DUNE_ADMIN_ASSUME_YES=1", str(DUNE_SCRIPT), "admin", "refill-water", player_id]
        if amount:
            cmd.append(amount)
    elif action == "item_search":
        if not query:
            return jsonify({"ok": False, "error": "missing search query"}), 400
        cmd = [str(DUNE_SCRIPT), "admin", "item-search", query]
    elif action == "spawn_vehicle":
        if not player_id:
            return jsonify({"ok": False, "error": "missing player/FLS id"}), 400
        if vehicle_id not in REDBLINK_VEHICLE_SPAWN_TEMPLATES:
            return jsonify({"ok": False, "error": "invalid vehicle id"}), 400
        if template_name not in REDBLINK_VEHICLE_SPAWN_TEMPLATES[vehicle_id]:
            return jsonify({"ok": False, "error": "invalid template for selected vehicle"}), 400
        try:
            spawn_offset = int(offset)
        except ValueError:
            return jsonify({"ok": False, "error": "offset must be a whole number"}), 400
        if spawn_offset < 0 or spawn_offset > 5000:
            return jsonify({"ok": False, "error": "offset must be between 0 and 5000"}), 400
        cmd = [
            "env",
            "DUNE_ADMIN_ASSUME_YES=1",
            str(DUNE_SCRIPT),
            "admin",
            "spawn-vehicle",
            player_id,
            vehicle_id,
            template_name,
            str(spawn_offset),
        ]
    elif action == "spawn_vehicle_at":
        if not player_id:
            return jsonify({"ok": False, "error": "missing player/FLS id"}), 400
        if vehicle_id not in REDBLINK_VEHICLE_SPAWN_TEMPLATES:
            return jsonify({"ok": False, "error": "invalid vehicle id"}), 400
        if template_name not in REDBLINK_VEHICLE_SPAWN_TEMPLATES[vehicle_id]:
            return jsonify({"ok": False, "error": "invalid template for selected vehicle"}), 400
        try:
            valid_x = validate_float_value(x, "X")
            valid_y = validate_float_value(y, "Y")
            valid_z = validate_float_value(z, "Z")
            valid_rotation = validate_float_value(rotation or "0", "Rotation")
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        cmd = [
            "env",
            "DUNE_ADMIN_ASSUME_YES=1",
            str(DUNE_SCRIPT),
            "admin",
            "spawn-vehicle-at",
            player_id,
            vehicle_id,
            template_name,
            valid_x,
            valid_y,
            valid_z,
            valid_rotation,
        ]
    elif action == "skill_module":
        if not player_id:
            return jsonify({"ok": False, "error": "missing player/FLS id"}), 400
        if not module_id:
            return jsonify({"ok": False, "error": "missing skill module"}), 400
        skill_modules = load_redblink_skill_modules()
        module_by_id = {module["id"]: module for module in skill_modules}
        if skill_modules and module_id not in module_by_id:
            return jsonify({"ok": False, "error": "invalid skill module"}), 400
        try:
            level = int(skill_level)
        except ValueError:
            return jsonify({"ok": False, "error": "skill level must be a whole number"}), 400
        max_level = module_by_id.get(module_id, {}).get("maxLevel", 100)
        if level < 0 or level > max_level:
            return jsonify({"ok": False, "error": f"skill level must be between 0 and {max_level}"}), 400
        cmd = [
            "env",
            "DUNE_ADMIN_ASSUME_YES=1",
            str(DUNE_SCRIPT),
            "admin",
            "skill-module",
            player_id,
            module_id,
            str(level),
        ]
    elif action == "kick":
        if kick_scope == "all_online":
            cmd = [str(DUNE_SCRIPT), "admin", "kick", "--all-online", "--yes"]
        else:
            if not player_id:
                return jsonify({"ok": False, "error": "missing player/FLS id"}), 400
            cmd = [str(DUNE_SCRIPT), "admin", "kick", player_id, "--yes"]
            if force_kick:
                cmd.append("--force")
    else:
        return jsonify({"ok": False, "error": "invalid RedBlink admin action"}), 400

    try:
        input_text = "y\n" if action in ("refill_water", "spawn_vehicle", "spawn_vehicle_at") else None
        output = run_command(cmd, timeout=120, input_text=input_text)
        log_action(session["user"], f"dune admin {action}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"RedBlink admin command failed: {exc}"}), 500



@app.route("/api/maps-list", methods=["POST"])
def api_maps_list():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        output = run_command([str(DUNE_SCRIPT), "maps", "list"], timeout=60)
        log_action(session["user"], "dune maps list")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Map list failed: {exc}"}), 500


@app.route("/api/maps-mode", methods=["POST"])
def api_maps_mode():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    map_name = request.form.get("map_name", "").strip()

    try:
        cmd = [str(DUNE_SCRIPT), "maps", "mode"]
        if map_name:
            cmd.append(map_name)
        output = run_command(cmd, timeout=60)
        log_action(session["user"], f"dune maps mode {map_name or 'all'}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Map mode failed: {exc}"}), 500


@app.route("/api/maps-set-mode", methods=["POST"])
def api_maps_set_mode():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    map_name = request.form.get("map_name", "").strip()
    mode = request.form.get("mode", "").strip()

    if not map_name:
        return jsonify({"ok": False, "error": "missing map name"}), 400

    if mode not in ("dynamic", "always-on"):
        return jsonify({"ok": False, "error": "invalid map mode"}), 400

    try:
        output = run_command([str(DUNE_SCRIPT), "maps", "set", map_name, mode], timeout=120)
        log_action(session["user"], f"dune maps set {map_name} {mode}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Map set failed: {exc}"}), 500


@app.route("/api/maps-reconcile", methods=["POST"])
def api_maps_reconcile():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    try:
        output = run_command([str(DUNE_SCRIPT), "maps", "reconcile"], timeout=180)
        log_action(session["user"], "dune maps reconcile")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Map reconcile failed: {exc}"}), 500


@app.route("/api/deepdesert-dual", methods=["POST"])
def api_deepdesert_dual():
    if not logged_in():
        return jsonify({"ok": False, "error": "not logged in"}), 401
    if not is_operator_or_admin():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    action = request.form.get("action", "").strip()

    allowed = {
        "status": [str(DUNE_SCRIPT), "deepdesert", "dual", "status"],
        "enable": [str(DUNE_SCRIPT), "deepdesert", "dual", "enable", "--yes"],
        "disable": [str(DUNE_SCRIPT), "deepdesert", "dual", "disable", "--yes"],
        "disable_force": [str(DUNE_SCRIPT), "deepdesert", "dual", "disable", "--force", "--yes"],
        "bootstrap": [str(DUNE_SCRIPT), "deepdesert", "dual", "bootstrap", "--yes"],
        "repair": [str(DUNE_SCRIPT), "deepdesert", "dual", "repair"],
    }

    cmd = allowed.get(action)
    if not cmd:
        return jsonify({"ok": False, "error": "invalid Deep Desert dual action"}), 400

    try:
        output = run_command(cmd, timeout=300)
        log_action(session["user"], f"dune deepdesert dual {action}")
        return jsonify({"ok": True, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Deep Desert dual command failed: {exc}"}), 500




# =========================================================
# SOCKET.IO HOST SHELL
# =========================================================

@socketio.on("connect")
def socket_connect():
    if not logged_in() or not is_admin() or not ENABLE_HOST_SHELL:
        disconnect()
        return False

    if current_installation_mode() == "docker":
        emit("shell_output", {"data": "[connected to Easy Dune Admin container shell]\n"})
    elif current_installation_mode() == "hyperv":
        emit("shell_output", {"data": "[connected to local webadmin shell; use SSH for the Hyper-V VM shell]\n"})
    else:
        emit("shell_output", {"data": "[connected to host shell]\n"})


@socketio.on("shell_start")
def socket_shell_start():
    if not logged_in() or not is_admin() or not ENABLE_HOST_SHELL:
        disconnect()
        return

    log_action(session.get("user", "unknown"), "started host shell session")
    start_shell_session(request.sid)


@socketio.on("shell_input")
def socket_shell_input(message):
    if not logged_in() or not is_admin() or not ENABLE_HOST_SHELL:
        disconnect()
        return

    session_obj = SHELL_SESSIONS.get(request.sid)
    if not session_obj:
        return

    data = message.get("data", "")
    os.write(session_obj["fd"], data.encode())


@socketio.on("shell_resize")
def socket_shell_resize(message):
    if not logged_in() or not is_admin() or not ENABLE_HOST_SHELL:
        disconnect()
        return

    session_obj = SHELL_SESSIONS.get(request.sid)
    if not session_obj:
        return

    try:
        rows = int(message.get("rows", 24))
        cols = int(message.get("cols", 80))
        rows = max(10, min(rows, 200))
        cols = max(40, min(cols, 400))

        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(session_obj["fd"], termios.TIOCSWINSZ, winsize)
    except Exception:
        return


@socketio.on("disconnect")
def socket_disconnect():
    stop_shell_session(request.sid)
