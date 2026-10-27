import type { Page } from "@playwright/test";
import { expect, sentCalls, test } from "./fixtures";

async function edit(page: Page, day: string, end: string) {
  await page.getByRole("button", { name: day, exact: true }).click();
  const field = page.getByRole("textbox", { name: `${day}, period 1, end time` });
  await field.fill(end);
  await field.press("Enter");
}

test("saves only the days that changed", async ({ page, card }) => {
  await card();
  await edit(page, "Monday", "09:00");
  await edit(page, "Friday", "10:00");
  await expect(page.getByText("2 days changed")).toBeVisible();
  await page.getByRole("button", { name: "Save (2)" }).click();

  await expect(page.getByText("Sent to the thermostat: Monday, Friday.")).toBeAttached();
  const [call, ...others] = await sentCalls(page, "culfw/schedule/set");
  expect(others).toEqual([]);
  expect(call).toEqual({
    type: "culfw/schedule/set",
    entity_id: "climate.living_room",
    days: {
      monday: [
        { start: "06:00", end: "09:00" },
        { start: "17:00", end: "22:00" },
      ],
      friday: [{ start: "06:00", end: "10:00" }],
    },
  });
  await expect(page.getByText("No changes.")).toBeVisible();
  await expect(page.getByText("Queued", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("06:00–09:00 · 17:00–22:00")).toBeVisible();
});

test("follows a saved day from queued over sending to saved", async ({ page, card }) => {
  await card();
  await edit(page, "Tuesday", "09:00");
  await page.getByRole("button", { name: "Save (1)" }).click();
  const row = page.locator(".day-row", { hasText: "Tue" });
  await expect(row.getByText("Queued")).toBeVisible();

  await page.evaluate(() => window.__server.push({ days: { tuesday: { status: "sending" } } }));
  await expect(row.getByText("Sending")).toBeVisible();

  await page.evaluate(() =>
    window.__server.push({
      days: {
        tuesday: {
          status: "saved",
          periods: [{ start: "06:00", end: "09:00" }],
          requested: null,
          pending_since: null,
        },
      },
    }),
  );
  await expect(row.getByText("Saved")).toBeVisible();
  await expect(row.getByText("06:00–09:00")).toBeVisible();
});

test("offers to send a day again that was not confirmed", async ({ page, card }) => {
  await card({ days: { wednesday: { status: "unconfirmed" } } });
  await page.getByRole("button", { name: "Wednesday", exact: true }).click();
  await page.getByRole("button", { name: "Send again" }).click();
  const [call] = await sentCalls(page, "culfw/schedule/set");
  expect(call?.days).toEqual({ wednesday: [{ start: "06:00", end: "09:00" }] });
});

test("discards the changes", async ({ page, card }) => {
  await card();
  await edit(page, "Monday", "09:00");
  await edit(page, "Tuesday", "09:00");
  await page.getByRole("button", { name: "Discard" }).click();
  await expect(page.getByText("No changes.")).toBeVisible();
  await expect(page.getByText("06:00–08:30 · 17:00–22:00")).toBeVisible();
  expect(await sentCalls(page, "culfw/schedule/set")).toEqual([]);
  await expect(page.getByText("Changes discarded.")).toBeAttached();
});

test("shows an error of the integration in words and keeps the changes", async ({ page, card }) => {
  await card({ language: "de" });
  await page.evaluate(() => {
    window.__server.failNext = {
      code: "home_assistant_error",
      message: "The thermostat is silent.",
      translation_key: "send_device_silent",
      translation_placeholders: { code: "063 072", minutes: "50" },
    };
  });
  await page.getByRole("button", { name: "Montag", exact: true }).click();
  const field = page.getByRole("textbox", { name: "Montag, Phase 1, Ende als Uhrzeit" });
  await field.fill("09:00");
  await field.press("Enter");
  await page.getByRole("button", { name: "Speichern (1)" }).click();
  await expect(
    page.getByRole("alert").filter({
      hasText: "Speichern fehlgeschlagen: Das Thermostat 063 072 ist seit 50 Minuten still",
    }),
  ).toBeVisible();
  await expect(page.getByText("1 Tag geändert")).toBeVisible();

  await page.getByRole("button", { name: "Speichern (1)" }).click();
  await expect(page.getByText("An das Thermostat gesendet: Montag.")).toBeAttached();
  await expect(page.getByRole("alert").filter({ hasText: "fehlgeschlagen" })).toHaveCount(0);
});

test("shows the message of an error that it has no text for", async ({ page, card }) => {
  await card();
  await edit(page, "Monday", "09:00");
  await page.evaluate(() => {
    window.__server.failNext = { code: "home_assistant_error", message: "Boom happened" };
  });
  await page.getByRole("button", { name: "Save (1)" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Saving failed: Boom happened" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Dismiss" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Saving failed" })).toHaveCount(0);
});

test("confirms the overwrite of unread days before it sends", async ({ page, card }) => {
  await card({
    days: {
      thursday: { status: "unknown", periods: null },
      friday: { status: "unknown", periods: null },
    },
  });
  await page.getByRole("button", { name: "Thursday", exact: true }).click();
  await page.getByRole("button", { name: "Add heating period" }).click();
  await page.getByRole("button", { name: "Friday", exact: true }).click();
  await page.getByRole("button", { name: "Add heating period" }).click();
  await page.getByRole("button", { name: "Monday", exact: true }).click();
  const field = page.getByRole("textbox", { name: "Monday, period 1, end time" });
  await field.fill("09:00");
  await field.press("Enter");
  await page.getByRole("button", { name: "Save (3)" }).click();

  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("The days Thursday, Friday were never read");
  expect(await sentCalls(page, "culfw/schedule/set")).toEqual([]);

  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  expect(await sentCalls(page, "culfw/schedule/set")).toEqual([]);
  await expect(page.getByRole("button", { name: "Save (3)" })).toBeEnabled();

  await page.getByRole("button", { name: "Save (3)" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Overwrite" }).click();
  const [call] = await sentCalls(page, "culfw/schedule/set");
  expect(Object.keys(call?.days as object)).toEqual(["monday", "thursday", "friday"]);
});

test("copies a day to the weekdays and to the weekend", async ({ page, card }) => {
  await card();
  await page.getByRole("button", { name: "Monday", exact: true }).click();
  await page.getByRole("button", { name: "Copy to other days…" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Copy Monday to other days");
  await expect(dialog.getByRole("checkbox")).toHaveCount(6);
  await expect(dialog.getByRole("checkbox", { name: "Tuesday" })).toBeChecked();
  await expect(dialog.getByRole("checkbox", { name: "Saturday" })).not.toBeChecked();

  await dialog.getByRole("button", { name: "Weekend" }).click();
  await expect(dialog.getByRole("checkbox", { name: "Tuesday" })).not.toBeChecked();
  await expect(dialog.getByRole("checkbox", { name: "Sunday" })).toBeChecked();
  await dialog.getByRole("button", { name: "All days" }).click();
  await expect(dialog.getByRole("checkbox", { name: "Thursday" })).toBeChecked();
  await dialog.getByRole("button", { name: "Weekdays" }).click();
  await dialog.getByRole("checkbox", { name: "Saturday" }).check();
  await dialog.getByRole("checkbox", { name: "Friday" }).uncheck();
  await dialog.getByRole("button", { name: "Copy", exact: true }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByText("4 days changed")).toBeVisible();
  expect(await sentCalls(page, "culfw/schedule/set")).toEqual([]);
  await page.getByRole("button", { name: "Save (4)" }).click();
  const [call] = await sentCalls(page, "culfw/schedule/set");
  const days = call?.days as Record<string, unknown>;
  expect(Object.keys(days)).toEqual(["tuesday", "wednesday", "thursday", "saturday"]);
  for (const periods of Object.values(days)) {
    expect(periods).toEqual([
      { start: "06:00", end: "08:30" },
      { start: "17:00", end: "22:00" },
    ]);
  }
});

test("cancels the copy dialog with the keyboard", async ({ page, card }) => {
  await card();
  await page.getByRole("button", { name: "Monday", exact: true }).click();
  await page.getByRole("button", { name: "Copy to other days…" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByText("No changes.")).toBeVisible();
});

test("reads one day or the whole week on request", async ({ page, card }) => {
  await card({ days: { friday: { status: "unknown", periods: null } } });
  await page.getByRole("button", { name: "Friday", exact: true }).click();
  await page.getByRole("button", { name: "Read this day" }).click();
  await page.getByRole("button", { name: "Read week" }).click();
  const calls = await sentCalls(page, "culfw/schedule/refresh");
  expect(calls).toEqual([
    { type: "culfw/schedule/refresh", entity_id: "climate.living_room", days: ["friday"] },
    { type: "culfw/schedule/refresh", entity_id: "climate.living_room" },
  ]);
});

test("shows an error when reading fails", async ({ page, card }) => {
  await card();
  await page.evaluate(() => {
    window.__server.failNext = { code: "unauthorized", message: "Unauthorized" };
  });
  await page.getByRole("button", { name: "Read week" }).click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Reading failed: You are not allowed to change this thermostat." }),
  ).toBeVisible();
});

test("saves while the thermostat is silent and says that the changes wait", async ({
  page,
  card,
}) => {
  await card({ state: { reachable: false } });
  await edit(page, "Monday", "09:00");
  await expect(page.getByRole("button", { name: "Save (1)" })).toBeEnabled();
  await page.getByRole("button", { name: "Save (1)" }).click();
  expect((await sentCalls(page, "culfw/schedule/set")).length).toBe(1);
  await expect(page.getByText("sent when the thermostat answers")).toBeVisible();
});
