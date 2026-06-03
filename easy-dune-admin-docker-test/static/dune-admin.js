let latestCharacters = [];

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function showOutput(text, sourceElement = null) {
    const output = document.getElementById("actionOutput");
    if (output) {
        output.style.display = "block";
        output.textContent = text;
    }

    if (sourceElement && sourceElement instanceof Element) {
        showLocalOutput(sourceElement, text);
    }
}

function showLocalOutput(form, text) {
    if (!form) return;

    const panel = form.closest(".box, .card, .map-panel, .selected");
    if (!panel) return;

    let output = panel.querySelector(":scope > .local-action-output");
    if (!output) {
        output = document.createElement("div");
        output.className = "msg local-action-output";
        panel.appendChild(output);
    }

    output.style.display = "block";
    output.textContent = text;
}

async function postForm(endpoint, form) {
    const data = new FormData(form);

    const response = await fetch(endpoint, {
        method: "POST",
        body: data
    });

    const json = await response.json();

    if (!json.ok) {
        const message = json.error || "Action failed.";
        showOutput(message);
        showLocalOutput(form, message);
        return;
    }

    const message = json.output || "Action completed.";
    showOutput(message);
    showLocalOutput(form, message);
}

function wireAjaxForms() {
    document.querySelectorAll(".ajaxForm").forEach(form => {
        form.addEventListener("submit", async function(event) {
            event.preventDefault();
            await postForm(form.dataset.endpoint, form);
        });
    });
}

async function refreshLogs() {
    const panel = document.getElementById("logOutput");
    if (!panel) return;

    const response = await fetch("/api/logs");
    const data = await response.json();

    if (!data.ok) {
        panel.textContent = data.error || "Unable to refresh logs.";
        return;
    }

    panel.textContent = data.lines.join("\n");
}

async function fetchCharacters(includeOffline = true) {
    const response = await fetch(`/api/characters?include_offline=${includeOffline ? "1" : "0"}`);
    const data = await response.json();
    latestCharacters = data.characters || [];
    return latestCharacters;
}

function characterLabel(c, includeIds = true) {
    const status = c.online_status || "Unknown";
    const name = c.character_name || "Unknown";
    if (!includeIds || !c.fls_id) {
        return `[${status}] ${name}`;
    }
    return `[${status}] ${name} | FLS ${c.fls_id} | Actor ${c.character_actor_id || ""} | Inv ${c.inventory_id || ""}`;
}

function fillCharacterSelect(selectId, characters, includeIds = true) {
    const select = document.getElementById(selectId);
    if (!select) return;

    select.innerHTML = `<option value="">Select a character...</option>`;

    characters.forEach((c, index) => {
        const opt = document.createElement("option");
        opt.value = String(index);
        opt.textContent = characterLabel(c, includeIds);
        select.appendChild(opt);
    });
}

async function loadMemoryMapOptions() {
    const setSelect = document.getElementById("memorySetMapSelect");
    const unsetSelect = document.getElementById("memoryUnsetMapSelect");
    const selects = [setSelect, unsetSelect].filter(Boolean);
    if (selects.length === 0) return;

    const setFallback = (message) => {
        selects.forEach(select => {
            select.innerHTML = "";
            const opt = document.createElement("option");
            opt.value = "Survival_1";
            opt.textContent = message || "Survival_1 | discovery unavailable";
            select.appendChild(opt);
        });
    };

    try {
        const response = await fetch("/api/memory-maps");
        const data = await response.json();
        if (!data.ok) {
            setFallback(data.error || "Survival_1 | memory map discovery failed");
            return;
        }

        const maps = data.maps || [];
        if (maps.length === 0) {
            setFallback("Survival_1 | no memory maps reported");
            return;
        }

        selects.forEach(select => {
            const current = select.value;
            select.innerHTML = "";
            maps.forEach(row => {
                const opt = document.createElement("option");
                opt.value = row.map_name || "";
                opt.textContent = row.label || row.map_name || "Unknown map";
                select.appendChild(opt);
            });
            if (current && maps.some(row => row.map_name === current)) {
                select.value = current;
            }
        });
    } catch (err) {
        setFallback("Survival_1 | memory map discovery failed");
    }
}

async function refreshOnlinePlayers() {
    const panel = document.getElementById("onlinePlayers");
    if (!panel) return;

    try {
        const response = await fetch("/api/online-players");
        const data = await response.json();

        const players = data.players || [];

        if (players.length === 0) {
            panel.innerHTML = "No players online.";
            return;
        }

        panel.innerHTML = renderOnlinePlayersTable(players);

    } catch (err) {
        panel.innerHTML =
            `<span class="status-bad">Failed to refresh online players.</span>`;
    }
}

function renderOnlinePlayersTable(players) {
    return `
        <div class="online-table-wrap">
        <table class="online-table">
            <thead>
                <tr>
                    <th>Character</th>
                    <th>Status</th>
                    <th>Funcom ID</th>
                    <th>Map</th>
                    <th>Partition</th>
                </tr>
            </thead>
            <tbody>
                ${players.map(player => `
                    <tr>
                        <td>${escapeHtml(player.character_name || "")}</td>
                        <td>${escapeHtml(player.online_status || "")} / ${escapeHtml(player.life_state || "")}</td>
                        <td>${escapeHtml(player.funcom_id || "")}</td>
                        <td>${escapeHtml(player.map || "")}</td>
                        <td>${escapeHtml(player.partition_id || "")}</td>
                    </tr>
                `).join("")}
            </tbody>
        </table>
        </div>
    `;
}

async function loadCharactersForGrantPage() {
    const chars = await fetchCharacters(true);

    fillCharacterSelect("grantCharacterSelect", chars);
    fillCharacterSelect("scoutCharacterSelect", chars);
    fillCharacterSelect("mediumCharacterSelect", chars);
}

async function loadCharactersForAdminPage() {
    const chars = await fetchCharacters(true);
    fillCharacterSelect("overrepairCharacterSelect", chars);
    fillCharacterSelect("overrepairItemCharacterSelect", chars);
    fillCharacterSelect("inventoryBrowserCharacterSelect", chars);
    fillCharacterSelect("lasgunCharacterSelect", chars);
    fillCharacterSelect("redblinkWaterCharacterSelect", chars);
    fillCharacterSelect("redblinkVehicleCharacterSelect", chars);
    fillCharacterSelect("redblinkVehicleAtCharacterSelect", chars);
    fillCharacterSelect("redblinkLocationCharacterSelect", chars);
    fillCharacterSelect("redblinkSkillModuleCharacterSelect", chars);
    fillCharacterSelect("redblinkKickCharacterSelect", chars);
    fillCharacterSelect("researchCharacterSelect", chars);
    fillCharacterSelect("characterXpCharacterSelect", chars);
    fillCharacterSelect("characterLevelCharacterSelect", chars);
    fillCharacterSelect("skillPointsCharacterSelect", chars);
    fillCharacterSelect("xpCharacterSelect", chars);
    fillCharacterSelect("specializationGrantAllCharacterSelect", chars);
    fillCharacterSelect("specializationMaxCharacterSelect", chars);
    fillCharacterSelect("specializationResetCharacterSelect", chars);
    fillCharacterSelect("classProgressionCharacterSelect", chars);
    fillCharacterSelect("progressionCharacterSelect", chars);
    fillCharacterSelect("solariCharacterSelect", chars);
    fillCharacterSelect("solariBankCharacterSelect", chars);
    fillCharacterSelect("exchangeBankSolariCharacterSelect", chars);
}

