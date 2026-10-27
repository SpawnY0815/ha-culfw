import { describe, expect, it, vi } from "vitest";
import {
  asApiError,
  isClosed,
  isWireState,
  parseState,
  refreshSchedule,
  setSchedule,
  subscribeSchedule,
} from "../../src/ws";
import type { WireState } from "../../src/ws";
import type { Hass } from "../../src/types";
import { WEEKDAYS } from "../../src/types";
import wireStates from "../fixtures/wire_states.json";

function wire(): WireState {
  const days = Object.fromEntries(
    WEEKDAYS.map((weekday) => [
      weekday,
      { status: "unknown", periods: null, requested: null, pending_since: null },
    ]),
  ) as unknown as WireState["days"];
  days.monday = {
    status: "queued",
    periods: [{ start: "06:00", end: "08:30" }],
    requested: [{ start: "06:00", end: "24:00" }],
    pending_since: "2026-10-20T10:00:00+00:00",
  };
  return {
    limits: { step_minutes: 10, max_periods: 2, day_end: "24:00" },
    days,
    week_program_read_at: null,
    day_temperature: 21,
    night_temperature: null,
    link_up: true,
    reachable: false,
  };
}

function fakeHass(): {
  hass: Hass;
  callWS: ReturnType<typeof vi.fn>;
  subscribe: ReturnType<typeof vi.fn>;
} {
  const callWS = vi.fn().mockResolvedValue({});
  const subscribe = vi.fn().mockResolvedValue(() => undefined);
  const hass = {
    language: "en",
    states: {},
    callWS,
    connection: { subscribeMessage: subscribe },
  } as unknown as Hass;
  return { hass, callWS, subscribe };
}

describe("parseState", () => {
  it("converts the times to minutes and keeps unknown days unknown", () => {
    const state = parseState(wire());
    expect(state.limits).toEqual({ stepMinutes: 10, maxPeriods: 2, dayEnd: 1440 });
    expect(state.days.monday.periods).toEqual([{ start: 360, end: 510 }]);
    expect(state.days.monday.requested).toEqual([{ start: 360, end: 1440 }]);
    expect(state.days.monday.pendingSince).toBe("2026-10-20T10:00:00+00:00");
    expect(state.days.tuesday.periods).toBeNull();
    expect(state.dayTemperature).toBe(21);
    expect(state.nightTemperature).toBeNull();
    expect(state.reachable).toBe(false);
    expect(state.linkUp).toBe(true);
  });

  it("falls back to the full day and to zero for text it cannot read", () => {
    const data = wire();
    data.limits.day_end = "soon";
    data.days.monday.periods = [{ start: "x", end: "y" }];
    const state = parseState(data);
    expect(state.limits.dayEnd).toBe(1440);
    expect(state.days.monday.periods).toEqual([{ start: 0, end: 0 }]);
  });
});

describe("isWireState", () => {
  // Return the data of the server with one value replaced, or removed for undefined.
  function changed(path: string[], value: unknown): unknown {
    const data = structuredClone(wire()) as unknown as Record<string, unknown>;
    let parent = data;
    for (const key of path.slice(0, -1)) {
      parent = parent[key] as Record<string, unknown>;
    }
    const last = path[path.length - 1] as string;
    if (value === undefined) {
      delete parent[last];
    } else {
      parent[last] = value;
    }
    return data;
  }

  it("accepts the data of the server", () => {
    expect(isWireState(wire())).toBe(true);
  });

  // The file is written by the tests of the integration from what it really sends, so a
  // change of the payload that the card cannot take fails here.
  it.each(Object.entries(wireStates))("accepts the payload of %s", (_name, payload) => {
    expect(isWireState(payload)).toBe(true);
    expect(parseState(payload as unknown as WireState).linkUp).toBe(true);
  });

  it.each([
    ["no object", null, [] as string[]],
    ["no limits", undefined, ["limits"]],
    ["a step of zero", 0, ["limits", "step_minutes"]],
    ["a step that is text", "10", ["limits", "step_minutes"]],
    ["a fractional step", 7.5, ["limits", "step_minutes"]],
    ["a step of a week", 10080, ["limits", "step_minutes"]],
    ["a million periods", 1e6, ["limits", "max_periods"]],
    ["a day end that is a number", 1440, ["limits", "day_end"]],
    ["a missing day", undefined, ["days", "sunday"]],
    ["a day that is null", null, ["days", "monday"]],
    ["a status that is markup", "<b>", ["days", "monday", "status"]],
    ["a status that is a prototype key", "constructor", ["days", "monday", "status"]],
    ["periods that are no list", "06:00", ["days", "monday", "periods"]],
    ["a period without an end", [{ start: "06:00" }], ["days", "monday", "periods"]],
    ["a period that is a number", [6], ["days", "monday", "requested"]],
    ["a pending time that is a number", 1, ["days", "monday", "pending_since"]],
    ["a temperature that is text", "warm", ["day_temperature"]],
    ["a temperature that is not finite", Infinity, ["night_temperature"]],
    ["a link flag that is text", "yes", ["link_up"]],
    ["a reach flag that is missing", undefined, ["reachable"]],
  ])("refuses %s", (_name, value, path) => {
    expect(isWireState(path.length === 0 ? value : changed(path, value))).toBe(false);
  });
});

