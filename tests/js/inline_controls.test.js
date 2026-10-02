import {
    afterEach,
    beforeAll,
    beforeEach,
    describe,
    expect,
    it,
    vi,
} from "vitest";

let api;

beforeAll(async () => {
    const js =
        "../../src/django_admin_inline_controls/static/django_admin_inline_controls/js";
    await import(`${js}/core.js`);
    await import(`${js}/save.js`);
    await import(`${js}/actions.js`);
    await import(`${js}/contrib/unfold.js`);
    api = globalThis.DjangoAdminInlineControls;
});

const config = (overrides = {}) => ({
    prefix: "books",
    mode: "pages",
    ajax: true,
    pageParam: "books-page",
    filterPrefix: "books-f",
    filterFormId: "books-inline-controls-filters",
    filterParams: ["books-f-status", "books-f-q", "books-f-tags"],
    ordering: [],
    nextUrl: null,
    messages: { sortRemove: "Remove", sortToggle: "Toggle", unsaved: "Sure?" },
    // Mirrors DEFAULT_SELECTORS in controls.py.
    selectors: {
        container: [".inline-group fieldset"],
        heading: ["h2"],
        footer_parent: [":scope > details"],
        table_head: [".inline-group table thead"],
        column_header: ["th.column-{name}"],
        row_label: [
            ":scope > td.original > p",
            ":scope > h3",
            ":scope > td.original",
        ],
        tabular_rows: [
            "{group} .tabular.inline-related tbody:first > tr.form-row",
        ],
        stacked_rows: ["{group} .inline-related"],
    },
    ...overrides,
});

describe("updateElementIndex", () => {
    it("rewrites id, name, for and aria-describedby", () => {
        const el = document.createElement("input");
        el.id = "id_books-3-title";
        el.name = "books-3-title";
        el.setAttribute(
            "aria-describedby",
            "id_books-3-title_helptext id_books-3-title_error",
        );
        api.updateElementIndex(el, "books", 7);

        expect(el.id).toBe("id_books-7-title");
        expect(el.name).toBe("books-7-title");
        expect(el.getAttribute("aria-describedby")).toBe(
            "id_books-7-title_helptext id_books-7-title_error",
        );
    });

    it("handles __prefix__ and prefixes containing dashes", () => {
        const el = document.createElement("label");
        el.setAttribute(
            "for",
            "id_demo-book-content_type-object_id-__prefix__-title",
        );
        api.updateElementIndex(el, "demo-book-content_type-object_id", 2);

        expect(el.getAttribute("for")).toBe(
            "id_demo-book-content_type-object_id-2-title",
        );
    });

    it("does not touch another inline whose prefix extends this one", () => {
        const el = document.createElement("input");
        el.name = "books-2-0-title";
        api.updateElementIndex(el, "books-2", 5);
        expect(el.name).toBe("books-2-5-title");
    });
});

describe("formRows / reindexForm", () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <div id="books-group">
              <table><tbody>
                <tr id="books-0" class="form-row has_original"><td><input name="books-0-title" id="id_books-0-title"></td></tr>
                <tr id="books-1" class="form-row"><td><input name="books-1-title" id="id_books-1-title"></td></tr>
                <tr id="books-empty" class="form-row empty-form"><td><input name="books-__prefix__-title"></td></tr>
                <tr id="books-2-0"><td></td></tr>
              </tbody></table>
            </div>`;
    });

    it("finds only this formset's rows", () => {
        const group = document.getElementById("books-group");
        expect(api.formRows(group, "books").map((row) => row.id)).toEqual([
            "books-0",
            "books-1",
            "books-empty",
        ]);
    });

    it("renumbers a row and its fields", () => {
        const row = document.getElementById("books-1");
        api.reindexForm(row, "books", 9);

        expect(row.id).toBe("books-9");
        expect(row.querySelector("input").name).toBe("books-9-title");
        expect(row.querySelector("input").id).toBe("id_books-9-title");
    });
});

describe("filterUrl", () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <select name="books-f-status" form="books-inline-controls-filters">
              <option value="">---</option><option value="published" selected>P</option>
            </select>
            <input name="books-f-q" form="books-inline-controls-filters" value="">
            <select name="books-f-tags" multiple form="books-inline-controls-filters">
              <option value="1" selected></option><option value="2"></option><option value="3" selected></option>
            </select>
            <input name="unrelated" value="x">`;
    });

    it("replaces this inline's filters and resets its page", () => {
        const url = new URL(
            api.filterUrl(
                config(),
                false,
                "http://x/change/?books-page=3&books-f-q=old&articles-page=2",
            ),
        );

        expect(url.searchParams.get("books-page")).toBeNull();
        expect(url.searchParams.get("books-f-q")).toBeNull();
        expect(url.searchParams.get("books-f-status")).toBe("published");
        expect(url.searchParams.getAll("books-f-tags")).toEqual(["1", "3"]);
        expect(url.searchParams.get("articles-page")).toBe("2");
        expect(url.searchParams.get("unrelated")).toBeNull();
    });

    it("clears every filter", () => {
        const url = new URL(
            api.filterUrl(
                config(),
                true,
                "http://x/?books-f-status=draft&books-o=title",
            ),
        );

        expect([...url.searchParams.keys()]).toEqual(["books-o"]);
    });
});

