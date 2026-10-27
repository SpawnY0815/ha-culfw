import type { Page } from "@playwright/test";
import { expect, handle, minuteToX, test, trackBox } from "./fixtures";

async function drag(page: Page, fromX: number, fromY: number, toX: number, toY = fromY) {
  await page.mouse.move(fromX, fromY);
  await page.mouse.down();
  const steps = 8;
  for (let step = 1; step <= steps; step += 1) {
    await page.mouse.move(fromX + ((toX - fromX) * step) / steps, toY);
  }
  await page.mouse.up();
}

test("drags the end of a period and snaps to 10 minutes", async ({ page, card }) => {
  await card();
  const end = handle(page, "Monday", 1, "end");
  await expect(end).toHaveAttribute("aria-valuetext", "08:30");
  const box = await trackBox(end);
  const y = box.top + box.height / 2;
  await drag(page, minuteToX(box, 8 * 60 + 30), y, minuteToX(box, 9 * 60 + 33), y);
  await expect(end).toHaveAttribute("aria-valuetext", "09:30");
  await expect(page.getByText("06:00–09:30 · 17:00–22:00")).toBeVisible();
  await expect(page.getByText("Edited", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("1 day changed")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save (1)" })).toBeEnabled();
});

test("shows the time above the handle while it is dragged", async ({ page, card }) => {
  await card();
  const start = handle(page, "Monday", 1, "start");
  const box = await trackBox(start);
  const y = box.top + box.height / 2;
  await page.mouse.move(minuteToX(box, 360), y);
  await page.mouse.down();
  await page.mouse.move(minuteToX(box, 300), y, { steps: 4 });
  await expect(page.locator(".bubble")).toHaveText("05:00");
  await page.mouse.up();
  await expect(page.locator(".bubble")).toHaveCount(0);
});

test("stops the end of a period at the next period", async ({ page, card }) => {
  await card();
  const end = handle(page, "Monday", 1, "end");
  const box = await trackBox(end);
  const y = box.top + box.height / 2;
  await drag(page, minuteToX(box, 8 * 60 + 30), y, minuteToX(box, 20 * 60), y);
  await expect(end).toHaveAttribute("aria-valuetext", "17:00");
});

test("moves a whole period by its bar and keeps its length", async ({ page, card }) => {
  await card();
  const start = handle(page, "Tuesday", 1, "start");
  const box = await trackBox(start);
  const y = box.top + box.height / 2;
  await drag(page, minuteToX(box, 7 * 60), y, minuteToX(box, 9 * 60), y);
  await expect(page.getByText("08:00–10:30")).toBeVisible();
});

test("adds a period with a tap on free space and not on a period", async ({ page, card }) => {
  await card();
  const start = handle(page, "Tuesday", 1, "start");
  const box = await trackBox(start);
  const y = box.top + box.height / 2;
  await page.mouse.click(minuteToX(box, 7 * 60), y);
  await expect(page.getByRole("slider", { name: "Tuesday, period 2, start" })).toHaveCount(0);
  await page.mouse.click(minuteToX(box, 12 * 60), y);
  await expect(page.getByRole("slider", { name: "Tuesday, period 2, start" })).toHaveAttribute(
    "aria-valuetext",
    "12:00",
  );
  await expect(page.getByText("06:00–08:30 · 12:00–13:00")).toBeVisible();
});

test("does not add a third period", async ({ page, card }) => {
  await card();
  const start = handle(page, "Monday", 1, "start");
  const box = await trackBox(start);
  await page.mouse.click(minuteToX(box, 12 * 60), box.top + box.height / 2);
  await expect(page.getByRole("slider", { name: /Monday, period 3/ })).toHaveCount(0);
  await expect(page.getByText("06:00–08:30 · 17:00–22:00")).toBeVisible();
});

test("returns to the saved program when a change is dragged back", async ({ page, card }) => {
  await card();
  const end = handle(page, "Tuesday", 1, "end");
  const box = await trackBox(end);
  const y = box.top + box.height / 2;
  await drag(page, minuteToX(box, 8 * 60 + 30), y, minuteToX(box, 10 * 60), y);
  await expect(page.getByText("1 day changed")).toBeVisible();
  await drag(page, minuteToX(box, 10 * 60), y, minuteToX(box, 8 * 60 + 30), y);
  await expect(page.getByText("No changes.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
});

test("drops the change when the browser cancels the drag", async ({ page, card }) => {
  await card();
  const end = handle(page, "Tuesday", 1, "end");
  const box = await trackBox(end);
  const y = box.top + box.height / 2;
  await page.mouse.move(minuteToX(box, 8 * 60 + 30), y);
  await page.mouse.down();
  await page.mouse.move(minuteToX(box, 10 * 60), y, { steps: 5 });
  await expect(end).toHaveAttribute("aria-valuetext", "10:00");
  await end.dispatchEvent("pointercancel", { pointerId: 1, pointerType: "mouse" });
  await expect(end).toHaveAttribute("aria-valuetext", "08:30");
  await page.mouse.up();
  await expect(page.getByText("No changes.")).toBeVisible();
});

test("ignores a drag with the right mouse button", async ({ page, card }) => {
  await card();
  const end = handle(page, "Tuesday", 1, "end");
  const box = await trackBox(end);
  const y = box.top + box.height / 2;
  await page.mouse.move(minuteToX(box, 8 * 60 + 30), y);
  await page.mouse.down({ button: "right" });
  await page.mouse.move(minuteToX(box, 10 * 60), y, { steps: 5 });
  await page.mouse.up({ button: "right" });
  await expect(end).toHaveAttribute("aria-valuetext", "08:30");
});
