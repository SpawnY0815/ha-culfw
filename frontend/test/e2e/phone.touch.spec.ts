import type { Page } from "@playwright/test";
import { expect, handle, minuteToX, sentCalls, test, trackBox } from "./fixtures";

interface Point {
  x: number;
  y: number;
}

// Playwright has no touch drag, so the touch events go through the protocol of the
// browser, which treats them like a finger and honors touch-action.
async function touchDrag(page: Page, from: Point, to: Point, steps = 10) {
  const session = await page.context().newCDPSession(page);
  await session.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [from] });
  for (let step = 1; step <= steps; step += 1) {
    await session.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [
        {
          x: from.x + ((to.x - from.x) * step) / steps,
          y: from.y + ((to.y - from.y) * step) / steps,
        },
      ],
    });
  }
  await session.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await session.detach();
}

async function openDay(page: Page, day: string) {
  await page.getByRole("button", { name: new RegExp(`^${day}:`) }).tap();
}

test("shows a compact overview with one button for each day on a phone", async ({ page, card }) => {
  await card();
  await expect(
    page.getByRole("button", { name: /^Monday: 06:00–08:30 · 17:00–22:00, Saved$/ }),
  ).toBeVisible();
  await expect(page.getByRole("slider")).toHaveCount(0);
  await page.screenshot({ path: "test-results/screens/phone-overview-light.png" });
  const scrolls = await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth,
  );
  expect(scrolls).toBe(true);
});

test("opens the expanded day editor with large handles", async ({ page, card }) => {
  await card();
  await openDay(page, "Monday");
  await expect(page.getByRole("button", { name: "Back to the week" })).toBeVisible();
  await expect(page.getByRole("slider")).toHaveCount(6);
  const box = await handle(page, "Monday", 1, "end").boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(48);
  await expect(page.getByText("00", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: "test-results/screens/phone-editor-light.png" });
  await page.getByRole("button", { name: "Back to the week" }).tap();
  await expect(page.getByRole("slider")).toHaveCount(0);
});

test("drags a handle with a finger", async ({ page, card }) => {
  await card();
  await openDay(page, "Tuesday");
  const end = handle(page, "Tuesday", 1, "end");
  const box = await trackBox(end);
  const y = box.top + box.height / 2;
  await touchDrag(
    page,
    { x: minuteToX(box, 8 * 60 + 30), y },
    { x: minuteToX(box, 10 * 60 + 2), y },
  );
  await expect(end).toHaveAttribute("aria-valuetext", "10:00");
  await expect(page.getByRole("textbox", { name: "Tuesday, period 1, end time" })).toHaveValue(
    "10:00",
  );
  await expect(page.getByRole("button", { name: "Save (1)" })).toBeEnabled();
});

test("moves a period with a finger on its bar", async ({ page, card }) => {
  await card();
  await openDay(page, "Tuesday");
  const start = handle(page, "Tuesday", 1, "start");
  const box = await trackBox(start);
  const y = box.top + box.height / 2;
  await touchDrag(page, { x: minuteToX(box, 7 * 60), y }, { x: minuteToX(box, 9 * 60), y });
  await expect(page.getByRole("textbox", { name: "Tuesday, period 1, start time" })).toHaveValue(
    "08:00",
  );
  await expect(page.getByRole("textbox", { name: "Tuesday, period 1, end time" })).toHaveValue(
    "10:30",
  );
});

test("lets a vertical swipe on a period scroll the page and changes nothing", async ({
  page,
  card,
}) => {
  await card();
  await openDay(page, "Tuesday");
  const start = handle(page, "Tuesday", 1, "start");
  const box = await trackBox(start);
  const x = minuteToX(box, 7 * 60);
  const y = box.top + box.height / 2;
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await touchDrag(page, { x, y }, { x, y: y - 160 }, 12);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(40);
  await expect(page.getByText("No changes.")).toBeVisible();
});

test("lets a vertical swipe on the free track scroll the page and adds no period", async ({
  page,
  card,
}) => {
  await card();
  await openDay(page, "Tuesday");
  const box = await trackBox(handle(page, "Tuesday", 1, "start"));
  const x = minuteToX(box, 16 * 60);
  const y = box.top + box.height / 2;
  await touchDrag(page, { x, y }, { x, y: y - 160 }, 12);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(40);
  await expect(page.getByRole("slider", { name: /period 2/ })).toHaveCount(0);
});

test("adds a period with a tap", async ({ page, card }) => {
  await card();
  await openDay(page, "Tuesday");
  const box = await trackBox(handle(page, "Tuesday", 1, "start"));
  await page.touchscreen.tap(minuteToX(box, 16 * 60), box.top + box.height / 2);
  await expect(page.getByRole("textbox", { name: "Tuesday, period 2, start time" })).toHaveValue(
    "16:00",
  );
  await expect(page.getByRole("textbox", { name: "Tuesday, period 2, end time" })).toHaveValue(
    "17:00",
  );
});

test("edits and saves with the numeric fields on a phone", async ({ page, card }) => {
  await card({ language: "de" });
  await page.getByRole("button", { name: /^Samstag:/ }).tap();
  const field = page.getByRole("textbox", { name: "Samstag, Phase 1, Beginn als Uhrzeit" });
  await field.fill("08:00");
  await field.press("Enter");
  await page.getByRole("button", { name: "Speichern (1)" }).tap();
  const [call] = await sentCalls(page, "culfw/schedule/set");
  expect(call?.days).toEqual({ saturday: [{ start: "08:00", end: "24:00" }] });
  await page.screenshot({ path: "test-results/screens/phone-editor-de.png" });
});

test("shows the empty state on a phone", async ({ page, card }) => {
  await card({ unknown: true });
  await expect(page.getByRole("button", { name: "Read now" })).toBeVisible();
  await page.screenshot({ path: "test-results/screens/phone-empty.png" });
});

test("follows the dark theme with the variables of Home Assistant", async ({ page, card }) => {
  await card();
  await page.evaluate(() => document.documentElement.classList.add("dark"));
  await openDay(page, "Monday");
  await expect(page.getByRole("heading", { name: "Living room" })).toHaveCSS(
    "color",
    "rgb(225, 225, 225)",
  );
  await page.screenshot({ path: "test-results/screens/phone-editor-dark.png" });
  await page.getByRole("button", { name: "Back to the week" }).tap();
  await page.screenshot({ path: "test-results/screens/phone-overview-dark.png" });
});