describe("decorateHeaders / placeControls", () => {
    const render = () => {
        document.body.innerHTML = `
            <div class="inline-controls" id="books-inline-controls">
              <div class="inline-controls-toolbar"><div class="inline-controls-ordering"></div></div>
              <div class="inline-group" id="books-group">
                <fieldset class="module"><h2>Books</h2>
                  <table><thead><tr>
                    <th class="column-title required">Title <img class="help"></th>
                    <th class="column-pages">Pages</th>
                  </tr></thead></table>
                </fieldset>
              </div>
              <nav class="inline-controls-footer"></nav>
            </div>`;
        return document.getElementById("books-inline-controls");
    };

    it("turns headers into sort links", () => {
        const root = render();
        const all = api.decorateHeaders(
            root,
            config({
                ordering: [
                    {
                        name: "title",
                        direction: "descending",
                        priority: 1,
                        toggleUrl: "?books-o=title",
                        removeUrl: "?",
                    },
                    {
                        name: "pages",
                        direction: "",
                        priority: 0,
                        toggleUrl: "?books-o=pages,-title",
                        removeUrl: "?books-o=-title",
                    },
                ],
            }),
        );

        expect(all).toBe(true);
        const title = root.querySelector("th.column-title");
        expect(title.classList.contains("inline-controls-descending")).toBe(
            true,
        );
        const toggle = title.querySelector(".inline-controls-sort-toggle");
        expect(toggle.textContent).toBe("Title");
        expect(toggle.getAttribute("href")).toBe("?books-o=title");
        expect(title.querySelector("img.help")).not.toBeNull();
        expect(
            title
                .querySelector(".inline-controls-sort-remove")
                .getAttribute("href"),
        ).toBe("?");
        expect(
            root.querySelector("th.column-pages .inline-controls-sort-remove"),
        ).toBeNull();
    });

    it("reports headers it could not find", () => {
        const root = render();
        const all = api.decorateHeaders(
            root,
            config({
                ordering: [
                    {
                        name: "missing",
                        direction: "",
                        priority: 0,
                        toggleUrl: "?",
                        removeUrl: "?",
                    },
                ],
            }),
        );
        expect(all).toBe(false);
    });

    it("moves the toolbar under the heading and the footer into the fieldset", () => {
        const root = render();
        api.placeControls(root, config());

        const fieldset = root.querySelector("fieldset");
        expect(fieldset.querySelector("h2").nextElementSibling.className).toBe(
            "inline-controls-toolbar",
        );
        expect(fieldset.lastElementChild.className).toBe(
            "inline-controls-footer",
        );
    });
});

