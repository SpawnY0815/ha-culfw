import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

const MARKUP =
  '<img src=x onerror="window.pwned = true"><script>window.pwned = true</script>' as const;

async function nothingRan(page: Page) {
  expect(
    await page.evaluate(() => (window as unknown as { pwned?: boolean }).pwned),
  ).toBeUndefined();
  // Locators pierce the shadow roots of the card, so this finds markup anywhere in it.
  await expect(page.locator("fht-schedule-card img")).toHaveCount(0);
  await expect(page.locator("fht-schedule-card script")).toHaveCount(0);
}

test("shows the name of the entity as text", async ({ page, card }) => {
  await card();
  await page.evaluate((text) => {
    window.__card.hass = {
      ...window.__hass,
      states: { "climate.living_room": { state: "auto", attributes: { friendly_name: text } } },
    };
  }, MARKUP);

  await expect(page.getByRole("heading", { name: MARKUP })).toBeVisible();
  await nothingRan(page);
});

test("shows the error of the server as text, with and without a translation", async ({
  page,
  card,
}) => {
  await card();
  await page.getByRole("button", { name: "Monday", exact: true }).click();
  const field = page.getByRole("textbox", { name: "Monday, period 1, end time" });
  await field.fill("09:00");
  await field.press("Enter");

  await page.evaluate((text) => {
    window.__server.failNext = {
      code: "home_assistant_error",
      message: text,
      translation_key: "schedule_time_invalid",
      translation_placeholders: { day: text, value: text },
    };
  }, MARKUP);
  await page.getByRole("button", { name: "Save (1)" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "is not a time of day" })).toContainText(
    MARKUP,
  );
  await nothingRan(page);

  await page.evaluate((text) => {
    window.__server.failNext = { code: "home_assistant_error", message: text };
  }, MARKUP);
  await page.getByRole("button", { name: "Save (1)" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Saving failed" })).toContainText(MARKUP);
  await nothingRan(page);
});

test("shows the error of a refused subscription as text", async ({ page, card }) => {
  await card();
  await page.evaluate((text) => {
    window.__server.failSubscribe = { code: "home_assistant_error", message: text };
  }, MARKUP);
  await page.evaluate(() => window.__server.close());
  await page.getByRole("button", { name: "Try again" }).waitFor();

  await expect(page.getByRole("alert")).toContainText(MARKUP);
  await nothingRan(page);
});

test("refuses data of another form and recovers with the next good state", async ({
  page,
  card,
}) => {
  await card();
  const bad = [
    { days: null },
    {},
    "closed",
    null,
    42,
    [],
    { limits: { step_minutes: 0, max_periods: 2, day_end: "24:00" } },
  ];
  for (const event of bad) {
    await page.evaluate((data) => window.__server.pushRaw(data), event);
    await expect(
      page.getByText("The data from Home Assistant has an unexpected form."),
    ).toBeVisible();
    await page.evaluate(() => window.__server.push({}));
    await expect(page.getByText("Saved", { exact: true })).toHaveCount(7);
  }

  await page.evaluate(() =>
    window.__server.pushRaw({
      ...window.__server.state,
      days: {
        ...window.__server.state.days,
        monday: { status: "<b>bold</b>", periods: null, requested: null, pending_since: null },
      },
    }),
  );
  await expect(
    page.getByText("The data from Home Assistant has an unexpected form."),
  ).toBeVisible();
  await expect(page.locator("b")).toHaveCount(0);
});

test("runs under a policy that forbids inline scripts and requests", async ({
  page,
  card,
  errors,
}) => {
  await card();
  // The suite is only a proof of the card if the policy is in force, so ask the browser.
  const ran = await page.evaluate(async () => {
    const script = document.createElement("script");
    script.textContent = "window.pwned = true";
    document.head.append(script);
    const fetched = await fetch("/mock-hass.js").then(
      () => true,
      () => false,
    );
    return { script: (window as unknown as { pwned?: boolean }).pwned === true, fetched };
  });
  expect(ran).toEqual({ script: false, fetched: false });
  expect(errors).toHaveLength(3);
  expect(errors.join("\n")).toContain("Content Security Policy");
  errors.length = 0;
});
