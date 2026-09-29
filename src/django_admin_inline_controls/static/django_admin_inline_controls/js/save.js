/*
 * django-admin-inline-controls: the save button (inline_save_button).
 * Loaded after core.js, only by inlines that use it.
 */
(() => {
    const core = globalThis.DjangoAdminInlineControls;
    const SCOPE = ".inline-controls-save";

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

    /** POST only this inline's forms and swap in the re-rendered inline. */
    async function saveInline(root) {
        const state = core.stateOf(root);
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
            core.showStatus(root, "failed", config.messages.saveFailed, SCOPE);
        }
    }

    core.register({
        click(event, root) {
            if (!event.target.closest("[data-inline-controls-save]")) {
                return false;
            }
            saveInline(root);
            return true;
        },
    });

    Object.assign(core, { inlineFormData, saveInline });
})();
