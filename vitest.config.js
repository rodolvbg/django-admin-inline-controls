import { defineConfig } from "vitest/config";

export default defineConfig({
    test: {
        environment: "jsdom",
        include: ["tests/js/**/*.test.js"],
        coverage: {
            provider: "v8",
            reporter: [["text", { skipFull: true }]],
            include: [
                "src/django_admin_inline_controls/static/django_admin_inline_controls/**/*.js",
            ],
        },
    },
});
