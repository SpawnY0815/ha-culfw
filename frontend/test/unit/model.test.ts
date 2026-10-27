import { describe, expect, it } from "vitest";
import cases from "../fixtures/day_validation.json";
import {
  addPeriodAt,
  clamp,
  copyTargets,
  dirtyDays,
  formatTime,
  freeGaps,
  hasTouching,
  heatingMinutes,
  mergeTouching,
  movePeriod,
  parseTime,
  periodsEqual,
  removePeriod,
  resizeEnd,
  resizeStart,
  shownPeriods,
  snap,
  sortPeriods,
  suggestPeriod,
  toWire,
  validateDay,
  validateRanges,
} from "../../src/model";
import type { DayState, Limits, Period, Weekday } from "../../src/types";
import { WEEKDAYS } from "../../src/types";

const limits: Limits = { stepMinutes: 10, maxPeriods: 2, dayEnd: 1440 };

function p(start: string, end: string): Period {
  return { start: parseTime(start) as number, end: parseTime(end) as number };
}

function day(partial: Partial<DayState> = {}): DayState {
  return {
    status: "saved",
    periods: [],
    requested: null,
    pendingSince: null,
    ...partial,
  };
}

function week(overrides: Partial<Record<Weekday, DayState>> = {}) {
  return Object.fromEntries(
    WEEKDAYS.map((weekday) => [weekday, overrides[weekday] ?? day()]),
  ) as Record<Weekday, DayState>;
}

describe("time", () => {
  it.each([
    ["06:30", 390],
    ["6:30", 390],
    ["00:00", 0],
    ["24:00", 1440],
    ["06:30:00", 390],
    [" 06:30 ", 390],
  ])("parses %s", (text, minutes) => {
    expect(parseTime(text)).toBe(minutes);
  });

  it.each(["", "7", "7:3", "24:10", "25:00", "06:60", "06:00:30", "soon", "-1:00"])(
    "rejects %j",
    (text) => {
      expect(parseTime(text)).toBeNull();
    },
  );

  it("formats minutes with 24:00 as the end of the day", () => {
    expect(formatTime(0)).toBe("00:00");
    expect(formatTime(395)).toBe("06:35");
    expect(formatTime(1440)).toBe("24:00");
  });

  it("round trips every step of the day", () => {
    for (let minute = 0; minute <= 1440; minute += 10) {
      expect(parseTime(formatTime(minute))).toBe(minute);
    }
  });

  it("snaps to the step and stays in the day", () => {
    expect(snap(394, limits)).toBe(390);
    expect(snap(395, limits)).toBe(400);
    expect(snap(-30, limits)).toBe(0);
    expect(snap(5000, limits)).toBe(1440);
    expect(snap(7, { ...limits, stepMinutes: 15 })).toBe(0);
    expect(clamp(5, 1, 3)).toBe(3);
  });
});

describe("validation mirrors the backend", () => {
  it.each(cases.map((item) => [item.name, item] as const))("%s", (_name, item) => {
    expect(validateRanges(item.ranges, limits)?.key ?? null).toBe(item.error);
  });

  it("checks periods in minutes", () => {
    expect(validateDay([p("06:00", "08:00")], limits)).toBeNull();
    expect(validateDay([{ start: -10, end: 60 }], limits)?.key).toBe("schedule_time_invalid");
    expect(validateDay([{ start: 0, end: 1450 }], limits)?.key).toBe("schedule_time_invalid");
    expect(validateDay([{ start: 0.5, end: 60 }], limits)?.key).toBe("schedule_time_invalid");
    expect(validateDay([{ start: 5, end: 60 }], limits)?.key).toBe("schedule_time_step");
  });

  it("names the values in the error", () => {
    expect(validateDay([p("08:00", "07:00")], limits)?.params).toEqual({
      start: "08:00",
      end: "07:00",
    });
    expect(validateDay([p("06:00", "09:00"), p("08:00", "10:00")], limits)?.params).toEqual({
      first_start: "06:00",
      first_end: "09:00",
      second_start: "08:00",
      second_end: "10:00",
    });
    expect(validateRanges([{ start: "06:05", end: "07:00" }], limits)?.params).toEqual({
      value: "06:05",
      step: "10",
    });
  });

  it("uses the limits it is given", () => {
    const one = { ...limits, maxPeriods: 1 };
    expect(validateDay([p("01:00", "02:00"), p("03:00", "04:00")], one)?.params).toEqual({
      count: "2",
      max_ranges: "1",
    });
    expect(validateDay([{ start: 0, end: 15 }], { ...limits, stepMinutes: 15 })).toBeNull();
  });
});

