import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const SOURCES = resolve(here, "../../src");
const BUNDLE = resolve(here, "../../../custom_components/culfw/frontend/fht-schedule-card.js");

// What would let text from the server, or from a dashboard, run as code or as markup.
// The card writes every such text through Lit templates, which escape it.
const FORBIDDEN: [string, RegExp][] = [
  [
    "a Lit directive that writes markup",
    /unsafeHTML|unsafeSVG|unsafeStatic|unsafe-html|unsafe-svg/,
  ],
  ["static HTML of Lit", /static-html/],
  ["eval", /\beval\s*\(/],
  ["a function made from text", /new\s+Function\b|\bFunction\s*\(/],
  ["a timer with code as text", /set(Timeout|Interval)\s*\(\s*["'`]/],
  ["document.write", /document\s*\.\s*write/],
  ["markup assigned to an element", /\.(outerHTML|srcdoc)\s*=|insertAdjacentHTML/],
  ["a javascript: address", /javascript:/i],
  ["a request of its own", /\bfetch\s*\(|XMLHttpRequest|sendBeacon|new\s+WebSocket|importScripts/],
  ["browser storage", /localStorage|sessionStorage|document\.cookie/],
  ["an inline event handler attribute", /setAttribute\s*\(\s*["']on/i],
];

function sourceFiles(): string[] {
  return readdirSync(SOURCES)
    .filter((name) => name.endsWith(".ts"))
    .map((name) => join(SOURCES, name));
}

describe("the card stays free of ways to run text", () => {
  it("has sources to look at", () => {
    expect(sourceFiles().length).toBeGreaterThanOrEqual(7);
  });

  it.each(FORBIDDEN)("does not use %s in the sources", (_name, pattern) => {
    for (const file of sourceFiles()) {
      expect(readFileSync(file, "utf8"), file).not.toMatch(pattern);
    }
  });

  it("assigns innerHTML nowhere in the sources", () => {
    for (const file of sourceFiles()) {
      expect(readFileSync(file, "utf8"), file).not.toMatch(/\.innerHTML\s*=/);
    }
  });

  it.each(FORBIDDEN)("does not ship %s in the bundle", (_name, pattern) => {
    expect(readFileSync(BUNDLE, "utf8")).not.toMatch(pattern);
  });

  it("assigns innerHTML in the bundle only to make the template of Lit", () => {
    const bundle = readFileSync(BUNDLE, "utf8");
    // Lit parses the static strings of a template with a template element, and the
    // values of a template never go through it.
    expect(bundle.match(/\.innerHTML\s*=/g)).toHaveLength(1);
    expect(bundle).toContain('createElement("template")');
  });
});
