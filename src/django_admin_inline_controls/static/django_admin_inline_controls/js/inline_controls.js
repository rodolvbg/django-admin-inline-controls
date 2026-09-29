/*
 * django-admin-inline-controls
 *
 * Progressive enhancement for inlines rendered by InlineControlsMixin:
 * filters, sortable headers and page links refresh only that inline
 * (fetch + swap) and infinite mode appends the next page on scroll.
 * Plain script, no dependencies; uses django.jQuery only to re-run the
 * admin's own inline/widget initialization after a swap.
 */
(() => {
    const ROOT_SELECTOR = "[data-inline-controls]";
    const states = new WeakMap();
    let historyPushed = false;

    const escapeRegExp = (value) =>
        value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

    const readConfig = (root) => JSON.parse(root.dataset.inlineControls);

    /** Point every `<prefix>-<n>` reference in `el`'s attributes at `index`. */
    function updateElementIndex(el, prefix, index) {
        const pattern = new RegExp(
            `${escapeRegExp(prefix)}-(\\d+|__prefix__)(?=-|\\s|$)`,
            "g",
        );
        for (const attr of ["id", "name", "for", "aria-describedby"]) {
            const value = el.getAttribute(attr);
            if (value) {
                el.setAttribute(
                    attr,
                    value.replace(pattern, `${prefix}-${index}`),
                );
            }
        }
    }

    function reindexForm(form, prefix, index) {
        updateElementIndex(form, prefix, index);
        for (const el of form.querySelectorAll("*")) {
            updateElementIndex(el, prefix, index);
        }
    }

    /** Form containers (tabular rows / stacked blocks) of one formset. */
    function formRows(group, prefix) {
        const pattern = new RegExp(`^${escapeRegExp(prefix)}-(\\d+|empty)$`);
        return [...group.querySelectorAll("[id]")].filter((el) =>
            pattern.test(el.id),
        );
    }

    function formIndex(row, prefix) {
        const match = row.id.match(
            new RegExp(`^${escapeRegExp(prefix)}-(\\d+)$`),
        );
        return match ? Number.parseInt(match[1], 10) : null;
    }

    /** URL for the current filter widget values of one inline. */
    function filterUrl(config, clear, base = window.location.href) {
        const url = new URL(base);
        for (const name of config.filterParams) {
            url.searchParams.delete(name);
        }
        url.searchParams.delete(config.pageParam);
        if (!clear) {
            const widgets = document.querySelectorAll(
                `[form="${config.filterFormId}"]`,
            );
            for (const el of widgets) {
                if (!el.name || el.disabled) {
                    continue;
                }
                if (
                    (el.type === "checkbox" || el.type === "radio") &&
                    !el.checked
                ) {
                    continue;
                }
                if (el.tagName === "SELECT" && el.multiple) {
                    for (const option of el.selectedOptions) {
                        url.searchParams.append(el.name, option.value);
                    }
                } else if (el.value !== "") {
                    url.searchParams.append(el.name, el.value);
                }
            }
        }
        return url.toString();
    }

    async function fetchDocument(url) {
        const response = await fetch(url, {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const text = await response.text();
        return new DOMParser().parseFromString(text, "text/html");
    }

    /** Move the toolbar under the inline heading and the footer to its end. */
    function placeControls(root) {
        const fieldset = root.querySelector(".inline-group fieldset");
        if (!fieldset) {
            return;
        }
        const toolbar = root.querySelector(":scope > .inline-controls-toolbar");
        const heading = fieldset.querySelector("h2");
        if (toolbar && heading) {
            (heading.closest("summary") ?? heading).after(toolbar);
        }
        const footer = root.querySelector(":scope > .inline-controls-footer");
        if (footer) {
            (fieldset.querySelector(":scope > details") ?? fieldset).append(
                footer,
            );
        }
    }

    /**
     * Turn tabular column headers into sort links. Returns true when every
     * sortable column got a header, so the toolbar links can be hidden.
     */
    function decorateHeaders(root, config) {
        const thead = root.querySelector(".inline-group table thead");
        if (!thead || config.ordering.length === 0) {
            return false;
        }
        let all = true;
        for (const column of config.ordering) {
            const th = thead.querySelector(`th.column-${column.name}`);
            if (!th) {
                all = false;
                continue;
            }
            th.classList.add("inline-controls-sortable");
            if (column.direction) {
                th.classList.add(`inline-controls-${column.direction}`);
            }
            const link = document.createElement("a");
            link.href = column.toggleUrl;
            link.className = "inline-controls-sort-toggle";
            link.title = config.messages.sortToggle;
            link.dataset.inlineControlsNav = "";
            for (const node of [...th.childNodes]) {
                if (
                    node.nodeType === Node.TEXT_NODE &&
                    node.textContent.trim()
                ) {
                    link.append(node.textContent.trim());
                    node.remove();
                }
            }
            th.prepend(link);
            if (column.priority) {
                const priority = document.createElement("span");
                priority.className = "inline-controls-sort-priority";
                priority.textContent = ` ${column.priority}`;
                const remove = document.createElement("a");
                remove.href = column.removeUrl;
                remove.className = "inline-controls-sort-remove";
                remove.title = config.messages.sortRemove;
                remove.dataset.inlineControlsNav = "";
                remove.textContent = "×";
                link.after(priority, remove);
            }
        }
        return all;
    }

    /** Re-run the admin's inline and widget setup on freshly inserted HTML. */
    function reinitAdmin(container) {
        const $ = window.django?.jQuery;
        const group = container.matches(".js-inline-admin-formset")
            ? container
            : container.querySelector(".js-inline-admin-formset");
        if ($ && group && $.fn.tabularFormset) {
            const data = JSON.parse(group.dataset.inlineFormset);
            if (group.dataset.inlineType === "tabular") {
                const selector = `${data.name}-group .tabular.inline-related tbody:first > tr.form-row`;
                $(selector).tabularFormset(selector, data.options);
            } else if (group.dataset.inlineType === "stacked") {
                const selector = `${data.name}-group .inline-related`;
                $(selector).stackedFormset(selector, data.options);
            }
        }
        initWidgets(container);
    }

    function initWidgets(container) {
        const $ = window.django?.jQuery;
        if ($?.fn.djangoAdminSelect2) {
            $(container)
                .find(".admin-autocomplete")
                .not("[name*=__prefix__]")
                .djangoAdminSelect2();
        }
        if ($ && typeof window.DateTimeShortcuts !== "undefined") {
            $(".datetimeshortcuts").remove();
            window.DateTimeShortcuts.init();
        }
        if (typeof window.SelectFilter !== "undefined") {
            for (const el of container.querySelectorAll(
                ".selectfilter, .selectfilterstacked",
            )) {
                if (!el.name.includes("__prefix__")) {
                    window.SelectFilter.init(
                        el.id,
                        el.dataset.fieldName,
                        el.classList.contains("selectfilterstacked"),
                    );
                }
            }
        }
        if ($) {
            $(container)
                .find(".related-widget-wrapper select")
                .trigger("change");
        }
        container.dispatchEvent(
            new CustomEvent("inline-controls:updated", { bubbles: true }),
        );
    }

    /** Replace `root` with a copy of `fresh`, keeping <details> open state. */
    function swapInline(root, fresh) {
        const node = document.importNode(fresh, true);
        const wasOpen = [...root.querySelectorAll("details")].map(
            (details) => details.open,
        );
        node.querySelectorAll("details").forEach((details, index) => {
            if (index < wasOpen.length) {
                details.open = wasOpen[index];
            }
        });
        root.replaceWith(node);
        return node;
    }

    /** The admin form's values for the controls inside one inline group. */
    function inlineFormData(group, form) {
        const data = new FormData();
        const csrf = form.querySelector("[name=csrfmiddlewaretoken]");
        if (csrf) {
            data.append(csrf.name, csrf.value);
        }
        const skipTypes = ["submit", "button", "reset", "image"];
        for (const el of group.querySelectorAll("input, select, textarea")) {
            if (
                !el.name ||
                el.disabled ||
                el.form !== form ||
                el.name.includes("__prefix__") ||
                skipTypes.includes(el.type)
            ) {
                continue;
            }
            if (
                (el.type === "checkbox" || el.type === "radio") &&
                !el.checked
            ) {
                continue;
            }
            if (el.type === "file") {
                for (const file of el.files) {
                    data.append(el.name, file);
                }
            } else if (el.tagName === "SELECT" && el.multiple) {
                for (const option of el.selectedOptions) {
                    data.append(el.name, option.value);
                }
            } else {
                data.append(el.name, el.value);
            }
        }
        return data;
    }

    function showStatus(
        root,
        status,
        message,
        scope = ".inline-controls-save",
    ) {
        const el = root.querySelector(`${scope} .inline-controls-status`);
        if (el) {
            el.className = `inline-controls-status inline-controls-status-${status}`;
            el.textContent = message;
        }
    }

    /** POST only this inline's forms and swap in the re-rendered inline. */
    async function saveInline(root) {
        const state = states.get(root);
        const { config } = state;
        const group = document.getElementById(`${config.prefix}-group`);
        const form = group?.closest("form");
        if (state.loading || !config.saveUrl || !form) {
            return;
        }
        state.loading = true;
        root.classList.add("inline-controls-loading");
        const target = new URL(
            config.saveUrl + window.location.search,
            window.location.href,
        ).toString();
        try {
            const response = await fetch(target, {
                method: "POST",
                body: inlineFormData(group, form),
                credentials: "same-origin",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const text = await response.text();
            const doc = new DOMParser().parseFromString(text, "text/html");
            const result = doc.getElementById(
                `${config.prefix}-inline-controls-response`,
            );
            const fresh = doc.getElementById(root.id);
            if (!result || !fresh) {
                throw new Error("Inline not found in response");
            }
            const node = swapInline(root, fresh);
            setup(node);
            reinitAdmin(node);
            showStatus(node, result.dataset.status, result.dataset.message);
        } catch {
            state.loading = false;
            root.classList.remove("inline-controls-loading");
            showStatus(root, "failed", config.messages.saveFailed);
        }
    }

    const format = (template, values) =>
        template.replace(/%\((\w+)\)s/g, (_, key) => values[key]);

    /** Saved rows of the inline with their primary keys. */
    function selectableRows(root, config) {
        const group = root.querySelector(`[id="${config.prefix}-group"]`);
        if (!group) {
            return [];
        }
        return formRows(group, config.prefix)
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
        const label =
            row.querySelector(":scope > td.original > p") ??
            row.querySelector(":scope > h3") ??
            row.querySelector(":scope > td.original");
        (label ?? row).prepend(checkbox);
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
        const state = states.get(root);
        const { config } = state;
        const select = root.querySelector("[data-inline-controls-action]");
        const group = document.getElementById(`${config.prefix}-group`);
        const form = group?.closest("form");
        if (state.loading || !config.actionUrl || !select || !form) {
            return;
        }
        const scope = ".inline-controls-actions";
        const action = config.actions.find(
            (item) => item.name === select.value,
        );
        const pks = selectedPks(root);
        if (!action) {
            showStatus(root, "error", config.messages.noAction, scope);
            return;
        }
        if (pks.length === 0 && !state.selectAcross) {
            showStatus(root, "error", config.messages.noSelection, scope);
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
            const node = swapInline(root, fresh);
            setup(node);
            reinitAdmin(node);
            showStatus(
                node,
                result.dataset.status,
                result.dataset.message,
                scope,
            );
        } catch {
            state.loading = false;
            root.classList.remove("inline-controls-loading");
            showStatus(root, "failed", config.messages.actionFailed, scope);
        }
    }

    /** Replace one inline with its state at `url` (or reload if unsupported). */
    async function navigate(root, url) {
        const state = states.get(root);
        // A click while this inline is loading would act on stale links.
        if (state.loading) {
            return;
        }
        if (state.dirty && !window.confirm(state.config.messages.unsaved)) {
            return;
        }
        const target = new URL(url, window.location.href).toString();
        if (!state.config.ajax) {
            window.location.assign(target);
            return;
        }
        state.loading = true;
        root.classList.add("inline-controls-loading");
        try {
            const doc = await fetchDocument(target);
            const fresh = doc.getElementById(root.id);
            if (!fresh) {
                throw new Error("Inline not found in response");
            }
            const node = swapInline(root, fresh);
            window.history.pushState({ inlineControls: true }, "", target);
            historyPushed = true;
            setup(node);
            reinitAdmin(node);
        } catch {
            window.location.assign(target);
        }
    }

    /** Infinite mode: append the next page's saved objects to the formset. */
    async function loadMore(root) {
        const state = states.get(root);
        const { config } = state;
        if (state.loading || !config.nextUrl) {
            return;
        }
        state.loading = true;
        root.classList.add("inline-controls-loading");
        const target = new URL(config.nextUrl, window.location.href).toString();
        try {
            const doc = await fetchDocument(target);
            const fresh = doc.getElementById(root.id);
            const freshGroup = doc.getElementById(`${config.prefix}-group`);
            const group = document.getElementById(`${config.prefix}-group`);
            if (!fresh || !freshGroup || !group) {
                throw new Error("Inline not found in response");
            }
            const { prefix } = config;
            const totalInput = document.getElementById(
                `id_${prefix}-TOTAL_FORMS`,
            );
            const initialInput = document.getElementById(
                `id_${prefix}-INITIAL_FORMS`,
            );
            const initial = Number.parseInt(initialInput.value, 10);
            const loaded = formRows(freshGroup, prefix).filter((row) =>
                row.classList.contains("has_original"),
            );
            const count = loaded.length;
            const rows = formRows(group, prefix);
            // Unsaved rows must keep indexes above every saved one.
            const unsaved = rows.filter((row) => {
                const index = formIndex(row, prefix);
                return index !== null && index >= initial;
            });
            for (const row of unsaved.reverse()) {
                reindexForm(row, prefix, formIndex(row, prefix) + count);
            }
            const anchor = rows.find(
                (row) => !row.classList.contains("has_original"),
            );
            const last = rows.at(-1);
            const inserted = loaded.map((row, offset) => {
                const node = document.importNode(row, true);
                reindexForm(node, prefix, initial + offset);
                node.classList.add(`dynamic-${prefix}`);
                if (anchor) {
                    anchor.before(node);
                } else if (last) {
                    last.after(node);
                }
                return node;
            });
            totalInput.value = Number.parseInt(totalInput.value, 10) + count;
            initialInput.value = initial + count;

            const freshConfig = readConfig(fresh);
            state.config = {
                ...config,
                nextUrl: freshConfig.nextUrl,
                loadedCount: freshConfig.loadedCount,
            };
            root.dataset.inlineControls = JSON.stringify(state.config);
            const countEl = root.querySelector(".inline-controls-count");
            const freshCount = fresh.querySelector(".inline-controls-count");
            if (countEl && freshCount) {
                countEl.textContent = freshCount.textContent;
            }
            const more = root.querySelector("[data-inline-controls-more]");
            if (more) {
                if (freshConfig.nextUrl) {
                    more.href = freshConfig.nextUrl;
                } else {
                    state.observer?.disconnect();
                    more.remove();
                }
            }
            if (state.config.actionUrl) {
                for (const { row, pk } of selectableRows(root, state.config)) {
                    addRowCheckbox(row, pk, state.config);
                }
                updateSelection(root, state);
            }
            for (const node of inserted) {
                initWidgets(node);
            }
        } catch {
            window.location.assign(target);
        } finally {
            state.loading = false;
            root.classList.remove("inline-controls-loading");
        }
    }

    function setup(root) {
        if (states.has(root)) {
            return;
        }
        const config = readConfig(root);
        const state = {
            config,
            dirty: false,
            loading: false,
            observer: null,
            selectAcross: false,
        };
        states.set(root, state);

        placeControls(root);
        setupActions(root, state);
        if (decorateHeaders(root, config)) {
            const ordering = root.querySelector(".inline-controls-ordering");
            if (ordering) {
                ordering.hidden = true;
            }
        }

        const isFilterWidget = (el) =>
            el.getAttribute?.("form") === config.filterFormId;

        root.addEventListener("click", (event) => {
            const nav = event.target.closest("[data-inline-controls-nav]");
            if (nav) {
                event.preventDefault();
                navigate(root, nav.getAttribute("href"));
                return;
            }
            if (event.target.closest("[data-inline-controls-apply]")) {
                event.preventDefault();
                navigate(root, filterUrl(state.config, false));
            } else if (event.target.closest("[data-inline-controls-clear]")) {
                event.preventDefault();
                navigate(root, filterUrl(state.config, true));
            } else if (event.target.closest("[data-inline-controls-more]")) {
                event.preventDefault();
                loadMore(root);
            } else if (event.target.closest("[data-inline-controls-save]")) {
                event.preventDefault();
                saveInline(root);
            } else if (event.target.closest("[data-inline-controls-run]")) {
                event.preventDefault();
                runAction(root);
            } else if (
                event.target.closest("[data-inline-controls-select-across]")
            ) {
                event.preventDefault();
                for (const box of root.querySelectorAll(
                    ".inline-controls-select",
                )) {
                    box.checked = true;
                }
                state.selectAcross = true;
                updateSelection(root, state);
            }
        });
        root.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && isFilterWidget(event.target)) {
                event.preventDefault();
                navigate(root, filterUrl(state.config, false));
            }
        });
        const isActionWidget = (el) =>
            el.getAttribute?.("form") === config.actionsFormId;
        const markDirty = (event) => {
            if (
                event.target.classList?.contains("inline-controls-select-all")
            ) {
                for (const box of root.querySelectorAll(
                    ".inline-controls-select",
                )) {
                    box.checked = event.target.checked;
                }
            }
            if (isActionWidget(event.target)) {
                if (event.type === "change") {
                    updateSelection(root, state);
                }
                return;
            }
            if (!isFilterWidget(event.target)) {
                state.dirty = true;
            }
        };
        root.addEventListener("input", markDirty);
        root.addEventListener("change", markDirty);

        const more = root.querySelector("[data-inline-controls-more]");
        if (more && typeof window.IntersectionObserver !== "undefined") {
            state.observer = new IntersectionObserver((entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    loadMore(root);
                }
            });
            state.observer.observe(more);
        }
    }

    function init() {
        for (const root of document.querySelectorAll(ROOT_SELECTOR)) {
            setup(root);
        }
    }

    // Swapped inlines are not cached by the browser: going back or forward
    // through URLs pushed by navigate() needs a real load.
    window.addEventListener("popstate", () => {
        if (historyPushed) {
            window.location.reload();
        }
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    globalThis.DjangoAdminInlineControls = {
        decorateHeaders,
        filterUrl,
        formRows,
        init,
        inlineFormData,
        loadMore,
        navigate,
        placeControls,
        reindexForm,
        runAction,
        saveInline,
        setup,
        updateElementIndex,
    };
})();
