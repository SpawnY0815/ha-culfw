import { defineConfig } from "vitest/config";

// The Lit packages that end up in the bundle are BSD-3-Clause licensed, which
// requires the notice to stay with the distributed file.
const banner = `/*! culfw week program card. Bundles Lit (lit, lit-html, lit-element and
 * @lit/reactive-element), BSD-3-Clause, Copyright 2017 Google LLC. The license
 * text is in docs/schedule-card.md. */`;

export default defineConfig({
  build: {
    outDir: "../custom_components/culfw/frontend",
    emptyOutDir: true,
    target: "es2022",
    minify: true,
    sourcemap: false,
    cssCodeSplit: false,
    lib: {
      entry: "src/index.ts",
      formats: ["es"],
      fileName: () => "fht-schedule-card.js",
    },
    rolldownOptions: {
      output: { banner },
    },
  },
  test: {
    include: ["test/unit/**/*.test.ts"],
    environment: "node",
    coverage: {
      provider: "v8",
      include: ["src/model.ts", "src/i18n.ts", "src/ws.ts"],
      reporter: ["text"],
      thresholds: {
        "src/model.ts": {
          lines: 90,
          functions: 90,
          branches: 90,
          statements: 90,
        },
      },
    },
  },
});
