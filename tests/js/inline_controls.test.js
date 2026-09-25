import { beforeAll, beforeEach, describe, expect, it } from "vitest";

let api;

beforeAll(async () => {
    await import(
        "../../src/django_admin_inline_controls/static/django_admin_inline_controls/js/inline_controls.js"
    );
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
        api.placeControls(root);

        const fieldset = root.querySelector("fieldset");
        expect(fieldset.querySelector("h2").nextElementSibling.className).toBe(
            "inline-controls-toolbar",
        );
        expect(fieldset.lastElementChild.className).toBe(
            "inline-controls-footer",
        );
    });
});