describe("commands", () => {
  it("subscribes and tells states and the end of the subscription apart", async () => {
    const { hass, subscribe } = fakeHass();
    const onState = vi.fn();
    const onClosed = vi.fn();
    const onInvalid = vi.fn();
    await subscribeSchedule(hass, "climate.a", onState, onClosed, onInvalid);
    expect(subscribe.mock.calls[0]?.[1]).toEqual({
      type: "culfw/schedule/subscribe",
      entity_id: "climate.a",
    });
    const callback = subscribe.mock.calls[0]?.[0] as (event: unknown) => void;
    callback(wire());
    callback({ closed: true });
    expect(onState).toHaveBeenCalledOnce();
    expect(onClosed).toHaveBeenCalledOnce();
    expect(onInvalid).not.toHaveBeenCalled();
    expect(isClosed({ closed: true })).toBe(true);
    expect(isClosed(wire())).toBe(false);
  });

  it("hands an event of another form to onInvalid and nothing else", async () => {
    const { hass, subscribe } = fakeHass();
    const onState = vi.fn();
    const onClosed = vi.fn();
    const onInvalid = vi.fn();
    await subscribeSchedule(hass, "climate.a", onState, onClosed, onInvalid);
    const callback = subscribe.mock.calls[0]?.[0] as (event: unknown) => void;
    for (const event of [null, undefined, 7, "closed", [], {}, { closed: "yes" }]) {
      callback(event);
    }
    expect(onInvalid).toHaveBeenCalledTimes(7);
    expect(onState).not.toHaveBeenCalled();
    expect(onClosed).not.toHaveBeenCalled();
  });

  it("sends the days and the optional days of a read", async () => {
    const { hass, callWS } = fakeHass();
    await setSchedule(hass, "climate.a", { monday: [] });
    await refreshSchedule(hass, "climate.a");
    await refreshSchedule(hass, "climate.a", ["friday"]);
    expect(callWS.mock.calls.map((call): unknown => call[0])).toEqual([
      { type: "culfw/schedule/set", entity_id: "climate.a", days: { monday: [] } },
      { type: "culfw/schedule/refresh", entity_id: "climate.a" },
      { type: "culfw/schedule/refresh", entity_id: "climate.a", days: ["friday"] },
    ]);
  });
});

describe("asApiError", () => {
  it("keeps the known fields of an error of the websocket API", () => {
    expect(
      asApiError({
        code: "home_assistant_error",
        message: "No",
        translation_key: "send_blocked",
        translation_placeholders: { a: "b" },
        other: 1,
      }),
    ).toEqual({
      code: "home_assistant_error",
      message: "No",
      translation_key: "send_blocked",
      translation_placeholders: { a: "b" },
    });
  });

  it("accepts a plain text and anything else", () => {
    expect(asApiError("lost")).toEqual({ message: "lost" });
    expect(asApiError(42)).toEqual({ message: undefined });
    expect(asApiError(new Error("x"))).toEqual({ message: "x" });
  });
});