describe("period helpers", () => {
  it("sorts without changing the input", () => {
    const input = [p("17:00", "18:00"), p("06:00", "07:00")];
    expect(sortPeriods(input)[0]).toEqual(p("06:00", "07:00"));
    expect(input[0]).toEqual(p("17:00", "18:00"));
    expect(sortPeriods([p("06:00", "08:00"), p("06:00", "07:00")])[0]?.end).toBe(420);
  });

  it("compares periods without regard to their order", () => {
    expect(
      periodsEqual(
        [p("06:00", "07:00"), p("08:00", "09:00")],
        [p("08:00", "09:00"), p("06:00", "07:00")],
      ),
    ).toBe(true);
    expect(periodsEqual([p("06:00", "07:00")], [p("06:00", "07:10")])).toBe(false);
    expect(periodsEqual([p("06:00", "07:00")], [])).toBe(false);
  });

  it("finds and merges periods that touch", () => {
    const touching = [p("08:00", "10:00"), p("06:00", "08:00")];
    expect(hasTouching(touching)).toBe(true);
    expect(hasTouching([p("06:00", "07:00"), p("08:00", "09:00")])).toBe(false);
    expect(mergeTouching(touching)).toEqual([p("06:00", "10:00")]);
    expect(mergeTouching([p("06:00", "12:00"), p("07:00", "08:00")])).toEqual([
      p("06:00", "12:00"),
    ]);
    expect(mergeTouching([p("06:00", "07:00"), p("08:00", "09:00")])).toHaveLength(2);
  });

  it("lists the free stretches", () => {
    expect(freeGaps([], limits)).toEqual([{ start: 0, end: 1440 }]);
    expect(freeGaps([p("06:00", "08:00"), p("08:00", "10:00")], limits)).toEqual([
      { start: 0, end: 360 },
      { start: 600, end: 1440 },
    ]);
    expect(freeGaps([p("00:00", "24:00")], limits)).toEqual([]);
    expect(freeGaps([p("00:05", "23:55")], { ...limits, stepMinutes: 10 })).toEqual([]);
  });

  it("totals the heating time", () => {
    expect(heatingMinutes([p("06:00", "08:30"), p("17:00", "22:00")])).toBe(450);
    expect(heatingMinutes([])).toBe(0);
  });
});

describe("adding periods", () => {
  it("adds one hour where the user tapped", () => {
    expect(addPeriodAt([], 394, limits)).toEqual([p("06:30", "07:30")]);
  });

  it("stops at the next period and at the end of the day", () => {
    expect(addPeriodAt([p("07:00", "08:00")], 390, limits)).toEqual([
      p("06:30", "07:00"),
      p("07:00", "08:00"),
    ]);
    expect(addPeriodAt([], 1430, limits)).toEqual([p("23:50", "24:00")]);
  });

  it("refuses a tap on a period, at the limit and in a gap that is too small", () => {
    expect(addPeriodAt([p("06:00", "08:00")], 420, limits)).toBeNull();
    expect(addPeriodAt([p("06:00", "08:00"), p("17:00", "18:00")], 600, limits)).toBeNull();
    expect(addPeriodAt([p("06:00", "08:00")], 480, limits)).toEqual([
      p("06:00", "08:00"),
      p("08:00", "09:00"),
    ]);
    expect(addPeriodAt([p("00:00", "24:00")], 600, limits)).toBeNull();
  });

  it("suggests the morning on an empty day and the largest gap otherwise", () => {
    expect(suggestPeriod([], limits)).toEqual([p("06:00", "07:00")]);
    expect(suggestPeriod([p("06:00", "08:00")], limits)).toEqual([
      p("06:00", "08:00"),
      p("08:00", "09:00"),
    ]);
    expect(suggestPeriod([p("00:00", "12:00")], limits)).toEqual([
      p("00:00", "12:00"),
      p("12:00", "13:00"),
    ]);
    expect(suggestPeriod([p("00:00", "23:50")], limits)).toEqual([
      p("00:00", "23:50"),
      p("23:50", "24:00"),
    ]);
    expect(suggestPeriod([p("00:00", "03:00")], limits)).toEqual([
      p("00:00", "03:00"),
      p("03:00", "04:00"),
    ]);
  });

  it("suggests nothing when the day is full", () => {
    expect(suggestPeriod([p("01:00", "02:00"), p("03:00", "04:00")], limits)).toBeNull();
    expect(suggestPeriod([p("00:00", "24:00")], { ...limits, maxPeriods: 3 })).toBeNull();
  });

  it("starts at six o'clock only if the stretch has room for the hour", () => {
    expect(suggestPeriod([p("06:30", "24:00")], limits)).toEqual([
      p("00:00", "01:00"),
      p("06:30", "24:00"),
    ]);
  });
});

