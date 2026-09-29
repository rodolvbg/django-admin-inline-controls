/*
 * django-admin-inline-controls: inline actions (inline_actions).
 * Loaded after core.js, only by inlines that use them.
 */
(() => {
    const core = globalThis.DjangoAdminInlineControls;
    const SCOPE = ".inline-controls-actions";

    const format = (template, values) =>
        template.replace(/%\((\w+)\)s/g, (_, key) => values[key]);

    /** Saved rows of the inline with their primary keys. */
    function selectableRows(root, config) {
        const group = root.querySelector(`[id="${config.prefix}-group"]`);
        if (!group) {
            return [];
        }
        return core
            .formRows(group, config.prefix)
            .filter((row) => row.classList.contains("has_original"))
            .map((row) => {
                const index = row.id.slice(config.prefix.length + 1);
                const input = row.querySelector(
                    `[name="${config.prefix}-${index}-${config.pkName}"]`,
                );
                return { row, pk: input?.value };
            })
            .filter(({ pk }) => pk);
    }

    function addRowCheckbox(row, pk, config) {
        if (row.querySelector(".inline-controls-select")) {
            return;
        }
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "inline-controls-select";
        checkbox.value = pk;
        checkbox.setAttribute("form", config.actionsFormId);
        checkbox.setAttribute("aria-label", config.messages.selectRow ?? "");
        // Next to the object's name: the label line of a tabular row (inside
        // the zero-width "original" cell) or the heading of a stacked one.
        (core.query(row, config, "row_label") ?? row).prepend(checkbox);
    }

    function selectedPks(root) {
        return [
            ...root.querySelectorAll(".inline-controls-select:checked"),
        ].map((checkbox) => checkbox.value);
    }

    function updateSelection(root, state) {
        const { config } = state;
        const boxes = [...root.querySelectorAll(".inline-controls-select")];
        const checked = boxes.filter((box) => box.checked).length;
        const total = config.totalCount ?? boxes.length;
        const all = boxes.length > 0 && checked === boxes.length;
        if (!all) {
            state.selectAcross = false;
        }
        const toggle = root.querySelector(".inline-controls-select-all");
        if (toggle) {
            toggle.checked = all;
            toggle.indeterminate = checked > 0 && !all;
        }
        const label = root.querySelector("[data-inline-controls-selection]");
        if (label) {
            label.textContent = state.selectAcross
                ? format(config.messages.allSelected, { total })
                : format(config.messages.selected, {
                      sel: checked,
                      cnt: total,
                  });
        }
        const across = root.querySelector(
            "[data-inline-controls-select-across]",
        );
        if (across) {
            across.hidden = !all || state.selectAcross || total <= boxes.length;
            across.textContent = format(config.messages.selectAll, { total });
        }
    }

    function setupActions(root, state) {
        const { config } = state;
        state.selectAcross = false;
        if (!config.actionUrl) {
            return;
        }
        for (const { row, pk } of selectableRows(root, config)) {
            addRowCheckbox(row, pk, config);
        }
        const toggle = document.createElement("input");
        toggle.type = "checkbox";
        toggle.className = "inline-controls-select-all";
        toggle.setAttribute("form", config.actionsFormId);
        toggle.setAttribute("aria-label", config.messages.selectAllRows ?? "");
        root.querySelector(".inline-controls-actions")?.prepend(toggle);
        updateSelection(root, state);
    }

    async function runAction(root) {
        const state = core.stateOf(root);
        const { config } = state;
        const select = root.querySelector("[data-inline-controls-action]");
        const group = document.getElementById(`${config.prefix}-group`);
        const form = group?.closest("form");
        if (state.loading || !config.actionUrl || !select || !form) {
            return;
        }
        const action = config.actions.find(
            (item) => item.name === select.value,
        );
        const pks = selectedPks(root);
        if (!action) {
            core.showStatus(root, "error", config.messages.noAction, SCOPE);
            return;
        }
        if (pks.length === 0 && !state.selectAcross) {
            core.showStatus(root, "error", config.messages.noSelection, SCOPE);
            return;
        }
        const count = state.selectAcross
            ? (config.totalCount ?? pks.length)
            : pks.length;
        if (
            action.confirmation &&
            !window.confirm(format(action.confirmation, { count }))
        ) {
            return;
        }
        if (state.dirty && !window.confirm(config.messages.unsaved)) {
            return;
        }
        const data = new FormData();
        const csrf = form.querySelector("[name=csrfmiddlewaretoken]");
        if (csrf) {
            data.append(csrf.name, csrf.value);
        }
        data.append("action", action.name);
        for (const pk of pks) {
            data.append("_selected_action", pk);
        }
        data.append("select_across", state.selectAcross ? "1" : "0");
        data.append(
            "_inline_controls_loaded",
            String(selectableRows(root, config).length),
        );
        state.loading = true;
        root.classList.add("inline-controls-loading");
        const target = new URL(
            config.actionUrl + window.location.search,
            window.location.href,
        ).toString();
        try {
            const response = await fetch(target, {
                method: "POST",
                body: data,
                credentials: "same-origin",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const disposition =
                response.headers.get("Content-Disposition") ?? "";
            if (disposition.includes("attachment")) {
                const blob = await response.blob();
                const link = document.createElement("a");
                link.href = URL.createObjectURL(blob);
                link.download =
                    disposition.match(/filename="?([^";]+)"?/)?.[1] ??
                    "download";
                document.body.append(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(link.href);
                state.loading = false;
                root.classList.remove("inline-controls-loading");
                return;
            }
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }
            const text = await response.text();
            const doc = new DOMParser().parseFromString(text, "text/html");
            const result = doc.getElementById(
                `${config.prefix}-inline-controls-response`,
            );
            const fresh = doc.getElementById(root.id);
            if (!result || !fresh) {
                // Any other page the action returned (e.g. an intermediate
                // step) replaces this one.
                document.open();
                document.write(text);
                document.close();
                return;
            }
            const node = core.swapInline(root, fresh);
            core.setup(node);
            core.reinitAdmin(node);
            core.showStatus(
                node,
                result.dataset.status,
                result.dataset.message,
                SCOPE,
            );
        } catch {
            state.loading = false;
            root.classList.remove("inline-controls-loading");
            core.showStatus(
                root,
                "failed",
                config.messages.actionFailed,
                SCOPE,
            );
        }
    }

    /** Tick every row's checkbox, or clear them. */
    function checkAll(root, checked) {
        for (const box of root.querySelectorAll(".inline-controls-select")) {
            box.checked = checked;
        }
    }

    core.register({
        setup: setupActions,
        rowsLoaded(root, state) {
            if (state.config.actionUrl) {
                for (const { row, pk } of selectableRows(root, state.config)) {
                    addRowCheckbox(row, pk, state.config);
                }
                updateSelection(root, state);
            }
        },
        click(event, root, state) {
            if (event.target.closest("[data-inline-controls-run]")) {
                runAction(root);
                return true;
            }
            if (event.target.closest("[data-inline-controls-select-across]")) {
                checkAll(root, true);
                state.selectAcross = true;
                updateSelection(root, state);
                return true;
            }
            return false;
        },
        edit(event, root, state) {
            const { target } = event;
            if (target.getAttribute?.("form") !== state.config.actionsFormId) {
                return false;
            }
            if (target.classList.contains("inline-controls-select-all")) {
                checkAll(root, target.checked);
            }
            if (event.type === "change") {
                updateSelection(root, state);
            }
            return true;
        },
    });

    Object.assign(core, { runAction });
})();