describe("inlineFormData", () => {
    it("collects only this inline's submittable fields", () => {
        document.body.innerHTML = `
            <form id="author_form">
              <input name="csrfmiddlewaretoken" value="tok">
              <input name="name" value="Parent">
              <div id="books-group">
                <input name="books-TOTAL_FORMS" value="2">
                <input name="books-0-title" value="A">
                <input type="checkbox" name="books-0-featured" checked>
                <input type="checkbox" name="books-1-featured">
                <select name="books-0-tags" multiple>
                  <option value="1" selected></option><option value="2" selected></option>
                </select>
                <textarea name="books-0-notes">n</textarea>
                <input name="books-__prefix__-title" value="template">
                <input name="books-1-title" value="disabled" disabled>
                <input name="books-f-q" form="books-inline-controls-filters" value="filter">
                <button type="submit" name="books-0-button" value="x"></button>
              </div>
              <div id="books-2-group"><input name="books-2-0-title" value="other"></div>
            </form>`;
        const data = api.inlineFormData(
            document.getElementById("books-group"),
            document.getElementById("author_form"),
        );

        expect([...data.entries()]).toEqual([
            ["csrfmiddlewaretoken", "tok"],
            ["books-TOTAL_FORMS", "2"],
            ["books-0-title", "A"],
            ["books-0-featured", "on"],
            ["books-0-tags", "1"],
            ["books-0-tags", "2"],
            ["books-0-notes", "n"],
        ]);
    });
});

describe("action checkboxes", () => {
    it("adds a checkbox per saved row and detaches it from the form", () => {
        document.body.innerHTML = `
            <form>
              <div class="inline-controls" id="books-inline-controls">
                <div class="inline-controls-toolbar"><div class="inline-controls-actions">
                  <span data-inline-controls-selection></span>
                  <a data-inline-controls-select-across hidden></a>
                </div></div>
                <div class="inline-group js-inline-admin-formset" id="books-group">
                  <fieldset class="module"><h2>Books</h2><table>
                    <thead><tr><th class="original"></th></tr></thead>
                    <tbody>
                      <tr id="books-0" class="form-row has_original"><td class="original"><p>Book 7</p><input type="hidden" name="books-0-id" value="7"></td></tr>
                      <tr id="books-1" class="form-row has_original"><td class="original"><input type="hidden" name="books-1-id" value="9"></td></tr>
                      <tr id="books-2" class="form-row"><td class="original"><input type="hidden" name="books-2-id" value=""></td></tr>
                    </tbody>
                  </table></fieldset>
                </div>
              </div>
            </form>`;
        const root = document.getElementById("books-inline-controls");
        root.dataset.inlineControls = JSON.stringify(
            config({
                actionUrl: "/action/",
                actionsFormId: "books-inline-controls-actions",
                actions: [{ name: "go", confirmation: null }],
                pkName: "id",
                totalCount: 30,
                messages: {
                    ...config().messages,
                    selected: "%(sel)s of %(cnt)s selected",
                    selectAll: "Select all %(total)s",
                    allSelected: "All %(total)s selected",
                },
            }),
        );
        api.setup(root);

        const boxes = root.querySelectorAll(".inline-controls-select");
        expect([...boxes].map((box) => box.value)).toEqual(["7", "9"]);
        expect(boxes[0].getAttribute("form")).toBe(
            "books-inline-controls-actions",
        );
        expect(boxes[0].form).toBeNull();
        expect(boxes[0].parentElement.tagName).toBe("P");
        expect(boxes[1].parentElement.tagName).toBe("TD");
        expect(
            root.querySelector(
                ".inline-controls-actions > .inline-controls-select-all",
            ),
        ).not.toBeNull();
        const label = root.querySelector("[data-inline-controls-selection]");
        expect(label.textContent).toBe("0 of 30 selected");

        const toggle = root.querySelector(".inline-controls-select-all");
        toggle.checked = true;
        toggle.dispatchEvent(new Event("change", { bubbles: true }));
        expect(label.textContent).toBe("2 of 30 selected");
        const across = root.querySelector(
            "[data-inline-controls-select-across]",
        );
        expect(across.hidden).toBe(false);
        expect(across.textContent).toBe("Select all 30");

        across.click();
        expect(label.textContent).toBe("All 30 selected");
        expect(across.hidden).toBe(true);

        boxes[0].checked = false;
        boxes[0].dispatchEvent(new Event("change", { bubbles: true }));
        expect(label.textContent).toBe("1 of 30 selected");
        expect(toggle.indeterminate).toBe(true);
    });
});

