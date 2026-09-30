/*
 * django-admin-inline-controls: django-unfold integration.
 *
 * Unfold binds its "Add another" and delete buttons once, on page load:
 * bind them on refreshed inlines and appended rows too.
 */
document.addEventListener("inline-controls:updated", (event) => {
    const handlers = {
        ".add-row": window.addInlineTemplateHandler,
        ".delete-template": window.deleteInlineTemplateHandler,
    };
    for (const [selector, handler] of Object.entries(handlers)) {
        if (typeof handler !== "function") {
            continue;
        }
        for (const el of event.target.querySelectorAll(selector)) {
            // The same listener is only added once.
            el.addEventListener("click", handler);
        }
    }
});
