import { describe, expect, it } from "vitest";
import {
  dayName,
  dayShort,
  describeError,
  pickerText,
  pickLanguage,
  stringKeys,
  t,
} from "../../src/i18n";

describe("language", () => {
  it("picks German for every German locale and English otherwise", () => {
    expect(pickLanguage("de")).toBe("de");
    expect(pickLanguage("de-AT")).toBe("de");
    expect(pickLanguage("DE")).toBe("de");
    expect(pickLanguage("en")).toBe("en");
    expect(pickLanguage("fr")).toBe("en");
    expect(pickLanguage(undefined)).toBe("en");
  });

  it("has the same texts in both languages", () => {
    expect(stringKeys("de")).toEqual(stringKeys("en"));
  });

  it("keeps the placeholders of a text in its translation", () => {
    const placeholders = (text: string) => [...text.matchAll(/\{(\w+)/g)].map((m) => m[1]).sort();
    for (const key of stringKeys("en")) {
      const name = key as Parameters<typeof t>[1];
      const params = Object.fromEntries(
        placeholders(t("en", name)).map((placeholder) => [placeholder as string, "x"]),
      );
      // Filling every placeholder of the English text must fill the German one too.
      expect(t("de", name, params), key).not.toMatch(/\{\w+\}/);
      expect(t("en", name, params), key).not.toMatch(/\{\w+\}/);
    }
  });
});

describe("card picker", () => {
  it("names the card in the language and finds it by the name of the other one", () => {
    expect(pickerText("en").name).toBe("FHT week program");
    expect(pickerText("de").name).toBe("FHT Wochenprogramm");
    // The picker searches the description too, so each one holds the other name.
    expect(pickerText("en").description).toContain("FHT Wochenprogramm");
    expect(pickerText("de").description).toContain("FHT week program");
  });
});

describe("texts", () => {
  it("fills placeholders and leaves unknown ones", () => {
    expect(t("en", "aria.start", { day: "Monday", n: 1 })).toBe("Monday, period 1, start");
    expect(t("en", "aria.start", { day: "Monday" })).toBe("Monday, period {n}, start");
  });

  it("chooses the plural form", () => {
    expect(t("en", "footer.changed", { count: 1 })).toBe("1 day changed");
    expect(t("en", "footer.changed", { count: 3 })).toBe("3 days changed");
    expect(t("de", "footer.changed", { count: 1 })).toBe("1 Tag geändert");
    expect(t("de", "footer.changed", { count: 0 })).toBe("0 Tage geändert");
  });

  it("names the weekdays", () => {
    expect(dayName("en", "monday")).toBe("Monday");
    expect(dayName("de", "sunday")).toBe("Sonntag");
    expect(dayShort("de", "tuesday")).toBe("Di");
    expect(dayShort("en", "tuesday")).toBe("Tue");
  });
});

describe("errors", () => {
  it("translates an error of the integration with its placeholders", () => {
    const error = {
      code: "service_validation_error",
      message: "Monday: 06:05 is not a multiple of 10 minutes.",
      translation_key: "schedule_time_step",
      translation_placeholders: { day: "Monday", value: "06:05", step: "10" },
    };
    expect(describeError("en", error)).toContain("Monday: 06:05 is not a multiple of 10");
    expect(describeError("de", error)).toBe(
      "Montag: 06:05 ist kein Vielfaches von 10 Minuten. Das Thermostat schaltet in Schritten von 10 Minuten.",
    );
  });

  it("lets the caller name the day", () => {
    expect(
      describeError(
        "de",
        {
          translation_key: "schedule_range_backwards",
          translation_placeholders: { start: "08:00", end: "07:00" },
        },
        { day: "Freitag" },
      ),
    ).toContain("Freitag: Der Bereich von 08:00 bis 07:00");
  });

  it("keeps a day that is not a weekday name", () => {
    expect(
      describeError("de", {
        translation_key: "schedule_time_invalid",
        translation_placeholders: { day: "Someday", value: "x" },
      }),
    ).toContain("Someday: x ist keine Uhrzeit");
  });

  it("falls back to the message and to a plain text", () => {
    expect(describeError("en", { message: "Boom", translation_key: "other_key" })).toBe("Boom");
    expect(describeError("en", { message: "Boom" })).toBe("Boom");
    expect(describeError("en", undefined)).toBe("Something went wrong.");
    expect(describeError("de", {})).toBe("Etwas ist schiefgelaufen.");
  });

  it("explains the codes of the websocket API in words", () => {
    expect(describeError("en", { code: "unauthorized", message: "Unauthorized" })).toBe(
      "You are not allowed to change this thermostat.",
    );
    expect(describeError("de", { code: "unknown_command", message: "Unknown command." })).toContain(
      "Aktualisiere die Integration",
    );
  });
});
