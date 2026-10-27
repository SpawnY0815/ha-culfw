import type { DayState, Draft, Limits, Period, Weekday } from "./types";
import { WEEKDAYS } from "./types";

/** Translation keys shared with the exceptions of the integration. */
export type ValidationKey =
  | "schedule_time_invalid"
  | "schedule_time_step"
  | "schedule_too_many_ranges"
  | "schedule_range_backwards"
  | "schedule_ranges_overlap";

export interface ValidationError {
  key: ValidationKey;
  params: Record<string, string>;
}

export interface TextRange {
  start: string;
  end: string;
}

export type CopyPreset = "weekdays" | "weekend" | "all";

const MINUTES_PER_HOUR = 60;
const DEFAULT_PERIOD_MINUTES = 60;
const MORNING_START = 6 * MINUTES_PER_HOUR;
const TIME = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/;

/** Return minutes after midnight, or null if the text is not a time of day. */
export function parseTime(text: string, dayEnd = 1440): number | null {
  const match = TIME.exec(text.trim());
  if (match === null) {
    return null;
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  const seconds = Number(match[3] ?? 0);
  const total = hours * MINUTES_PER_HOUR + minutes;
  if (minutes >= MINUTES_PER_HOUR || seconds !== 0 || total > dayEnd) {
    return null;
  }
  return total;
}

/** Return minutes after midnight as HH:MM, where 24:00 is the end of the day. */
export function formatTime(minutes: number): string {
  const hours = Math.floor(minutes / MINUTES_PER_HOUR);
  const rest = minutes % MINUTES_PER_HOUR;
  return `${String(hours).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

export function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

/** Round to the nearest step and keep the result inside the day. */
export function snap(minutes: number, limits: Limits): number {
  const step = limits.stepMinutes;
  return clamp(Math.round(minutes / step) * step, 0, limits.dayEnd);
}

export function sortPeriods(periods: readonly Period[]): Period[] {
  return periods
    .map((period) => ({ ...period }))
    .sort((a, b) => a.start - b.start || a.end - b.end);
}

export function periodsEqual(a: readonly Period[], b: readonly Period[]): boolean {
  if (a.length !== b.length) {
    return false;
  }
  const left = sortPeriods(a);
  const right = sortPeriods(b);
  return left.every(
    (period, index) => period.start === right[index]?.start && period.end === right[index]?.end,
  );
}

function error(key: ValidationKey, params: Record<string, string> = {}): ValidationError {
  return { key, params };
}

function tooMany(count: number, limits: Limits): ValidationError {
  return error("schedule_too_many_ranges", {
    count: String(count),
    max_ranges: String(limits.maxPeriods),
  });
}

function checkTimes(
  times: readonly [number | null, string][],
  limits: Limits,
): ValidationError | null {
  for (const [minutes, text] of times) {
    if (minutes === null || !Number.isInteger(minutes)) {
      return error("schedule_time_invalid", { value: text });
    }
    if (minutes < 0 || minutes > limits.dayEnd) {
      return error("schedule_time_invalid", { value: text });
    }
    if (minutes % limits.stepMinutes !== 0) {
      return error("schedule_time_step", {
        value: text,
        step: String(limits.stepMinutes),
      });
    }
  }
  return null;
}

/**
 * Check the periods of one day with the rules of the integration.
 *
 * The rules are the ones of `parse_day` in schedule.py: at most `maxPeriods`
 * ranges, times in steps, each range ends after it starts, and the ranges do
 * not overlap but may touch. The first problem is returned.
 */
export function validateDay(periods: readonly Period[], limits: Limits): ValidationError | null {
  if (periods.length > limits.maxPeriods) {
    return tooMany(periods.length, limits);
  }
  for (const period of periods) {
    const problem = checkTimes(
      [
        [period.start, formatTime(period.start)],
        [period.end, formatTime(period.end)],
      ],
      limits,
    );
    if (problem !== null) {
      return problem;
    }
  }
  for (const period of periods) {
    if (period.start >= period.end) {
      return error("schedule_range_backwards", {
        start: formatTime(period.start),
        end: formatTime(period.end),
      });
    }
  }
  const sorted = sortPeriods(periods);
  for (let index = 1; index < sorted.length; index += 1) {
    const first = sorted[index - 1] as Period;
    const second = sorted[index] as Period;
    if (second.start < first.end) {
      return error("schedule_ranges_overlap", {
        first_start: formatTime(first.start),
        first_end: formatTime(first.end),
        second_start: formatTime(second.start),
        second_end: formatTime(second.end),
      });
    }
  }
  return null;
}

/** Parse and check time ranges that were typed as text. */
export function validateRanges(
  ranges: readonly TextRange[],
  limits: Limits,
): ValidationError | null {
  if (ranges.length > limits.maxPeriods) {
    return tooMany(ranges.length, limits);
  }
  const periods: Period[] = [];
  for (const range of ranges) {
    const start = parseTime(range.start, limits.dayEnd);
    const end = parseTime(range.end, limits.dayEnd);
    const problem = checkTimes(
      [
        [start, range.start],
        [end, range.end],
      ],
      limits,
    );
    if (problem !== null) {
      return problem;
    }
    periods.push({ start: start as number, end: end as number });
  }
  return validateDay(periods, limits);
}

/** Return true if two periods of the day end and start at the same time. */
export function hasTouching(periods: readonly Period[]): boolean {
  const sorted = sortPeriods(periods);
  return sorted.some((period, index) => index > 0 && sorted[index - 1]?.end === period.start);
}

/** Join periods that touch, so that the thermostat gets one switch pair. */
export function mergeTouching(periods: readonly Period[]): Period[] {
  const merged: Period[] = [];
  for (const period of sortPeriods(periods)) {
    const last = merged[merged.length - 1];
    if (last !== undefined && last.end >= period.start) {
      last.end = Math.max(last.end, period.end);
    } else {
      merged.push(period);
    }
  }
  return merged;
}

/** Return the free stretches of the day that are at least one step long. */
export function freeGaps(periods: readonly Period[], limits: Limits): Period[] {
  const gaps: Period[] = [];
  let cursor = 0;
  for (const period of sortPeriods(periods)) {
    if (period.start - cursor >= limits.stepMinutes) {
      gaps.push({ start: cursor, end: period.start });
    }
    cursor = Math.max(cursor, period.end);
  }
  if (limits.dayEnd - cursor >= limits.stepMinutes) {
    gaps.push({ start: cursor, end: limits.dayEnd });
  }
  return gaps;
}

function insert(periods: readonly Period[], period: Period): Period[] {
  return sortPeriods([...periods, period]);
}

/**
 * Add a one hour period where the user tapped, or return null if it is not possible.
 *
 * It is not possible if the day has the most periods already or the tap is on
 * a period. The new period stops at the next period and at the end of the day.
 */
export function addPeriodAt(
  periods: readonly Period[],
  minute: number,
  limits: Limits,
): Period[] | null {
  if (periods.length >= limits.maxPeriods) {
    return null;
  }
  const tapped = snap(minute, limits);
  const gap = freeGaps(periods, limits).find(
    (candidate) => candidate.start <= tapped && tapped < candidate.end,
  );
  if (gap === undefined) {
    return null;
  }
  const start = Math.min(tapped, gap.end - limits.stepMinutes);
  const end = Math.min(start + DEFAULT_PERIOD_MINUTES, gap.end);
  return insert(periods, { start, end });
}

/** Add a period in the largest free stretch, for the button without a tap. */
export function suggestPeriod(periods: readonly Period[], limits: Limits): Period[] | null {
  if (periods.length >= limits.maxPeriods) {
    return null;
  }
  let largest: Period | undefined;
  for (const gap of freeGaps(periods, limits)) {
    if (largest === undefined || gap.end - gap.start > largest.end - largest.start) {
      largest = gap;
    }
  }
  if (largest === undefined) {
    return null;
  }
  const morning = largest.start === 0 && largest.end >= MORNING_START + DEFAULT_PERIOD_MINUTES;
  const start = morning ? MORNING_START : largest.start;
  const end = Math.min(start + DEFAULT_PERIOD_MINUTES, largest.end);
  return insert(periods, { start, end });
}

function neighbors(
  periods: readonly Period[],
  index: number,
  limits: Limits,
): { low: number; high: number } {
  return {
    low: periods[index - 1]?.end ?? 0,
    high: periods[index + 1]?.start ?? limits.dayEnd,
  };
}

/** Move a period, keeping its length. It stops at its neighbors. */
export function movePeriod(
  periods: readonly Period[],
  index: number,
  start: number,
  limits: Limits,
): Period[] {
  const current = periods[index];
  if (current === undefined) {
    return periods.map((period) => ({ ...period }));
  }
  const length = current.end - current.start;
  const { low, high } = neighbors(periods, index, limits);
  const moved = clamp(snap(start, limits), low, high - length);
  return periods.map((period, position) =>
    position === index ? { start: moved, end: moved + length } : { ...period },
  );
}

/** Move the start of a period. It stops at its neighbor and keeps one step. */
export function resizeStart(
  periods: readonly Period[],
  index: number,
  start: number,
  limits: Limits,
): Period[] {
  const current = periods[index];
  if (current === undefined) {
    return periods.map((period) => ({ ...period }));
  }
  const { low } = neighbors(periods, index, limits);
  const moved = clamp(snap(start, limits), low, current.end - limits.stepMinutes);
  return periods.map((period, position) =>
    position === index ? { start: moved, end: period.end } : { ...period },
  );
}

/** Move the end of a period. It stops at its neighbor and keeps one step. */
export function resizeEnd(
  periods: readonly Period[],
  index: number,
  end: number,
  limits: Limits,
): Period[] {
  const current = periods[index];
  if (current === undefined) {
    return periods.map((period) => ({ ...period }));
  }
  const { high } = neighbors(periods, index, limits);
  const moved = clamp(snap(end, limits), current.start + limits.stepMinutes, high);
  return periods.map((period, position) =>
    position === index ? { start: period.start, end: moved } : { ...period },
  );
}

export function removePeriod(periods: readonly Period[], index: number): Period[] {
  return periods.filter((_, position) => position !== index).map((period) => ({ ...period }));
}

/** Return the periods that the thermostat holds or is going to hold. */
export function shownPeriods(day: DayState): Period[] | null {
  return day.requested ?? day.periods;
}

/** Return the days whose edited periods differ from what is shown by the server. */
export function dirtyDays(draft: Draft, days: Record<Weekday, DayState>): Weekday[] {
  return WEEKDAYS.filter((weekday) => {
    const edited = draft[weekday];
    if (edited === undefined) {
      return false;
    }
    const shown = shownPeriods(days[weekday]);
    return shown === null || !periodsEqual(edited, shown);
  });
}

/** Return the days that a copy preset selects, without the day that is copied. */
export function copyTargets(preset: CopyPreset, source: Weekday): Weekday[] {
  const group: readonly Weekday[] =
    preset === "weekdays"
      ? WEEKDAYS.slice(0, 5)
      : preset === "weekend"
        ? WEEKDAYS.slice(5)
        : WEEKDAYS;
  return group.filter((weekday) => weekday !== source);
}

/** Return the days of a draft in the shape of the websocket command `set`. */
export function toWire(draft: Draft, weekdays: readonly Weekday[]): Record<string, TextRange[]> {
  const days: Record<string, TextRange[]> = {};
  for (const weekday of weekdays) {
    days[weekday] = sortPeriods(draft[weekday] ?? []).map((period) => ({
      start: formatTime(period.start),
      end: formatTime(period.end),
    }));
  }
  return days;
}

/** Return the total heating time of a day in minutes. */
export function heatingMinutes(periods: readonly Period[]): number {
  return periods.reduce((sum, period) => sum + period.end - period.start, 0);
}