describe("dragging", () => {
  const two = [p("06:00", "08:00"), p("17:00", "18:00")];

  it("moves a period and keeps its length", () => {
    expect(movePeriod(two, 0, 7 * 60 + 4, limits)[0]).toEqual(p("07:00", "09:00"));
  });

  it("stops a move at the neighbors and at the day", () => {
    expect(movePeriod(two, 0, 20 * 60, limits)[0]).toEqual(p("15:00", "17:00"));
    expect(movePeriod(two, 1, 0, limits)[1]).toEqual(p("08:00", "09:00"));
    expect(movePeriod(two, 0, -100, limits)[0]).toEqual(p("00:00", "02:00"));
    expect(movePeriod([p("22:00", "23:00")], 0, 5000, limits)[0]).toEqual(p("23:00", "24:00"));
  });

  it("resizes the start and keeps one step", () => {
    expect(resizeStart(two, 0, 5 * 60, limits)[0]).toEqual(p("05:00", "08:00"));
    expect(resizeStart(two, 0, 8 * 60, limits)[0]).toEqual(p("07:50", "08:00"));
    expect(resizeStart(two, 1, 0, limits)[1]).toEqual(p("08:00", "18:00"));
  });

  it("resizes the end and keeps one step", () => {
    expect(resizeEnd(two, 0, 9 * 60, limits)[0]).toEqual(p("06:00", "09:00"));
    expect(resizeEnd(two, 0, 0, limits)[0]).toEqual(p("06:00", "06:10"));
    expect(resizeEnd(two, 0, 20 * 60, limits)[0]).toEqual(p("06:00", "17:00"));
    expect(resizeEnd(two, 1, 99999, limits)[1]).toEqual(p("17:00", "24:00"));
  });

  it("ignores an index that does not exist and never changes its input", () => {
    expect(movePeriod(two, 5, 0, limits)).toEqual(two);
    expect(resizeStart(two, 5, 0, limits)).toEqual(two);
    expect(resizeEnd(two, 5, 0, limits)).toEqual(two);
    expect(two[0]).toEqual(p("06:00", "08:00"));
  });

  it("removes a period", () => {
    expect(removePeriod(two, 0)).toEqual([p("17:00", "18:00")]);
    expect(removePeriod(two, 9)).toEqual(two);
  });
});

describe("days", () => {
  it("shows what is on its way before what was reported", () => {
    expect(shownPeriods(day({ periods: [p("06:00", "07:00")] }))).toEqual([p("06:00", "07:00")]);
    expect(
      shownPeriods(day({ status: "queued", periods: [], requested: [p("06:00", "07:00")] })),
    ).toEqual([p("06:00", "07:00")]);
    expect(shownPeriods(day({ status: "unknown", periods: null }))).toBeNull();
  });

  it("finds the days that differ from the server", () => {
    const days = week({
      tuesday: day({ periods: [p("06:00", "07:00")] }),
      wednesday: day({ status: "unknown", periods: null }),
      thursday: day({ status: "queued", periods: [], requested: [p("06:00", "07:00")] }),
    });
    const draft = {
      monday: [],
      tuesday: [p("06:00", "07:00")],
      wednesday: [],
      thursday: [p("06:00", "07:10")],
      friday: [p("06:00", "07:00")],
    };
    expect(dirtyDays(draft, days)).toEqual(["wednesday", "thursday", "friday"]);
    expect(dirtyDays({}, days)).toEqual([]);
  });

  it("selects the days of the copy presets", () => {
    expect(copyTargets("weekdays", "monday")).toEqual([
      "tuesday",
      "wednesday",
      "thursday",
      "friday",
    ]);
    expect(copyTargets("weekend", "saturday")).toEqual(["sunday"]);
    expect(copyTargets("weekend", "monday")).toEqual(["saturday", "sunday"]);
    expect(copyTargets("all", "wednesday")).toHaveLength(6);
    expect(copyTargets("all", "wednesday")).not.toContain("wednesday");
  });

  it("builds the data of the command set", () => {
    expect(
      toWire({ monday: [p("17:00", "22:00"), p("06:00", "08:30")], tuesday: [] }, [
        "monday",
        "tuesday",
      ]),
    ).toEqual({
      monday: [
        { start: "06:00", end: "08:30" },
        { start: "17:00", end: "22:00" },
      ],
      tuesday: [],
    });
    expect(toWire({}, ["friday"])).toEqual({ friday: [] });
  });
});
