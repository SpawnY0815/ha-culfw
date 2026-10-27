import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test as base } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";

const here = dirname(fileURLToPath(import.meta.url));
const BUNDLE = resolve(here, "../../../custom_components/culfw/frontend/fht-schedule-card.js");
const ORIGIN = "http://card.test";

// A policy as strict as a deployment could set it for scripts. The card needs no script
// of its own besides the one file, no eval, no request and no frame, so a violation
// shows up as an error in the console and fails the test.
const POLICY = [
  "default-src 'none'",
  "script-src 'self'",
  // The card positions its bars with style attributes, as the frontend of Home
  // Assistant does itself, so styles are the one thing that this policy allows inline.
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "connect-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join("; ");

const FILES: Record<string, [string, string]> = {
  "/": [resolve(here, "page.html"), "text/html"],
  "/mock-hass.js": [resolve(here, "mock-hass.js"), "text/javascript"],
  "/fht-schedule-card.js": [BUNDLE, "text/javascript"],
};

export interface Mount {
  language?: string;
  width?: number;
  unknown?: boolean;
  days?: Record<string, Record<string, unknown>>;
  state?: Record<string, unknown>;
}

export const test = base.extend<{
  card: (options?: Mount) => Promise<void>;
  // What the page wrote to the console as an error or warning. A test that provokes one
  // on purpose empties the list after it checked it.
  errors: string[];
}>({
  // eslint-disable-next-line no-empty-pattern -- Playwright reads the fixtures it needs from the pattern.
  errors: async ({}, use) => {
    await use([]);
  },
  card: async ({ page, errors }, use) => {
    await page.route(`${ORIGIN}/**`, async (route) => {
      const path = new URL(route.request().url()).pathname;
      const file = FILES[path];
      if (file === undefined) {
        await route.fulfill({ status: 404, body: "not found" });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: file[1],
        body: readFileSync(file[0]),
        headers: { "Content-Security-Policy": POLICY },
      });
    });
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error" || message.type() === "warning") {
        errors.push(message.text());
      }
    });
    await use(async (options = {}) => {
      await page.goto(`${ORIGIN}/`);
      await page.waitForFunction(() => customElements.get("fht-schedule-card") !== undefined);
      await page.evaluate((opts) => window.mountCard(opts), options as Record<string, unknown>);
    });
    expect(errors).toEqual([]);
  },
});

export { expect };

export interface TrackBox {
  left: number;
  width: number;
  top: number;
  height: number;
}

/** Return the box of the track that holds a handle, from its shadow root. */
export async function trackBox(handle: Locator): Promise<TrackBox> {
  return handle.evaluate((element) => {
    const rect = (element.closest(".track") as HTMLElement).getBoundingClientRect();
    return { left: rect.left, width: rect.width, top: rect.top, height: rect.height };
  });
}

export function minuteToX(box: TrackBox, minute: number): number {
  return box.left + (minute / 1440) * box.width;
}

export function handle(page: Page, day: string, period: number, edge: "start" | "end"): Locator {
  return page.getByRole("slider", { name: `${day}, period ${period}, ${edge}`, exact: true });
}

export async function sentCalls(page: Page, type: string): Promise<Record<string, unknown>[]> {
  const calls = await page.evaluate(() => window.__server.calls);
  return calls.filter((call) => call.type === type);
}
