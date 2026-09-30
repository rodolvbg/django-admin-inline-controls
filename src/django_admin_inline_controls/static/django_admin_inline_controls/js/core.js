/*
 * django-admin-inline-controls
 *
 * Progressive enhancement for inlines rendered by InlineControlsMixin:
 * filters, sortable headers and page links refresh only that inline
 * (fetch + swap) and infinite mode appends the next page on scroll. The
 * save button and the actions are separate scripts (save.js, actions.js),
 * loaded only by inlines that use them.
 * Plain script, no dependencies; uses django.jQuery only to re-run the
 * admin's own inline/widget initialization after a swap.
 */
(() => {
    const ROOT_SELECTOR = "[data-inline-controls]";
    const states = new WeakMap();
    const features = [];
    let historyPushed = false;

    const escapeRegExp = (value) =>
        value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

    const readConfig = (root) => JSON.parse(root.dataset.inlineControls);

    /** The configured selectors for `key`, with {placeholders} filled in. */
    function selectorsFor(config, key, values = {}) {
        return []
            .concat(config.selectors?.[key] ?? [])
            .map((selector) =>
                selector.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? ""),
            );
    }

    /** First element matching any of `key`'s selectors, in their order. */
    function query(scope, config, key, values) {
        for (const selector of selectorsFor(config, key, values)) {
            const element = scope?.querySelector(selector);
            if (element) {
                return element;
            }
        }
        return null;
    }

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

    /**
     * Index of a form row of `prefix`: a number, "empty" for the template
     * of new rows, or undefined if `row` isn't one. Read from its id
     * (`<prefix>-<n>`) or, without one, from its fields' names.
     */
    function rowIndex(row, prefix) {
        const escaped = escapeRegExp(prefix);
        if (row.id) {
            return row.id.match(new RegExp(`^${escaped}-(\\d+|empty)$`))?.[1];
        }
        const pattern = new RegExp(`^${escaped}-(\\d+|__prefix__)-`);
        for (const field of row.querySelectorAll("[name]")) {
            const match = field.name.match(pattern);
            if (match) {
                return match[1] === "__prefix__" ? "empty" : match[1];
            }
        }
        return undefined;
    }

    /** Form containers (tabular rows / stacked blocks) of one formset. */
    function formRows(group, prefix, config = {}) {
        const selectors = selectorsFor(config, "form_rows", { prefix });
        return [
            ...group.querySelectorAll(selectors.join(", ") || "[id]"),
        ].filter((row) => rowIndex(row, prefix) !== undefined);
    }

    function formIndex(row, prefix) {
        const index = rowIndex(row, prefix);
        return index === undefined || index === "empty"
            ? null
            : Number.parseInt(index, 10);
    }

    /** Whether a form row holds a saved object (not a new one). */
    function isSaved(row, config) {
        const selectors = selectorsFor(config, "saved_row");
        return row.matches(selectors.join(", ") || ".has_original");
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
    function placeControls(root, config = readConfig(root)) {
        const toolbar = root.querySelector(":scope > .inline-controls-toolbar");
        const footer = root.querySelector(":scope > .inline-controls-footer");
        // Listeners can place them themselves and cancel the default.
        const placing = new CustomEvent("inline-controls:place", {
            bubbles: true,
            cancelable: true,
            detail: { toolbar, footer },
        });
        if (!root.dispatchEvent(placing)) {
            return;
        }
        const container = query(root, config, "container");
        if (!container) {
            return;
        }
        const heading = query(container, config, "heading");
        if (toolbar && heading) {
            (heading.closest("summary") ?? heading).after(toolbar);
        }
        if (footer) {
            (query(container, config, "footer_parent") ?? container).append(
                footer,
            );
        }
    }

    /**
     * Turn tabular column headers into sort links. Returns true when every
     * sortable column got a header, so the toolbar links can be hidden.
     */
    function decorateHeaders(root, config) {
        const thead = query(root, config, "table_head");
        if (!thead || config.ordering.length === 0) {
            return false;
        }
        let all = true;
        for (const column of config.ordering) {
            const th = query(thead, config, "column_header", {
                name: column.name,
            });
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
            const texts = [...th.childNodes].filter(
                (node) =>
                    node.nodeType === Node.TEXT_NODE && node.textContent.trim(),
            );
            for (const node of texts) {
                link.append(node.textContent.trim());
                node.remove();
            }
            if (texts.length === 0) {
                // The label is in child elements (Unfold): link them all.
                link.append(...th.childNodes);
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
    function reinitAdmin(container, config = readConfig(container)) {
        const $ = window.django?.jQuery;
        const group = container.matches(".js-inline-admin-formset")
            ? container
            : container.querySelector(".js-inline-admin-formset");
        if ($ && group && $.fn.tabularFormset) {
            const data = JSON.parse(group.dataset.inlineFormset);
            const values = { group: `${data.name}-group` };
            if (group.dataset.inlineType === "tabular") {
                const [selector] = selectorsFor(config, "tabular_rows", values);
                $(selector).tabularFormset(selector, data.options);
            } else if (group.dataset.inlineType === "stacked") {
                const [selector] = selectorsFor(config, "stacked_rows", values);
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

    /** Show a result message in the status element under `scope`. */
    function showStatus(root, status, message, scope) {
        const el = root.querySelector(`${scope} .inline-controls-status`);
        if (el) {
            el.className = `inline-controls-status inline-controls-status-${status}`;
            el.textContent = message;
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
            const loaded = formRows(freshGroup, prefix, config).filter((row) =>
                isSaved(row, config),
            );
            const count = loaded.length;
            const rows = formRows(group, prefix, config);
            // Unsaved rows must keep indexes above every saved one.
            const unsaved = rows.filter((row) => {
                const index = formIndex(row, prefix);
                return index !== null && index >= initial;
            });
            for (const row of unsaved.reverse()) {
                reindexForm(row, prefix, formIndex(row, prefix) + count);
            }
            const anchor = rows.find((row) => !isSaved(row, config));
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
            for (const feature of features) {
                feature.rowsLoaded?.(root, state);
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
        const state = { config, dirty: false, loading: false, observer: null };
        states.set(root, state);

        placeControls(root, config);
        for (const feature of features) {
            feature.setup?.(root, state);
        }
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
            } else if (event.target.closest("[data-inline-controls-apply]")) {
                event.preventDefault();
                navigate(root, filterUrl(state.config, false));
            } else if (event.target.closest("[data-inline-controls-clear]")) {
                event.preventDefault();
                navigate(root, filterUrl(state.config, true));
            } else if (event.target.closest("[data-inline-controls-more]")) {
                event.preventDefault();
                loadMore(root);
            } else if (
                features.some((feature) => feature.click?.(event, root, state))
            ) {
                event.preventDefault();
            }
        });
        root.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && isFilterWidget(event.target)) {
                event.preventDefault();
                navigate(root, filterUrl(state.config, false));
            }
        });
        const markDirty = (event) => {
            // A feature's own widgets (e.g. the action checkboxes) are not
            // edits of the inline.
            if (
                features.some((feature) => feature.edit?.(event, root, state))
            ) {
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

    /**
     * Add a feature (the save button, the actions…), loaded as its own
     * script after this one. Its optional hooks get `(root, state)`:
     * `setup` when an inline is set up, `rowsLoaded` after infinite mode
     * appends rows, and `click` / `edit` also the event first, returning
     * true when they handled it.
     */
    function register(feature) {
        features.push(feature);
        for (const root of document.querySelectorAll(ROOT_SELECTOR)) {
            const state = states.get(root);
            if (state) {
                feature.setup?.(root, state);
            }
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
        formIndex,
        formRows,
        init,
        isSaved,
        loadMore,
        navigate,
        placeControls,
        query,
        register,
        reindexForm,
        reinitAdmin,
        setup,
        showStatus,
        stateOf: (root) => states.get(root),
        swapInline,
        updateElementIndex,
    };
})();
