import { expect, test } from "./fixtures";

test("renders the header, the seven days and the status of each", async ({ page, card }) => {
  await card();
  await expect(page.getByRole("heading", { name: "Living room" })).toBeVisible();
  await expect(page.getByText("Week program", { exact: true })).toBeVisible();
  await expect(page.getByText("Day21.0 °C")).toBeVisible();
  await expect(page.getByText("Night17.0 °C")).toBeVisible();
  await expect(page.getByText("Thermostat reachable")).toBeVisible();

  const names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  for (const name of names) {
    await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
  }
  await expect(page.getByText("06:00–08:30 · 17:00–22:00")).toBeVisible();
  await expect(page.getByText("Saved", { exact: true })).toHaveCount(7);
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  await expect(page.getByText("No changes.")).toBeVisible();
  await page.screenshot({ path: "test-results/screens/desktop-light.png" });
});

test("shows the program of a day that is on its way as pending", async ({ page, card }) => {
  await card({
    days: {
      wednesday: {
        status: "sending",
        periods: [{ start: "06:00", end: "09:00" }],
        requested: [{ start: "05:00", end: "09:00" }],
        pending_since: "2026-10-20T10:00:00+00:00",
      },
      thursday: { status: "queued", requested: [], periods: [{ start: "06:00", end: "09:00" }] },
      friday: { status: "unconfirmed" },
      saturday: { status: "error" },
    },
  });
  await expect(page.getByText("05:00–09:00")).toBeVisible();
  await expect(page.getByText("Sending", { exact: true })).toBeVisible();
  await expect(page.getByText("Queued", { exact: true })).toBeVisible();
  await expect(page.getByText("Not confirmed", { exact: true })).toBeVisible();
  await expect(page.getByText("Error", { exact: true })).toBeVisible();
  await expect(page.getByText("Night temperature all day")).toBeVisible();
});

test("follows the pushes of the server", async ({ page, card }) => {
  await card();
  await page.evaluate(() =>
    window.__server.push({
      day_temperature: 22.5,
      days: { tuesday: { status: "saved", periods: [{ start: "05:00", end: "06:00" }] } },
    }),
  );
  await expect(page.getByText("Day22.5 °C")).toBeVisible();
  await expect(page.getByText("05:00–06:00")).toBeVisible();
});

test("shows the texts in German", async ({ page, card }) => {
  await card({ language: "de" });
  await expect(page.getByText("Wochenprogramm", { exact: true })).toBeVisible();
  await expect(page.getByText("Tag21,0 °C")).toBeVisible();
  await expect(page.getByText("Nacht17,0 °C")).toBeVisible();
  await expect(page.getByText("Thermostat erreichbar")).toBeVisible();
  await expect(page.getByRole("button", { name: "Montag", exact: true })).toBeVisible();
  await expect(page.getByText("Gespeichert", { exact: true })).toHaveCount(7);
  await expect(page.getByText("Keine Änderungen.")).toBeVisible();
});

test("shows an empty state with a button to read the program", async ({ page, card }) => {
  await card({ unknown: true });
  await expect(page.getByText("The week program has not been read yet.")).toBeVisible();
  await expect(page.getByText("about 35 minutes")).toBeVisible();
  await page.getByRole("button", { name: "Read now" }).click();
  await expect(page.getByText("Reading was requested.")).toHaveCount(2);
  const calls = await page.evaluate(() => window.__server.calls);
  expect(calls.at(-1)).toEqual({
    type: "culfw/schedule/refresh",
    entity_id: "climate.living_room",
  });

  await page.evaluate(() =>
    window.__server.push({
      days: { monday: { status: "saved", periods: [{ start: "06:00", end: "07:00" }] } },
    }),
  );
  await expect(page.getByText("The week program has not been read yet.")).toBeHidden();
  await expect(page.locator(".chip", { hasText: "Not read" })).toHaveCount(6);
  await page.screenshot({ path: "test-results/screens/desktop-partly-read.png" });
});

test("lets the user edit a program that was never read", async ({ page, card }) => {
  await card({ unknown: true });
  await page.getByRole("button", { name: "Edit an empty program" }).click();
  await expect(page.getByText("Not read yet")).toHaveCount(7);
  await expect(page.getByText("The week program has not been read yet.")).toBeHidden();
});

test("warns when the radio stick is disconnected or the thermostat is silent", async ({
  page,
  card,
}) => {
  await card({ state: { link_up: false, reachable: false } });
  await expect(page.getByText("Radio stick disconnected").first()).toBeVisible();
  await expect(page.getByText("sent when the radio stick is back")).toBeVisible();

  await page.evaluate(() => window.__server.push({ link_up: true }));
  await expect(page.getByText("sent when the thermostat answers")).toBeVisible();
  await expect(page.getByText("Thermostat not responding").first()).toBeVisible();

  await page.evaluate(() => window.__server.push({ reachable: true }));
  await expect(page.getByText("sent when the thermostat answers")).toBeHidden();
  await expect(page.getByText("Thermostat reachable")).toBeVisible();
});

test("shows a load error and tries again", async ({ page, card }) => {
  await card({});
  await page.evaluate(() => {
    window.__server.failSubscribe = { code: "unauthorized", message: "Unauthorized" };
    window.__card.setConfig({ type: "custom:fht-schedule-card", entity: "climate.other" });
    (window.__hass.states as Record<string, unknown>)["climate.other"] = {
      state: "auto",
      attributes: {},
    };
    window.__card.hass = { ...window.__hass };
  });
  await expect(
    page.getByText(
      "The week program could not be loaded: You are not allowed to change this thermostat.",
    ),
  ).toBeVisible();
  await page.evaluate(() => {
    window.__server.failSubscribe = null;
  });
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("06:00–08:30 · 17:00–22:00")).toBeVisible();
});