function fillGrantPlayerId() {
    const sel = document.getElementById("grantCharacterSelect");
    const input = document.getElementById("grantPlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

function fillScoutPlayerId() {
    const sel = document.getElementById("scoutCharacterSelect");
    const input = document.getElementById("scoutPlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

function fillMediumPlayerId() {
    const sel = document.getElementById("mediumCharacterSelect");
    const input = document.getElementById("mediumPlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

function fillOverrepairFields() {
    const sel = document.getElementById("overrepairCharacterSelect");
    const c = latestCharacters[Number(sel.value)];
    if (!c) return;

    const actorInput = document.getElementById("overrepairActorId");
    const inventoryInput = document.getElementById("overrepairInventoryId");

    if (actorInput) actorInput.value = c.character_actor_id || "";
    if (inventoryInput) inventoryInput.value = c.inventory_id || "";
}

function resetOverrepairItemPickers(inventoryMessage = "Select a character first...", itemMessage = "Select an inventory first...") {
    const inventorySelect = document.getElementById("overrepairItemInventorySelect");
    const itemSelect = document.getElementById("overrepairItemSelect");

    if (inventorySelect) {
        inventorySelect.innerHTML = `<option value="">${escapeHtml(inventoryMessage)}</option>`;
    }

    if (itemSelect) {
        itemSelect.innerHTML = `<option value="">${escapeHtml(itemMessage)}</option>`;
    }
}

async function fillOverrepairItemCharacterFields() {
    const sel = document.getElementById("overrepairItemCharacterSelect");
    const c = latestCharacters[Number(sel.value)];
    const actorInput = document.getElementById("overrepairItemActorId");

    if (!c) {
        if (actorInput) actorInput.value = "";
        resetOverrepairItemPickers();
        return;
    }

    if (actorInput) actorInput.value = c.character_actor_id || "";
    await loadOverrepairInventories();
}

async function loadOverrepairInventories() {
    const actorInput = document.getElementById("overrepairItemActorId");
    const inventorySelect = document.getElementById("overrepairItemInventorySelect");
    const itemSelect = document.getElementById("overrepairItemSelect");
    const actorId = actorInput ? actorInput.value.trim() : "";

    if (!inventorySelect || !actorId) {
        resetOverrepairItemPickers();
        return;
    }

    inventorySelect.innerHTML = `<option value="">Loading inventories...</option>`;
    if (itemSelect) itemSelect.innerHTML = `<option value="">Select an inventory first...</option>`;

    try {
        const response = await fetch(`/api/character-inventories?character_actor_id=${encodeURIComponent(actorId)}`);
        const data = await response.json();

        if (!data.ok) {
            inventorySelect.innerHTML = `<option value="">${escapeHtml(data.error || "Inventory lookup failed.")}</option>`;
            return;
        }

        const inventories = data.inventories || [];
        if (inventories.length === 0) {
            inventorySelect.innerHTML = `<option value="">No inventories found.</option>`;
            return;
        }

        inventorySelect.innerHTML = `<option value="">Select an inventory...</option>`;
        inventories.forEach(inv => {
            const opt = document.createElement("option");
            opt.value = inv.inventory_id || "";
            opt.textContent = `${inv.inventory_label || "Inventory"} | ID ${inv.inventory_id || ""} | Items ${inv.item_count || "0"}`;
            inventorySelect.appendChild(opt);
        });
    } catch (err) {
        inventorySelect.innerHTML = `<option value="">Inventory lookup failed.</option>`;
    }
}

async function loadOverrepairInventoryItems() {
    const actorInput = document.getElementById("overrepairItemActorId");
    const inventorySelect = document.getElementById("overrepairItemInventorySelect");
    const itemSelect = document.getElementById("overrepairItemSelect");
    const actorId = actorInput ? actorInput.value.trim() : "";
    const inventoryId = inventorySelect ? inventorySelect.value.trim() : "";

    if (!itemSelect || !actorId || !inventoryId) {
        if (itemSelect) itemSelect.innerHTML = `<option value="">Select an inventory first...</option>`;
        return;
    }

    itemSelect.innerHTML = `<option value="">Loading items...</option>`;

    try {
        const url = `/api/character-inventory-items?character_actor_id=${encodeURIComponent(actorId)}&inventory_id=${encodeURIComponent(inventoryId)}`;
        const response = await fetch(url);
        const data = await response.json();

        if (!data.ok) {
            itemSelect.innerHTML = `<option value="">${escapeHtml(data.error || "Item lookup failed.")}</option>`;
            return;
        }

        const items = data.items || [];
        if (items.length === 0) {
            itemSelect.innerHTML = `<option value="">No items found.</option>`;
            return;
        }

        itemSelect.innerHTML = `<option value="">Select an item...</option>`;
        items.forEach(item => {
            const opt = document.createElement("option");
            opt.value = item.item_row_id || "";
            const durability = item.current_durability
                ? ` | Dur ${item.current_durability}/${item.max_durability || "missing max"}`
                : " | No current durability";
            opt.textContent =
                `Pos ${item.position_index || "?"} | Row ${item.item_row_id || ""} | ${item.template_id || "Unknown item"} | QL ${item.quality_level || "?"} | Stack ${item.stack_size || "?"}${durability}`;
            itemSelect.appendChild(opt);
        });
    } catch (err) {
        itemSelect.innerHTML = `<option value="">Item lookup failed.</option>`;
    }
}

function resetInventoryBrowser(inventoryMessage = "Select a character first...", summaryMessage = "Select a character to inspect inventories.") {
    const inventorySelect = document.getElementById("inventoryBrowserInventorySelect");
    const summary = document.getElementById("inventoryBrowserSummary");
    const tableWrap = document.getElementById("inventoryBrowserTableWrap");
    const tbody = document.getElementById("inventoryBrowserTableBody");

    if (inventorySelect) {
        inventorySelect.innerHTML = `<option value="">${escapeHtml(inventoryMessage)}</option>`;
    }
    if (summary) {
        summary.textContent = summaryMessage;
    }
    if (tbody) {
        tbody.innerHTML = "";
    }
    if (tableWrap) {
        tableWrap.style.display = "none";
    }
}

async function fillInventoryBrowserCharacterFields() {
    const sel = document.getElementById("inventoryBrowserCharacterSelect");
    const actorInput = document.getElementById("inventoryBrowserActorId");
    const c = latestCharacters[Number(sel.value)];

    if (!c) {
        if (actorInput) actorInput.value = "";
        resetInventoryBrowser();
        return;
    }

    if (actorInput) actorInput.value = c.character_actor_id || "";
    await loadInventoryBrowserInventories();
}

async function loadInventoryBrowserInventories() {
    const actorInput = document.getElementById("inventoryBrowserActorId");
    const inventorySelect = document.getElementById("inventoryBrowserInventorySelect");
    const summary = document.getElementById("inventoryBrowserSummary");
    const actorId = actorInput ? actorInput.value.trim() : "";

    if (!inventorySelect || !actorId) {
        resetInventoryBrowser();
        return;
    }

    inventorySelect.innerHTML = `<option value="">Loading inventories...</option>`;
    if (summary) summary.textContent = "Loading character inventories...";

    try {
        const response = await fetch(`/api/character-inventories?character_actor_id=${encodeURIComponent(actorId)}`);
        const data = await response.json();

        if (!data.ok) {
            resetInventoryBrowser(data.error || "Inventory lookup failed.", data.error || "Inventory lookup failed.");
            return;
        }

        const inventories = data.inventories || [];
        if (inventories.length === 0) {
            resetInventoryBrowser("No inventories found.", "No inventories found for this character.");
            return;
        }

        inventorySelect.innerHTML = `<option value="">Select an inventory...</option>`;
        inventories.forEach(inv => {
            const opt = document.createElement("option");
            opt.value = inv.inventory_id || "";
            opt.textContent = `${inv.inventory_label || "Inventory"} | ID ${inv.inventory_id || ""} | Items ${inv.item_count || "0"}`;
            inventorySelect.appendChild(opt);
        });

        if (summary) {
            summary.textContent = `${inventories.length} inventor${inventories.length === 1 ? "y" : "ies"} found. Select one to list items.`;
        }
    } catch (err) {
        resetInventoryBrowser("Inventory lookup failed.", "Inventory lookup failed.");
    }
}

async function loadInventoryBrowserItems() {
    const actorInput = document.getElementById("inventoryBrowserActorId");
    const inventorySelect = document.getElementById("inventoryBrowserInventorySelect");
    const summary = document.getElementById("inventoryBrowserSummary");
    const tableWrap = document.getElementById("inventoryBrowserTableWrap");
    const tbody = document.getElementById("inventoryBrowserTableBody");
    const actorId = actorInput ? actorInput.value.trim() : "";
    const inventoryId = inventorySelect ? inventorySelect.value.trim() : "";
    const inventoryLabel = inventorySelect && inventorySelect.selectedOptions.length
        ? inventorySelect.selectedOptions[0].textContent
        : "";

    if (!actorId || !inventoryId || !tbody) {
        if (summary) summary.textContent = "Select an inventory to list items.";
        if (tableWrap) tableWrap.style.display = "none";
        return;
    }

    tbody.innerHTML = "";
    if (tableWrap) tableWrap.style.display = "none";
    if (summary) summary.textContent = "Loading inventory items...";

    try {
        const url = `/api/character-inventory-items?character_actor_id=${encodeURIComponent(actorId)}&inventory_id=${encodeURIComponent(inventoryId)}`;
        const response = await fetch(url);
        const data = await response.json();

        if (!data.ok) {
            if (summary) summary.textContent = data.error || "Item lookup failed.";
            return;
        }

        const items = data.items || [];
        if (summary) {
            summary.textContent = `${inventoryLabel || `Inventory ${inventoryId}`}: ${items.length} item row(s).`;
        }

        if (items.length === 0) {
            if (tableWrap) tableWrap.style.display = "none";
            return;
        }

        tbody.innerHTML = items.map(item => {
            const durability = item.current_durability
                ? `${item.current_durability}/${item.max_durability || item.decayed_max_durability || "?"}`
                : "No current durability";
            return `
                <tr>
                    <td>${escapeHtml(item.position_index || "")}</td>
                    <td>${escapeHtml(item.item_row_id || "")}</td>
                    <td>${escapeHtml(item.template_id || "")}</td>
                    <td>${escapeHtml(item.stack_size || "")}</td>
                    <td>${escapeHtml(item.quality_level || "")}</td>
                    <td>${escapeHtml(durability)}</td>
                </tr>
            `;
        }).join("");

        if (tableWrap) tableWrap.style.display = "block";
    } catch (err) {
        if (summary) summary.textContent = "Item lookup failed.";
        if (tableWrap) tableWrap.style.display = "none";
    }
}

function fillLasgunPlayerId() {
    const sel = document.getElementById("lasgunCharacterSelect");
    const input = document.getElementById("lasgunPlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

function fillRedblinkWaterPlayerId() {
    const sel = document.getElementById("redblinkWaterCharacterSelect");
    const input = document.getElementById("redblinkWaterPlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

function fillRedblinkVehiclePlayerId() {
    const sel = document.getElementById("redblinkVehicleCharacterSelect");
    const input = document.getElementById("redblinkVehiclePlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

function fillRedblinkVehicleAtPlayerId() {
    const sel = document.getElementById("redblinkVehicleAtCharacterSelect");
    const input = document.getElementById("redblinkVehicleAtPlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

function fillRedblinkLocationPlayerId() {
    const sel = document.getElementById("redblinkLocationCharacterSelect");
    const input = document.getElementById("redblinkLocationPlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

function fillRedblinkSkillModulePlayerId() {
    const sel = document.getElementById("redblinkSkillModuleCharacterSelect");
    const input = document.getElementById("redblinkSkillModulePlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

function fillRedblinkKickPlayerId() {
    const sel = document.getElementById("redblinkKickCharacterSelect");
    const input = document.getElementById("redblinkKickPlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

function populateRedblinkVehicleTemplates() {
    const vehicleSelect = document.getElementById("redblinkVehicleId");
    const templateSelect = document.getElementById("redblinkVehicleTemplate");
    if (!vehicleSelect || !templateSelect || typeof redblinkVehicleSpawnTemplates === "undefined") return;

    const vehicleId = vehicleSelect.value;
    const templates = redblinkVehicleSpawnTemplates[vehicleId] || [];
    templateSelect.innerHTML = "";

    if (templates.length === 0) {
        templateSelect.innerHTML = `<option value="">No templates found.</option>`;
        return;
    }

    templates.forEach(templateName => {
        const opt = document.createElement("option");
        opt.value = templateName;
        opt.textContent = templateName;
        templateSelect.appendChild(opt);
    });
}

function populateRedblinkVehicleAtTemplates() {
    const vehicleSelect = document.getElementById("redblinkVehicleAtId");
    const templateSelect = document.getElementById("redblinkVehicleAtTemplate");
    if (!vehicleSelect || !templateSelect || typeof redblinkVehicleSpawnTemplates === "undefined") return;

    const vehicleId = vehicleSelect.value;
    const templates = redblinkVehicleSpawnTemplates[vehicleId] || [];
    templateSelect.innerHTML = "";

    if (templates.length === 0) {
        templateSelect.innerHTML = `<option value="">No templates found.</option>`;
        return;
    }

    templates.forEach(templateName => {
        const opt = document.createElement("option");
        opt.value = templateName;
        opt.textContent = templateName;
        templateSelect.appendChild(opt);
    });
}

function syncRedblinkSkillModuleLevel() {
    const select = document.getElementById("redblinkSkillModuleId");
    const input = document.getElementById("redblinkSkillModuleLevel");
    if (!select || !input || select.selectedOptions.length === 0) return;

    const maxLevel = Number(select.selectedOptions[0].dataset.maxLevel || "1");
    input.max = String(maxLevel);
    if (Number(input.value || "0") > maxLevel) {
        input.value = String(maxLevel);
    }
    if (input.value === "") {
        input.value = String(maxLevel > 0 ? maxLevel : 0);
    }
}

function syncRedblinkKickScope() {
    const scope = document.getElementById("redblinkKickScope");
    const characterSelect = document.getElementById("redblinkKickCharacterSelect");
    const playerInput = document.getElementById("redblinkKickPlayerId");
    const allOnline = scope && scope.value === "all_online";

    if (characterSelect) characterSelect.disabled = allOnline;
    if (playerInput) {
        playerInput.disabled = allOnline;
        playerInput.required = !allOnline;
        if (allOnline) playerInput.value = "";
    }
}

function fillResearchActorId() {
    const sel = document.getElementById("researchCharacterSelect");
    const input = document.getElementById("researchActorId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.character_actor_id || "";
}

function fillCharacterXpActorId() {
    const sel = document.getElementById("characterXpCharacterSelect");
    const input = document.getElementById("characterXpActorId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.character_actor_id || "";
}

function fillCharacterLevelActorId() {
    const sel = document.getElementById("characterLevelCharacterSelect");
    const input = document.getElementById("characterLevelActorId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.character_actor_id || "";
}

function fillSkillPointsActorId() {
    const sel = document.getElementById("skillPointsCharacterSelect");
    const input = document.getElementById("skillPointsActorId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.character_actor_id || "";
}

function fillXpActorId() {
    const sel = document.getElementById("xpCharacterSelect");
    const input = document.getElementById("xpActorId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.character_actor_id || "";
}

function fillSpecializationMaxActorId() {
    const sel = document.getElementById("specializationMaxCharacterSelect");
    const input = document.getElementById("specializationMaxActorId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.character_actor_id || "";
}

function fillSpecializationGrantAllActorId() {
    const sel = document.getElementById("specializationGrantAllCharacterSelect");
    const input = document.getElementById("specializationGrantAllActorId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.character_actor_id || "";
}

function fillSpecializationResetActorId() {
    const sel = document.getElementById("specializationResetCharacterSelect");
    const input = document.getElementById("specializationResetActorId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.character_actor_id || "";
}

function fillClassProgressionActorId() {
    const sel = document.getElementById("classProgressionCharacterSelect");
    const input = document.getElementById("classProgressionActorId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.character_actor_id || "";
}

function fillProgressionPlayerId() {
    const sel = document.getElementById("progressionCharacterSelect");
    const input = document.getElementById("progressionPlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

function fillSolariPlayerId() {
    const sel = document.getElementById("solariCharacterSelect");
    const input = document.getElementById("solariPlayerId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.fls_id || "";
}

async function fillSolariBankActorId() {
    const sel = document.getElementById("solariBankCharacterSelect");
    const input = document.getElementById("solariBankActorId");
    const c = latestCharacters[Number(sel.value)];
    if (input && c) input.value = c.character_actor_id || "";
    syncSolariBankActorIds();
    await refreshSolariBankBalance();
}

async function fillExchangeBankSolariActorId() {
    const sel = document.getElementById("exchangeBankSolariCharacterSelect");
    const actorInput = document.getElementById("exchangeBankSolariActorId");
    const controllerInput = document.getElementById("exchangeBankSolariControllerId");
    const c = latestCharacters[Number(sel.value)];
    if (actorInput && c) actorInput.value = c.character_actor_id || "";
    if (controllerInput && c) controllerInput.value = c.player_controller_id || "";
    syncExchangeBankSolariActorIds();
    await refreshExchangeBankSolariBalance();
}

function syncSolariBankActorIds() {
    const actorInput = document.getElementById("solariBankActorId");
    const addActor = document.getElementById("solariBankAddActorId");
    const setActor = document.getElementById("solariBankSetActorId");
    const actorId = actorInput ? actorInput.value.trim() : "";
    if (addActor) addActor.value = actorId;
    if (setActor) setActor.value = actorId;
}

function syncExchangeBankSolariActorIds() {
    const actorInput = document.getElementById("exchangeBankSolariActorId");
    const controllerInput = document.getElementById("exchangeBankSolariControllerId");
    const addActor = document.getElementById("exchangeBankSolariAddActorId");
    const setActor = document.getElementById("exchangeBankSolariSetActorId");
    const addController = document.getElementById("exchangeBankSolariAddControllerId");
    const setController = document.getElementById("exchangeBankSolariSetControllerId");
    const actorId = actorInput ? actorInput.value.trim() : "";
    const controllerId = controllerInput ? controllerInput.value.trim() : "";
    if (addActor) addActor.value = actorId;
    if (setActor) setActor.value = actorId;
    if (addController) addController.value = controllerId;
    if (setController) setController.value = controllerId;
}

async function refreshSolariBankBalance() {
    const actorInput = document.getElementById("solariBankActorId");
    const panel = document.getElementById("solariBankBalance");
    const actorId = actorInput ? actorInput.value.trim() : "";
    syncSolariBankActorIds();

    if (!panel) return;
    if (!actorId) {
        panel.textContent = "Select a character to load Solari Coin.";
        return;
    }

    try {
        const response = await fetch(`/api/solari-bank-balance?character_actor_id=${encodeURIComponent(actorId)}`);
        const data = await response.json();
        if (!data.ok) {
            panel.textContent = data.error || "Unable to load Solari Coin.";
            return;
        }

        const balance = data.balance || {};
        const amount = Number(balance.solari_balance || 0).toLocaleString();
        const stackCount = Number(balance.stack_count || 0).toLocaleString();
        const stackDetail = balance.stacks ? `\nStacks: ${balance.stacks}` : "";
        panel.textContent =
            `${balance.character_name || "Character"} Solari Coin: ${amount}\n`
            + `Solari Coin stack rows: ${stackCount}${stackDetail}`;
    } catch (err) {
        panel.textContent = "Unable to load Solari Coin.";
    }
}

async function refreshExchangeBankSolariBalance() {
    const actorInput = document.getElementById("exchangeBankSolariActorId");
    const controllerInput = document.getElementById("exchangeBankSolariControllerId");
    const panel = document.getElementById("exchangeBankSolariBalance");
    const actorId = actorInput ? actorInput.value.trim() : "";
    const controllerId = controllerInput ? controllerInput.value.trim() : "";
    syncExchangeBankSolariActorIds();

    if (!panel) return;
    if (!actorId && !controllerId) {
        panel.textContent = "Select a character to load Solari Credit.";
        return;
    }

    try {
        const params = new URLSearchParams();
        if (controllerId) params.set("player_controller_id", controllerId);
        if (actorId) params.set("character_actor_id", actorId);
        panel.textContent = "Loading Solari Credit...";
        const response = await fetch(`/api/exchange-bank-solari-balance?${params.toString()}`);
        const data = await response.json();
        if (!data.ok) {
            panel.textContent = data.error || "Unable to load Solari Credit.";
            return;
        }

        const balance = data.balance || {};
        const amount = Number(balance.exchange_bank_solari || 0).toLocaleString();
        panel.textContent =
            `${balance.character_name || "Character"} Solari Credit: ${amount}\n`
            + `Player Controller ID: ${balance.player_controller_id || ""}\n`
            + `Balance row: ${balance.balance_row || ""}`;
    } catch (err) {
        panel.textContent = "Unable to load Solari Credit.";
    }
}

async function searchItems() {
    const query = document.getElementById("itemSearchQuery").value || "";
    const resultsPanel = document.getElementById("itemSearchResults");

    const response = await fetch(`/api/item-search?q=${encodeURIComponent(query)}`);
    const data = await response.json();

    const items = data.items || [];

    if (items.length === 0) {
        resultsPanel.innerHTML = "No items found.";
        return;
    }

    resultsPanel.innerHTML = items.map(item => {
        const id = item.id || "";
        const name = item.name || id;
        const cat = item.category || "";
        const source = item.source || "";

        return `
            <div class="item">
                <b>${escapeHtml(name)}</b><br>
                ID:
                <a href="#" onclick="selectItem('${escapeHtml(id)}'); return false;">
                    ${escapeHtml(id)}
                </a><br>
                Category: ${escapeHtml(cat)}<br>
                Source: ${escapeHtml(source)}
            </div>
        `;
    }).join("");
}

function selectItem(itemId) {
    const input = document.getElementById("grantItemId");
    if (input) input.value = itemId;

    const selected = document.getElementById("selectedItemNotice");
    if (selected) {
        selected.textContent = `Selected Item: ${itemId}`;
        selected.style.display = "block";
    }
}


async function loadMarketPresetPreview() {
    const panel = document.getElementById("marketPresetPreview");
    if (!panel) return;

    try {
        const multiplierInput = document.getElementById("marketPriceMultiplier");
        const multiplier = multiplierInput ? multiplierInput.value || "1" : "1";
        const response = await fetch(`/api/market-preset-preview?price_multiplier=${encodeURIComponent(multiplier)}`);
        const data = await response.json();

        if (!data.ok) {
            panel.textContent = data.error || "Unable to load market seed preview.";
            return;
        }

        const summary = data.summary || {};
        panel.textContent =
            `Listings: ${summary.listings || 0}\n`
            + `Equippable listings: ${summary.equippable_listings || 0}\n`
            + `Schematic listings: ${summary.schematic_listings || 0}\n`
            + `Resource listings: ${summary.resource_listings || 0}\n`
            + `Ammunition listings: ${summary.ammunition_listings || 0}\n`
            + `Consumable listings: ${summary.consumable_listings || 0}\n`
            + `Utility listings: ${summary.utility_listings || 0}\n`
            + `Cartography listings: ${summary.cartography_listings || 0}\n`
            + `Resource units: ${summary.resource_units || 0}\n`
            + `Boosted wing/track/locomotion listings: ${summary.special_boosted_listings || 0}\n`
            + `Price multiplier: ${summary.price_multiplier || 1}x`;
    } catch (err) {
        panel.textContent = "Unable to load market seed preview.";
    }
}


async function loadMarketExchanges() {
    const select = document.getElementById("marketSeedExchangeId");
    if (!select) return;

    const configuredDefault = String(select.dataset.defaultExchangeId || "").trim();
    select.innerHTML = `<option value="">Loading exchanges...</option>`;

    try {
        const response = await fetch("/api/market-exchanges");
        const data = await response.json();

        if (!data.ok) {
            select.innerHTML = `<option value="${escapeHtml(configuredDefault)}">${configuredDefault ? `Configured exchange ${configuredDefault}` : "Default Global exchange"}</option>`;
            return;
        }

        const exchanges = data.exchanges || [];
        select.innerHTML = "";

        if (exchanges.length === 0) {
            const opt = document.createElement("option");
            opt.value = configuredDefault;
            opt.textContent = configuredDefault
                ? `Configured exchange ${configuredDefault}`
                : "Default Global exchange";
            select.appendChild(opt);
            return;
        }

        exchanges.forEach(exchange => {
            const opt = document.createElement("option");
            opt.value = exchange.exchange_id || "";
            const accessPoint = exchange.access_point_id ? ` | access ${exchange.access_point_id}` : "";
            opt.textContent =
                `${exchange.label || "Exchange"} | ID ${exchange.exchange_id || ""}${accessPoint}`
                + ` | orders ${exchange.order_count || 0}`
                + ` | player ${exchange.player_order_count || 0}`
                + ` | NPC ${exchange.npc_order_count || 0}`;
            if (configuredDefault && String(exchange.exchange_id || "") === configuredDefault) {
                opt.selected = true;
            }
            select.appendChild(opt);
        });
    } catch (err) {
        select.innerHTML = `<option value="${escapeHtml(configuredDefault)}">${configuredDefault ? `Configured exchange ${configuredDefault}` : "Default Global exchange"}</option>`;
    }
}


async function refreshMarketBuybackStatus() {
    const panel = document.getElementById("marketBuybackStatus");
    if (!panel) return;

    try {
        const response = await fetch("/api/market-buyback-status");
        const data = await response.json();

        if (!data.ok) {
            panel.textContent = data.error || "Unable to load buyback automation status.";
            return;
        }

        const status = data.status || {};
        panel.textContent =
            `Automated buyback: ${status.enabled ? "Running" : "Stopped"}\n`
            + `Interval: ${status.interval_minutes || 30} minutes\n`
            + `Price multiplier: ${status.price_multiplier || 1}x\n`
            + `Buy threshold: ${status.threshold_percent || 60}%\n`
            + `Max buys: ${status.max_buys || 500}\n`
            + `Next run: ${status.next_run || "Not scheduled"}\n`
            + `Last run: ${status.last_run || "Never"}\n`
            + `Runs completed: ${status.runs || 0}\n`
            + `Last error: ${status.last_error || "None"}`;
    } catch (err) {
        panel.textContent = "Unable to load buyback automation status.";
    }
}


async function refreshMarketReseedStatus() {
    const panel = document.getElementById("marketReseedStatus");
    if (!panel) return;

    try {
        const response = await fetch("/api/market-reseed-status");
        const data = await response.json();

        if (!data.ok) {
            panel.textContent = data.error || "Unable to load reseed automation status.";
            return;
        }

        const status = data.status || {};
        panel.textContent =
            `Automated reseed: ${status.enabled ? "Running" : "Stopped"}\n`
            + `Interval: ${status.interval_minutes || 30} minutes\n`
            + `Price multiplier: ${status.price_multiplier || 1}x\n`
            + `Exchange ID: ${status.exchange_id || "Global/default"}\n`
            + `Next run: ${status.next_run || "Not scheduled"}\n`
            + `Last run: ${status.last_run || "Never"}\n`
            + `Runs completed: ${status.runs || 0}\n`
            + `Last error: ${status.last_error || "None"}`;
    } catch (err) {
        panel.textContent = "Unable to load reseed automation status.";
    }
}


// =========================================================
// Vehicle repair helpers
// =========================================================

let latestVehicles = [];
let latestOrnithopters = [];
let ornithopterAdminMapZoom = 0.10;
let ornithopterAdminMapControlsWired = false;
let ornithopterAdminMapDragging = false;
let ornithopterAdminMapDragStartX = 0;
let ornithopterAdminMapDragStartY = 0;
let ornithopterAdminMapDragScrollLeft = 0;
let ornithopterAdminMapDragScrollTop = 0;

async function fetchVehicles() {
    const response = await fetch("/api/vehicles");
    const data = await response.json();
    latestVehicles = data.vehicles || [];
    return latestVehicles;
}

function vehicleLabel(v) {
    const id = v.vehicle_id || "";
    const klass = v.vehicle_class || "Unknown vehicle";
    const shortClass = klass.split("/").pop() || klass;
    return `Vehicle ${id} | ${shortClass} | modules ${v.module_count || "?"} | durability ${v.min_durability || "?"}-${v.max_durability || "?"}`;
}

function fillVehicleSelect(selectId, vehicles) {
    const select = document.getElementById(selectId);
    if (!select) return;

    select.innerHTML = `<option value="">Select a vehicle...</option>`;

    vehicles.forEach((v, index) => {
        const opt = document.createElement("option");
        opt.value = String(index);
        opt.textContent = vehicleLabel(v);
        select.appendChild(opt);
    });
}

async function loadVehiclesForAdminPage() {
    const vehicles = await fetchVehicles();
    fillVehicleSelect("vehicleSelect", vehicles);
}

function fillVehicleRepairFields() {
    const sel = document.getElementById("vehicleSelect");
    const input = document.getElementById("vehicleRepairId");
    const v = latestVehicles[Number(sel.value)];
    if (input && v) input.value = v.vehicle_id || "";
}


// =========================================================
// Vehicle teleport helpers
// =========================================================

async function fetchOrnithopters() {
    const response = await fetch("/api/teleportable-vehicles");
    const data = await response.json();
    latestOrnithopters = data.vehicles || [];
    return latestOrnithopters;
}

function ornithopterLabel(t) {
    const id = t.actor_id || "";
    const shortClass = t.short_class || "Vehicle";
    const map = t.map || "Unknown map";
    const partition = t.partition_id || "?";
    const x = Number(t.x || 0).toFixed(0);
    const y = Number(t.y || 0).toFixed(0);
    const z = Number(t.z || 0).toFixed(0);
    const owner = t.owner_account_id ? ` | owner ${t.owner_account_id}` : "";
    return `Actor ${id} | ${shortClass} | ${map} partition ${partition} | X ${x} Y ${y} Z ${z}${owner}`;
}

function fillOrnithopterSelect(selectId, ornithopters) {
    const select = document.getElementById(selectId);
    if (!select) return;

    select.innerHTML = `<option value="">Select a vehicle...</option>`;

    ornithopters.forEach((t, index) => {
        const opt = document.createElement("option");
        opt.value = String(index);
        opt.textContent = ornithopterLabel(t);
        select.appendChild(opt);
    });
}

async function loadOrnithoptersForAdminPage() {
    const ornithopters = await fetchOrnithopters();
    fillOrnithopterSelect("ornithopterSelect", ornithopters);
    fillOrnithopterSelect("vehicleDeleteSelect", ornithopters);
    syncOrnithopterAdminMapZoomSlider();
    renderOrnithopterAdminMap();
}

function ornithopterPartitionForMap(mapKey) {
    // Partition IDs are configured per visible map instance because private
    // servers can run multiple Survival/Deep Desert instances with different
    // partition ids. Keep EASY_DUNE_MAP_CONFIGS_JSON in sync on such servers.
    if (typeof adminMapConfigs === "undefined") return "";
    const cfg = adminMapConfigs[mapKey] || adminMapConfigs.HaggaBasin || {};
    return cfg.default_partition_id || "";
}

function fillOrnithopterPartitionDefault() {
    const mapSelect = document.getElementById("ornithopterMapKey");
    const partitionInput = document.getElementById("ornithopterPartitionId");

    if (mapSelect && partitionInput) {
        partitionInput.value = ornithopterPartitionForMap(mapSelect.value);
    }
}

function ornithopterMapKeyForActor(t, fallbackMapKey) {
    // Some actor rows have a blank/nonstandard map field. For form safety, only
    // put map keys into the dropdown that the backend route accepts.
    if (typeof adminMapConfigs !== "undefined") {
        const actorMap = String(t.map || "");
        const partition = String(t.partition_id || "");

        for (const [key, cfg] of Object.entries(adminMapConfigs)) {
            const cfgActorMap = String(cfg.actor_map || key);
            const cfgPartition = String(cfg.default_partition_id || "");
            if (actorMap === cfgActorMap && (!cfgPartition || partition === cfgPartition)) {
                return key;
            }
        }

        if (t.map && adminMapConfigs[t.map]) {
            return t.map;
        }
    }
    return fallbackMapKey || "HaggaBasin";
}

function fillOrnithopterTeleportFields() {
    const sel = document.getElementById("ornithopterSelect");
    const t = latestOrnithopters[Number(sel.value)];
    if (!t) return;

    const actorInput = document.getElementById("ornithopterActorId");
    const mapSelect = document.getElementById("ornithopterMapKey");
    const partitionInput = document.getElementById("ornithopterPartitionId");
    const xInput = document.getElementById("ornithopterX");
    const yInput = document.getElementById("ornithopterY");
    const zInput = document.getElementById("ornithopterZ");

    const mapKey = ornithopterMapKeyForActor(t, mapSelect ? mapSelect.value : "HaggaBasin");

    if (actorInput) actorInput.value = t.actor_id || "";
    if (mapSelect) mapSelect.value = mapKey;
    if (partitionInput) partitionInput.value = t.partition_id || ornithopterPartitionForMap(mapKey);
    if (xInput) xInput.value = t.x || "";
    if (yInput) yInput.value = t.y || "";
    if (zInput) zInput.value = t.z || "";
}

function fillVehicleDeleteFields() {
    const sel = document.getElementById("vehicleDeleteSelect");
    const input = document.getElementById("vehicleDeleteActorId");
    const t = latestOrnithopters[Number(sel.value)];
    if (input && t) input.value = t.actor_id || "";
}

function adminWorldToMapPixels(x, y, mapConfig) {
    const minX = mapConfig.min_x;
    const maxX = mapConfig.max_x;
    const minY = mapConfig.min_y;
    const maxY = mapConfig.max_y;

    if (maxX === minX || maxY === minY) return null;

    const px = ((x - minX) / (maxX - minX)) * mapConfig.width;
    let py = ((y - minY) / (maxY - minY)) * mapConfig.height;

    if (mapConfig.flip_y) {
        py = mapConfig.height - py;
    }

    return {
        px,
        py,
        inBounds: px >= 0 && px <= mapConfig.width && py >= 0 && py <= mapConfig.height
    };
}

function adminMapPixelsToWorld(px, py, mapConfig) {
    const minX = mapConfig.min_x;
    const maxX = mapConfig.max_x;
    const minY = mapConfig.min_y;
    const maxY = mapConfig.max_y;

    if (mapConfig.width === 0 || mapConfig.height === 0) return null;

    let normalizedY = py / mapConfig.height;
    if (mapConfig.flip_y) {
        normalizedY = 1 - normalizedY;
    }

    return {
        x: minX + (px / mapConfig.width) * (maxX - minX),
        y: minY + normalizedY * (maxY - minY)
    };
}

function ornithopterBelongsOnMap(t, mapKey) {
    const cfg = typeof adminMapConfigs !== "undefined" ? adminMapConfigs[mapKey] : null;
    const actorMap = cfg ? String(cfg.actor_map || mapKey) : mapKey;
    const cfgPartition = cfg ? String(cfg.default_partition_id || "") : ornithopterPartitionForMap(mapKey);
    const actorMatches = String(t.map || "") === actorMap || String(t.map || "") === mapKey;
    const partitionMatches = !cfgPartition || String(t.partition_id || "") === cfgPartition;

    return actorMatches && partitionMatches;
}

function fillOrnithopterTeleportFromActor(t) {
    const actorInput = document.getElementById("ornithopterActorId");
    const mapSelect = document.getElementById("ornithopterMapKey");
    const partitionInput = document.getElementById("ornithopterPartitionId");
    const xInput = document.getElementById("ornithopterX");
    const yInput = document.getElementById("ornithopterY");
    const zInput = document.getElementById("ornithopterZ");

    const mapKey = ornithopterMapKeyForActor(t, document.getElementById("ornithopterMapView")?.value || "HaggaBasin");

    if (actorInput) actorInput.value = t.actor_id || "";
    if (mapSelect) mapSelect.value = mapKey;
    if (partitionInput) partitionInput.value = t.partition_id || ornithopterPartitionForMap(mapKey);
    if (xInput) xInput.value = t.x || "";
    if (yInput) yInput.value = t.y || "";
    if (zInput) zInput.value = t.z || "";
}

function fillOrnithopterTargetFromAdminMapClick(event) {
    if (typeof adminMapConfigs === "undefined") return;
    if (event.target.closest(".ornithopter-marker")) return;

    event.preventDefault();

    const mapSelect = document.getElementById("ornithopterMapView");
    const formMapSelect = document.getElementById("ornithopterMapKey");
    const partitionInput = document.getElementById("ornithopterPartitionId");
    const xInput = document.getElementById("ornithopterX");
    const yInput = document.getElementById("ornithopterY");
    const zInput = document.getElementById("ornithopterZ");
    const spawnAtXInput = document.getElementById("redblinkVehicleAtX");
    const spawnAtYInput = document.getElementById("redblinkVehicleAtY");
    const spawnAtZInput = document.getElementById("redblinkVehicleAtZ");
    const frame = document.getElementById("ornithopterMapFrame");
    const canvas = document.getElementById("ornithopterMapCanvas");
    const summary = document.getElementById("ornithopterMapSummary");

    if (!mapSelect || !frame || !canvas || !xInput || !yInput) return;

    const mapKey = mapSelect.value || "HaggaBasin";
    const mapConfig = adminMapConfigs[mapKey] || adminMapConfigs.HaggaBasin;
    const canvasRect = canvas.getBoundingClientRect();

    // Convert the double-click location back into source map image pixels.
    // Keep this formula paired with adminWorldToMapPixels/adminMapPixelsToWorld
    // if you ever recalibrate the map bounds in app.py.
    const px = (event.clientX - canvasRect.left) / ornithopterAdminMapZoom;
    const py = (event.clientY - canvasRect.top) / ornithopterAdminMapZoom;

    if (px < 0 || px > mapConfig.width || py < 0 || py > mapConfig.height) return;

    const world = adminMapPixelsToWorld(px, py, mapConfig);
    if (!world) return;

    if (formMapSelect) formMapSelect.value = mapKey;
    if (partitionInput) partitionInput.value = ornithopterPartitionForMap(mapKey);
    xInput.value = world.x.toFixed(3);
    yInput.value = world.y.toFixed(3);
    if (spawnAtXInput) spawnAtXInput.value = world.x.toFixed(3);
    if (spawnAtYInput) spawnAtYInput.value = world.y.toFixed(3);

    // Z is intentionally not derived from the flat map. If a vehicle has been
    // selected, leave its current altitude as the starting point; otherwise use
    // a conservative above-ground starter value the admin can adjust.
    if (zInput && !zInput.value) {
        zInput.value = "1500";
    }
    if (spawnAtZInput && !spawnAtZInput.value) {
        spawnAtZInput.value = "1500";
    }

    if (summary) {
        summary.textContent =
            `${mapConfig.label}: target set to X ${world.x.toFixed(0)} Y ${world.y.toFixed(0)} for teleport and spawn-at forms`;
    }
}

function syncOrnithopterAdminMapZoomSlider() {
    const slider = document.getElementById("ornithopterMapZoom");
    const readout = document.getElementById("ornithopterMapZoomReadout");
    const percent = Math.round(ornithopterAdminMapZoom * 100);

    if (slider) slider.value = String(percent);
    if (readout) readout.textContent = `${percent}%`;
}

function setOrnithopterAdminMapZoom(newZoom) {
    ornithopterAdminMapZoom = Math.max(0.05, Math.min(1.00, newZoom));
    syncOrnithopterAdminMapZoomSlider();
    renderOrnithopterAdminMap();
}

function setOrnithopterAdminMapZoomFromSlider() {
    const slider = document.getElementById("ornithopterMapZoom");
    if (!slider) return;
    setOrnithopterAdminMapZoom(Number(slider.value || 10) / 100);
}

function setOrnithopterAdminMapZoomAroundPoint(newZoom, clientX, clientY) {
    const frame = document.getElementById("ornithopterMapFrame");
    if (!frame) {
        setOrnithopterAdminMapZoom(newZoom);
        return;
    }

    const oldZoom = ornithopterAdminMapZoom;
    const nextZoom = Math.max(0.05, Math.min(1.00, newZoom));
    const rect = frame.getBoundingClientRect();
    const sourceX = (frame.scrollLeft + clientX - rect.left) / oldZoom;
    const sourceY = (frame.scrollTop + clientY - rect.top) / oldZoom;

    ornithopterAdminMapZoom = nextZoom;
    syncOrnithopterAdminMapZoomSlider();
    renderOrnithopterAdminMap();

    frame.scrollLeft = (sourceX * nextZoom) - (clientX - rect.left);
    frame.scrollTop = (sourceY * nextZoom) - (clientY - rect.top);
}

function wireOrnithopterAdminMapControls() {
    const frame = document.getElementById("ornithopterMapFrame");
    const canvas = document.getElementById("ornithopterMapCanvas");

    if (!frame || !canvas || ornithopterAdminMapControlsWired) return;
    ornithopterAdminMapControlsWired = true;

    frame.addEventListener("dblclick", fillOrnithopterTargetFromAdminMapClick);

    frame.addEventListener("pointerdown", function(event) {
        if (event.button !== 0 || event.target.closest(".ornithopter-marker")) return;

        ornithopterAdminMapDragging = true;
        ornithopterAdminMapDragStartX = event.clientX;
        ornithopterAdminMapDragStartY = event.clientY;
        ornithopterAdminMapDragScrollLeft = frame.scrollLeft;
        ornithopterAdminMapDragScrollTop = frame.scrollTop;
        frame.classList.add("is-dragging");
        frame.setPointerCapture(event.pointerId);
    });

    frame.addEventListener("pointermove", function(event) {
        if (!ornithopterAdminMapDragging) return;

        event.preventDefault();
        frame.scrollLeft = ornithopterAdminMapDragScrollLeft - (event.clientX - ornithopterAdminMapDragStartX);
        frame.scrollTop = ornithopterAdminMapDragScrollTop - (event.clientY - ornithopterAdminMapDragStartY);
    });

    frame.addEventListener("pointerup", function(event) {
        if (!ornithopterAdminMapDragging) return;

        ornithopterAdminMapDragging = false;
        frame.classList.remove("is-dragging");
        if (frame.hasPointerCapture(event.pointerId)) {
            frame.releasePointerCapture(event.pointerId);
        }
    });

    frame.addEventListener("pointercancel", function(event) {
        ornithopterAdminMapDragging = false;
        frame.classList.remove("is-dragging");
        if (frame.hasPointerCapture(event.pointerId)) {
            frame.releasePointerCapture(event.pointerId);
        }
    });

    frame.addEventListener("wheel", function(event) {
        if (!event.ctrlKey && !event.metaKey) {
            event.preventDefault();
            window.scrollBy({
                top: event.deltaY,
                left: event.deltaX,
                behavior: "auto"
            });
            return;
        }

        event.preventDefault();
        const zoomStep = event.deltaY < 0 ? 1.12 : 0.88;
        setOrnithopterAdminMapZoomAroundPoint(
            ornithopterAdminMapZoom * zoomStep,
            event.clientX,
            event.clientY
        );
    }, { passive: false });
}

function renderOrnithopterAdminMap() {
    if (typeof adminMapConfigs === "undefined") return;

    const mapSelect = document.getElementById("ornithopterMapView");
    const canvas = document.getElementById("ornithopterMapCanvas");
    const image = document.getElementById("ornithopterMapImage");
    const layer = document.getElementById("ornithopterMarkerLayer");
    const summary = document.getElementById("ornithopterMapSummary");

    if (!mapSelect || !canvas || !image || !layer || !summary) return;

    const mapKey = mapSelect.value || "HaggaBasin";
    const mapConfig = adminMapConfigs[mapKey] || adminMapConfigs.HaggaBasin;
    const zoom = ornithopterAdminMapZoom;

    image.src = `/static/${mapConfig.image}`;
    image.alt = mapConfig.label;

    const width = mapConfig.width * zoom;
    const height = mapConfig.height * zoom;

    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    image.style.width = `${width}px`;
    image.style.height = `${height}px`;
    layer.style.width = `${width}px`;
    layer.style.height = `${height}px`;
    layer.innerHTML = "";

    const visible = latestOrnithopters
        .filter(t => ornithopterBelongsOnMap(t, mapKey))
        .map(t => {
            const pixel = adminWorldToMapPixels(Number(t.x), Number(t.y), mapConfig);
            return { ...t, pixel };
        })
        .filter(t => t.pixel && t.pixel.inBounds);

    summary.textContent = `${mapConfig.label}: ${visible.length} vehicle actor(s) in bounds`;

    visible.forEach(t => {
        const marker = document.createElement("button");
        marker.type = "button";
        marker.className = "ornithopter-marker";
        marker.style.left = `${t.pixel.px * zoom}px`;
        marker.style.top = `${t.pixel.py * zoom}px`;
        marker.title = ornithopterLabel(t);
        marker.addEventListener("click", event => {
            event.stopPropagation();
            fillOrnithopterTeleportFromActor(t);
        });
        marker.addEventListener("dblclick", event => {
            event.stopPropagation();
        });
        layer.appendChild(marker);
    });
}
