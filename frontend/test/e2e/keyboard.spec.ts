import { expect, handle, test } from "./fixtures";

test("moves a handle with the arrow keys", async ({ page, card }) => {
  await card();
  const end = handle(page, "Monday", 1, "end");
  await end.focus();
  await page.keyboard.press("ArrowRight");
  await expect(end).toHaveAttribute("aria-valuetext", "08:40");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await expect(end).toHaveAttribute("aria-valuetext", "08:20");
  await page.keyboard.press("Shift+ArrowRight");
  await expect(end).toHaveAttribute("aria-valuetext", "09:20");
  await expect(end).toBeFocused();
});

test("keeps the range of a handle in its attributes", async ({ page, card }) => {
  await card();
  const end = handle(page, "Monday", 1, "end");
  await expect(end).toHaveAttribute("aria-valuemin", String(6 * 60 + 10));
  await expect(end).toHaveAttribute("aria-valuemax", String(17 * 60));
  await expect(end).toHaveAttribute("aria-valuenow", String(8 * 60 + 30));
  const start = handle(page, "Monday", 2, "start");
  await expect(start).toHaveAttribute("aria-valuemin", String(8 * 60 + 30));
  await expect(start).toHaveAttribute("aria-label", "Monday, period 2, start");
});

test("jumps to the limits with Home and End and stops at the neighbors", async ({ page, card }) => {
  await card();
  const end = handle(page, "Monday", 1, "end");
  await end.focus();
  await page.keyboard.press("End");
  await expect(end).toHaveAttribute("aria-valuetext", "17:00");
  const start = handle(page, "Monday", 1, "start");
  await start.focus();
  await page.keyboard.press("Home");
  await expect(start).toHaveAttribute("aria-valuetext", "00:00");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("ArrowDown");
  await expect(start).toHaveAttribute("aria-valuetext", "00:10");
  await page.keyboard.press("q");
  await expect(start).toHaveAttribute("aria-valuetext", "00:10");
});

test("removes a period with Delete and keeps the focus on the track", async ({ page, card }) => {
  await card();
  const start = handle(page, "Monday", 1, "start");
  await start.focus();
  await page.keyboard.press("Delete");
  await expect(page.getByText("17:00–22:00", { exact: true })).toBeVisible();
  await expect(page.getByRole("slider", { name: /Monday, period 2/ })).toHaveCount(0);
  await expect(page.getByRole("slider", { name: "Monday, period 1, start" })).toBeFocused();
  await expect(page.getByText("1 day changed")).toBeVisible();
});

test("edits the times in numeric fields", async ({ page, card }) => {
  await card();
  await page.getByRole("button", { name: "Monday", exact: true }).click();
  const field = page.getByRole("textbox", { name: "Monday, period 1, end time" });
  await expect(field).toHaveValue("08:30");
  await field.fill("9:00");
  await field.press("Enter");
  await expect(field).toHaveValue("09:00");
  await expect(page.getByText("06:00–09:00 · 17:00–22:00")).toBeVisible();
  await expect(handle(page, "Monday", 1, "end")).toHaveAttribute("aria-valuetext", "09:00");
});

test("says in words why a typed time is refused and keeps it until it is fixed", async ({
  page,
  card,
}) => {
  await card();
  await page.getByRole("button", { name: "Monday", exact: true }).click();
  const field = page.getByRole("textbox", { name: "Monday, period 1, end time" });

  await field.fill("09:05");
  await field.press("Enter");
  await expect(field).toHaveAttribute("aria-invalid", "true");
  await expect(field).toHaveValue("09:05");
  await expect(
    page.getByRole("alert").filter({ hasText: "not a multiple of 10 minutes" }),
  ).toBeVisible();
  await expect(page.getByText("06:00–08:30 · 17:00–22:00")).toBeVisible();

  await field.fill("soon");
  await field.press("Enter");
  await expect(page.getByRole("alert").filter({ hasText: "is not a time of day" })).toBeVisible();

  await field.fill("17:30");
  await field.press("Enter");
  await expect(page.getByRole("alert").filter({ hasText: "overlap" })).toBeVisible();

  const start = page.getByRole("textbox", { name: "Monday, period 1, start time" });
  await start.fill("09:00");
  await start.press("Enter");
  await expect(
    page.getByRole("alert").filter({ hasText: "must end after it starts" }).first(),
  ).toBeVisible();

  await field.fill("10:00");
  await field.press("Enter");
  await expect(field).toHaveAttribute("aria-invalid", "false");
  await expect(page.getByRole("alert").filter({ hasText: "overlap" })).toHaveCount(0);
});