describe("custom selectors", () => {
    const themed = () => {
        document.body.innerHTML = `
            <div class="inline-controls" id="books-inline-controls">
              <div class="inline-controls-toolbar"></div>
              <section class="card" id="books-group">
                <header class="card-title">Books</header>
                <table class="grid"><thead><tr>
                  <th data-col="title">Title</th>
                </tr></thead></table>
              </section>
              <nav class="inline-controls-footer"></nav>
            </div>`;
        return document.getElementById("books-inline-controls");
    };
    const themedConfig = (overrides) =>
        config({
            ordering: [
                {
                    name: "title",
                    direction: "",
                    priority: 0,
                    toggleUrl: "?o=title",
                    removeUrl: "?",
                },
            ],
            selectors: {
                ...config().selectors,
                container: [".card"],
                heading: [".card-title"],
                table_head: ["table.grid thead"],
                column_header: ['th[data-col="{name}"]'],
            },
            ...overrides,
        });

    it("places the toolbar and footer in another structure", () => {
        const root = themed();
        api.placeControls(root, themedConfig());

        const card = root.querySelector(".card");
        expect(
            card.querySelector(".card-title").nextElementSibling.className,
        ).toBe("inline-controls-toolbar");
        expect(card.lastElementChild.className).toBe("inline-controls-footer");
    });

    it("finds sortable headers with another selector", () => {
        const root = themed();

        expect(api.decorateHeaders(root, themedConfig())).toBe(true);
        expect(
            root.querySelector(
                'th[data-col="title"] .inline-controls-sort-toggle',
            ).textContent,
        ).toBe("Title");
    });

    it("tries a key's selectors in order", () => {
        const root = themed();
        const found = api.query(
            root,
            themedConfig({
                selectors: { container: [".missing", "section", ".card"] },
            }),
            "container",
        );

        expect(found.id).toBe("books-group");
    });

    it("lets a listener place the controls itself", () => {
        const root = themed();
        const handler = (event) => {
            event.preventDefault();
            document.body.prepend(event.detail.toolbar);
        };
        root.addEventListener("inline-controls:place", handler);
        api.placeControls(root, themedConfig());
        root.removeEventListener("inline-controls:place", handler);

        expect(document.body.firstElementChild.className).toBe(
            "inline-controls-toolbar",
        );
        expect(root.querySelector(".card .inline-controls-footer")).toBeNull();
    });
});

describe("register", () => {
    it("sets up a feature on inlines already set up", () => {
        document.body.innerHTML = `
            <div class="inline-controls" id="books-inline-controls"></div>`;
        const root = document.getElementById("books-inline-controls");
        root.dataset.inlineControls = JSON.stringify(config());
        api.setup(root);

        const seen = [];
        api.register({ setup: (el, state) => seen.push([el, state]) });
        expect(seen).toEqual([[root, api.stateOf(root)]]);
    });

    it("lets a feature handle clicks and keep its widgets from marking the inline dirty", () => {
        document.body.innerHTML = `
            <div class="inline-controls" id="books-inline-controls">
              <button data-custom></button><input name="books-0-title">
            </div>`;
        const root = document.getElementById("books-inline-controls");
        root.dataset.inlineControls = JSON.stringify(config());
        let clicks = 0;
        api.register({
            click: (event) => {
                if (event.target.matches("[data-custom]")) {
                    clicks += 1;
                    return true;
                }
                return false;
            },
            edit: (event) => event.target.matches("[data-custom]"),
        });
        api.setup(root);
        const button = root.querySelector("[data-custom]");
        const click = new MouseEvent("click", {
            bubbles: true,
            cancelable: true,
        });
        button.dispatchEvent(click);
        expect(clicks).toBe(1);
        expect(click.defaultPrevented).toBe(true);

        button.dispatchEvent(new Event("change", { bubbles: true }));
        expect(api.stateOf(root).dirty).toBe(false);
        root.querySelector("input").dispatchEvent(
            new Event("input", { bubbles: true }),
        );
        expect(api.stateOf(root).dirty).toBe(true);
    });
});

