import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["coverage/", "node_modules/", "playwright-report/", "test-results/"] },
  js.configs.recommended,
  {
    files: ["**/*.ts"],
    extends: tseslint.configs.recommendedTypeChecked,
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
  },
  { files: ["src/**/*.ts", "test/e2e/**"], languageOptions: { globals: globals.browser } },
  {
    // Text from the server and from a dashboard must never run as code or as markup:
    // everything reaches the page through Lit templates, which escape it.
    files: ["src/**/*.ts"],
    rules: {
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "no-script-url": "error",
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["lit/directives/unsafe-*", "lit/static-html*"],
              message: "These write text as markup. Use a template with a value.",
            },
          ],
        },
      ],
      "no-restricted-properties": [
        "error",
        { property: "innerHTML", message: "Use a Lit template." },
        { property: "outerHTML", message: "Use a Lit template." },
        { property: "insertAdjacentHTML", message: "Use a Lit template." },
        { property: "srcdoc", message: "Do not write documents from text." },
        { object: "document", property: "write", message: "Use a Lit template." },
      ],
    },
  },
  {
    files: ["test/unit/**/*.ts", "*.config.*", "test/e2e/*.spec.ts"],
    languageOptions: { globals: globals.node },
  },
);
