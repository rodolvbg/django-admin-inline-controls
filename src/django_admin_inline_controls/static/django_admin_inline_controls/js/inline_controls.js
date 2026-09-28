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
            const node = document.importNode(fresh, true);
            // Keep collapsible inlines (<details>) open or closed as they were.
            const wasOpen = [...root.querySelectorAll("details")].map(
                (details) => details.open,
            );
            node.querySelectorAll("details").forEach((details, index) => {
                if (index < wasOpen.length) {
                    details.open = wasOpen[index];
                }
            });
            root.replaceWith(node);
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

        placeControls(root);
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
            }
        });
        root.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && isFilterWidget(event.target)) {
                event.preventDefault();
                navigate(root, filterUrl(state.config, false));
            }
        });
        const markDirty = (event) => {
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
        loadMore,
        navigate,
        placeControls,
        reindexForm,
        setup,
        updateElementIndex,
    };
})();