describe("Unfold markup", () => {
    // Mirrors UNFOLD_SELECTORS in contrib/unfold.py.
    const unfold = (overrides = {}) =>
        config({
            selectors: {
                ...config().selectors,
                container: [
                    "[data-inline-type] > fieldset",
                    "[data-inline-type] > .inline-related > fieldset",
                ],
                table_head: ["table thead"],
                form_rows: ['[id="{prefix}-data"] > .form-group'],
                saved_row: [".original"],
                row_label: [
                    ':scope > tr > td > p[class~="group/title"]',
                    ":scope > tr.form-row > td",
                ],
            },
            ...overrides,
        });

    const render = () => {
        document.body.innerHTML = `
            <form>
              <div class="inline-controls" id="books-inline-controls">
                <div class="inline-controls-toolbar"><div class="inline-controls-actions">
                  <span data-inline-controls-selection></span>
                </div></div>
                <div id="books-group" data-inline-type="tabular">
                  <div class="tabular inline-related"><fieldset class="module">
                    <h2>Books</h2>
                    <table id="books-data">
                      <thead><tr><th class="column-title"><span><span>Title</span></span></th></tr></thead>
                      <tbody class="form-group original">
                        <tr><td><p class="group/title flex">Book 7</p></td></tr>
                        <tr class="form-row"><td><input type="hidden" name="books-0-id" value="7"><input name="books-0-title"></td></tr>
                      </tbody>
                      <tbody class="form-group template">
                        <tr class="form-row"><td><input name="books-1-title"></td></tr>
                      </tbody>
                      <tbody class="form-group template empty-form">
                        <tr class="form-row"><td><input name="books-__prefix__-title"></td></tr>
                      </tbody>
                    </table>
                  </fieldset></div>
                </div>
              </div>
            </form>`;
        return document.getElementById("books-inline-controls");
    };

    it("finds the forms by their fields' names", () => {
        const root = render();
        const group = document.getElementById("books-group");
        const rows = api.formRows(group, "books", unfold());

        expect(rows).toHaveLength(3);
        expect(rows.map((row) => api.formIndex(row, "books"))).toEqual([
            0,
            1,
            null,
        ]);
        expect(rows.map((row) => api.isSaved(row, unfold()))).toEqual([
            true,
            false,
            false,
        ]);
        // Without form_rows, only ids count.
        expect(api.formRows(group, "books", config())).toEqual([]);
        expect(root).not.toBeNull();
    });

    it("places the toolbar, sort links and checkboxes", () => {
        const root = render();
        root.dataset.inlineControls = JSON.stringify(
            unfold({
                ordering: [
                    {
                        name: "title",
                        direction: "",
                        priority: 0,
                        toggleUrl: "?books-o=title",
                        removeUrl: "",
                    },
                ],
                actionUrl: "/action/",
                actionsFormId: "books-inline-controls-actions",
                actions: [{ name: "go", confirmation: null }],
                pkName: "id",
                messages: {
                    ...config().messages,
                    selected: "%(sel)s of %(cnt)s selected",
                    selectAll: "",
                    allSelected: "",
                },
            }),
        );
        api.setup(root);

        const heading = root.querySelector("fieldset > h2");
        expect(heading.nextElementSibling.className).toBe(
            "inline-controls-toolbar",
        );
        const link = root.querySelector("th.column-title > a");
        expect(link.textContent).toBe("Title");
        expect(link.firstElementChild.tagName).toBe("SPAN");
        const box = root.querySelector(".inline-controls-select");
        expect(box.value).toBe("7");
        expect(box.parentElement.textContent).toBe("Book 7");
        expect(root.querySelectorAll(".inline-controls-select")).toHaveLength(
            1,
        );
    });

    it("re-binds Unfold's add and delete buttons after an update", () => {
        document.body.innerHTML = `
            <div id="fresh"><a class="add-row"></a><a class="delete-template"></a></div>`;
        const calls = [];
        window.addInlineTemplateHandler = () => calls.push("add");
        window.deleteInlineTemplateHandler = () => calls.push("delete");
        const fresh = document.getElementById("fresh");
        fresh.dispatchEvent(
            new CustomEvent("inline-controls:updated", { bubbles: true }),
        );
        fresh.dispatchEvent(
            new CustomEvent("inline-controls:updated", { bubbles: true }),
        );
        fresh.querySelector(".add-row").click();
        fresh.querySelector(".delete-template").click();

        expect(calls).toEqual(["add", "delete"]);
        delete window.addInlineTemplateHandler;
        delete window.deleteInlineTemplateHandler;
    });
});