test("steps a time by ten minutes with the buttons", async ({ page, card }) => {
  await card();
  await page.getByRole("button", { name: "Tuesday", exact: true }).click();
  await page.getByRole("button", { name: "Tuesday, period 1, end 10 minutes later" }).click();
  await expect(page.getByRole("textbox", { name: "Tuesday, period 1, end time" })).toHaveValue(
    "08:40",
  );
  await page.getByRole("button", { name: "Tuesday, period 1, start 10 minutes earlier" }).click();
  await expect(page.getByRole("textbox", { name: "Tuesday, period 1, start time" })).toHaveValue(
    "05:50",
  );
  await page.getByRole("button", { name: "Tuesday, period 1, end 10 minutes earlier" }).click();
  await page.getByRole("button", { name: "Tuesday, period 1, start 10 minutes later" }).click();
  await expect(page.getByText("No changes.")).toBeVisible();
});

test("adds, clears, resets and removes periods with the buttons", async ({ page, card }) => {
  await card();
  await page.getByRole("button", { name: "Tuesday", exact: true }).click();
  await page.getByRole("button", { name: "Add heating period" }).click();
  await expect(page.getByText("06:00–08:30 · 08:30–09:30")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add heating period" })).toBeDisabled();
  await page.getByRole("button", { name: "Merge touching periods" }).click();
  await expect(page.getByText("06:00–09:30")).toBeVisible();
  await page.getByRole("button", { name: "Clear day" }).click();
  await expect(page.getByText("Night temperature all day")).toBeVisible();
  await page.getByRole("button", { name: "Reset day" }).click();
  await expect(page.getByText("06:00–08:30", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Tuesday, remove period 1" }).click();
  await expect(page.getByText("Night temperature all day")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save (1)" })).toBeEnabled();
});

test("has labels for every control and groups the fields of a period", async ({ page, card }) => {
  await card();
  await page.getByRole("button", { name: "Monday", exact: true }).click();
  await expect(page.getByRole("group", { name: "Period 1" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Period 2" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Monday, heating periods" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Monday", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("region", { name: "Edit Monday" })).toBeVisible();
  const unnamed = await page
    .locator("button, input, [role=slider]")
    .evaluateAll(
      (elements) =>
        elements.filter(
          (element) =>
            !(element.getAttribute("aria-label") || (element as HTMLElement).innerText.trim()),
        ).length,
    );
  expect(unnamed).toBe(0);
});

test("moves a whole period with the keyboard", async ({ page, card }) => {
  await card();
  const mover = page.getByRole("slider", { name: "Tuesday, period 1, move", exact: true });
  await expect(mover).toHaveAttribute("aria-valuetext", "06:00–08:30");
  await mover.focus();
  await page.keyboard.press("ArrowRight");
  await expect(mover).toHaveAttribute("aria-valuetext", "06:10–08:40");
  await page.keyboard.press("Shift+ArrowLeft");
  await expect(mover).toHaveAttribute("aria-valuetext", "05:10–07:40");
  await page.keyboard.press("Home");
  await expect(mover).toHaveAttribute("aria-valuetext", "00:00–02:30");
  await page.keyboard.press("End");
  await expect(mover).toHaveAttribute("aria-valuetext", "21:30–24:00");
  await page.keyboard.press("Delete");
  await expect(page.getByText("Night temperature all day")).toBeVisible();
});
