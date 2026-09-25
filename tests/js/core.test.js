import { describe, expect, it } from "vitest";
import { exampleBehavior } from "../../src/django_admin_inline_controls/static/django_admin_inline_controls/js/core.js";

describe("exampleBehavior", () => {
    it("marks the element as initialized", () => {
        const el = document.createElement("div");
        exampleBehavior(el);
        expect(el.dataset.initialized).toBe("true");
    });
});