describe("row actions", () => {
    const render = () => {
        document.body.innerHTML = `
            <form id="author_form">
              <input name="csrfmiddlewaretoken" value="tok">
              <div class="inline-controls" id="books-inline-controls">
                <div class="inline-group" id="books-group">
                  <fieldset class="module"><h2>Books</h2><table><tbody>
                    <tr id="books-0" class="form-row has_original"><td>
                      <input type="hidden" name="books-0-id" value="7">
                      <span class="inline-controls-row-actions" data-inline-controls-row-actions hidden>
                        <button type="button" data-inline-controls-row-action="toggle" data-pk="7">Feature</button>
                        <button type="button" data-inline-controls-row-action="delete" data-pk="7" data-confirmation="Delete?">Delete</button>
                      </span>
                    </td></tr>
                  </tbody></table></fieldset>
                </div>
                <div class="inline-controls-footer"><span class="inline-controls-row-actions-status"><span class="inline-controls-status"></span></span></div>
              </div>
            </form>`;
        const root = document.getElementById("books-inline-controls");
        root.dataset.inlineControls = JSON.stringify(
            config({
                actionUrl: "/action/",
                actionsFormId: "books-inline-controls-actions",
                actions: [],
                rowActions: true,
                pkName: "id",
                messages: { ...config().messages, actionFailed: "Failed" },
            }),
        );
        return root;
    };

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it("shows the buttons without adding the bulk checkboxes", () => {
        const root = render();
        api.setup(root);

        expect(
            root.querySelector("[data-inline-controls-row-actions]").hidden,
        ).toBe(false);
        expect(root.querySelector(".inline-controls-select")).toBeNull();
    });

    it("posts the row's action and swaps in the response", async () => {
        const root = render();
        api.setup(root);
        const fresh = root.outerHTML.replace("Feature", "Unfeature");
        const fetch = vi.fn().mockResolvedValue({
            ok: true,
            redirected: false,
            headers: new Headers(),
            text: () =>
                Promise.resolve(
                    `<div id="books-inline-controls-response" data-status="done" data-message="Featured.">${fresh}</div>`,
                ),
        });
        vi.stubGlobal("fetch", fetch);

        await api.runRowAction(root, root.querySelector("[data-pk]"));

        const [, options] = fetch.mock.calls[0];
        expect([...options.body.entries()]).toEqual([
            ["csrfmiddlewaretoken", "tok"],
            ["_inline_controls_loaded", "1"],
            ["row_action", "toggle"],
            ["_selected_action", "7"],
        ]);
        const node = document.getElementById("books-inline-controls");
        expect(node.textContent).toContain("Unfeature");
        expect(
            node.querySelector(".inline-controls-row-actions-status")
                .textContent,
        ).toBe("Featured.");
    });

    it("asks for the confirmation first and reports failures", async () => {
        const root = render();
        api.setup(root);
        const fetch = vi.fn().mockRejectedValue(new Error("down"));
        vi.stubGlobal("fetch", fetch);
        const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
        const button = root.querySelector(
            '[data-inline-controls-row-action="delete"]',
        );

        await api.runRowAction(root, button);
        expect(confirm).toHaveBeenCalledWith("Delete?");
        expect(fetch).not.toHaveBeenCalled();

        confirm.mockReturnValue(true);
        button.click();
        await vi.waitFor(() =>
            expect(
                root.querySelector(".inline-controls-row-actions-status")
                    .textContent,
            ).toBe("Failed"),
        );
    });
});