test("does not ask again on every update after a failed load", async ({ page, card }) => {
  await card({});
  const calls = await page.evaluate(async () => {
    window.__server.failSubscribe = { code: "unauthorized", message: "Unauthorized" };
    window.__card.setConfig({ type: "custom:fht-schedule-card", entity: "climate.other" });
    (window.__hass.states as Record<string, unknown>)["climate.other"] = {
      state: "auto",
      attributes: {},
    };
    // Home Assistant sets hass on every state change, so the updates come one by one.
    for (let i = 0; i < 10; i += 1) {
      window.__card.hass = { ...window.__hass };
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    return window.__server.calls.filter((call) => call.entity_id === "climate.other").length;
  });
  expect(calls).toBe(1);
});

test("says so when the thermostat does not exist", async ({ page, card }) => {
  await card();
  await page.evaluate(() => {
    window.__card.setConfig({ type: "custom:fht-schedule-card", entity: "climate.gone" });
  });
  await expect(page.getByText("Thermostat climate.gone was not found.")).toBeVisible();
});

test("subscribes again after the integration ends the subscription", async ({ page, card }) => {
  await page.clock.install();
  await card();
  await expect(page.getByText("06:00–08:30 · 17:00–22:00")).toBeVisible();
  await page.evaluate(() => window.__server.close());
  await page.clock.runFor(1500);
  await expect.poll(() => page.evaluate(() => window.__server.subscriptions)).toBe(2);
  await page.evaluate(() => window.__server.push({ day_temperature: 19 }));
  await expect(page.getByText("Day19.0 °C")).toBeVisible();
});

test("stops listening when the card leaves the page", async ({ page, card }) => {
  await card();
  const count = await page.evaluate(() => {
    const server = window.__server as unknown as { listeners: Set<unknown> };
    const before = server.listeners.size;
    window.__card.remove();
    return [before, server.listeners.size];
  });
  expect(count).toEqual([1, 0]);
});

test("registers itself for the card picker once", async ({ page, card }) => {
  await card();
  const result = await page.evaluate(async () => {
    const cards = (window as unknown as { customCards: Record<string, unknown>[] }).customCards;
    const before = cards.length;
    // Loading the module a second time must not define the element again.
    const again = "/fht-schedule-card.js?again";
    await import(/* @vite-ignore */ again);
    const entry = cards.find((item) => item.type === "fht-schedule-card") as {
      getEntitySuggestion(hass: unknown, id: string): unknown;
    };
    const hass = window.__hass;
    const element = customElements.get("fht-schedule-card") as unknown as {
      getStubConfig(hass: unknown, a: string[], b: string[]): unknown;
      getConfigForm(): { schema: { name: string }[]; assertConfig(config: unknown): void };
    };
    const form = element.getConfigForm();
    // The sections view adds grid_options and the visibility editor adds visibility.
    form.assertConfig({
      type: "x",
      entity: "a",
      name: "b",
      grid_options: { columns: 6 },
      visibility: [],
    });
    let rejected = "";
    try {
      form.assertConfig({ type: "x", entity: 5 });
    } catch (error) {
      rejected = (error as Error).message;
    }
    return {
      before,
      after: cards.length,
      suggestion: entry.getEntitySuggestion(hass, "climate.living_room"),
      other: entry.getEntitySuggestion(hass, "climate.other"),
      stub: element.getStubConfig(hass, ["light.a", "climate.living_room"], []),
      stubNone: element.getStubConfig(hass, [], []),
      fields: element.getConfigForm().schema.map((field) => field.name),
      rejected,
    };
  });
  expect(result).toEqual({
    before: 1,
    after: 1,
    suggestion: { config: { type: "custom:fht-schedule-card", entity: "climate.living_room" } },
    other: null,
    stub: { entity: "climate.living_room" },
    stubNone: { entity: "" },
    fields: ["entity", "name"],
    rejected: "'entity' must be a string.",
  });
});

test("names itself in the language of Home Assistant in the card picker", async ({
  page,
  card,
}) => {
  await card();
  const names = await page.evaluate(() => {
    const cards = (window as unknown as { customCards: Record<string, unknown>[] }).customCards;
    const entry = cards.find((item) => item.type === "fht-schedule-card") as {
      name: string;
      description: string;
    };
    // Without the frontend the language of the document decides.
    const fallback = entry.name;
    const frontend = document.createElement("home-assistant") as HTMLElement & {
      hass?: { language: string };
    };
    document.body.append(frontend);
    const read = (language: string) => {
      frontend.hass = { language };
      return { name: entry.name, description: entry.description };
    };
    return { fallback, de: read("de-AT"), en: read("en"), fr: read("fr") };
  });
  expect(names.fallback).toBe("FHT week program");
  expect(names.de.name).toBe("FHT Wochenprogramm");
  expect(names.de.description).toContain("Wochenheizprogramm");
  expect(names.en.name).toBe("FHT week program");
  expect(names.fr.name).toBe("FHT week program");
});

test("reports the size for both dashboard layouts and rejects a wrong config", async ({
  page,
  card,
}) => {
  await card();
  const result = await page.evaluate(() => {
    const element = window.__card as unknown as {
      getCardSize(): number;
      getGridOptions(): unknown;
      setConfig(config: unknown): void;
    };
    let message = "";
    try {
      element.setConfig({ type: "custom:fht-schedule-card" });
    } catch (error) {
      message = (error as Error).message;
    }
    return { size: element.getCardSize(), grid: element.getGridOptions(), message };
  });
  expect(result.size).toBeGreaterThan(0);
  expect(result.grid).toEqual({ columns: 12, min_columns: 6, rows: "auto" });
  expect(result.message).toContain("climate entity");
});
