import type { DayState, DayStatus, Hass, Limits, Period, ScheduleState, Weekday } from "./types";
import { WEEKDAYS } from "./types";
import { parseTime } from "./model";
import type { ApiError } from "./i18n";
import type { TextRange } from "./model";

interface WireRange {
  start: string;
  end: string;
}

interface WireDay {
  status: DayStatus;
  periods: WireRange[] | null;
  requested: WireRange[] | null;
  pending_since: string | null;
}

export interface WireState {
  limits: { step_minutes: number; max_periods: number; day_end: string };
  days: Record<Weekday, WireDay>;
  week_program_read_at: string | null;
  day_temperature: number | null;
  night_temperature: number | null;
  link_up: boolean;
  reachable: boolean;
}

export interface ClosedEvent {
  closed: true;
}

export interface SetResult {
  sent: Weekday[];
  unchanged: Weekday[];
}

function toPeriods(ranges: WireRange[] | null, dayEnd: number): Period[] | null {
  if (ranges === null) {
    return null;
  }
  return ranges.map((range) => ({
    start: parseTime(range.start, dayEnd) ?? 0,
    end: parseTime(range.end, dayEnd) ?? 0,
  }));
}

/** Convert the data of the websocket API into the model of the card. */
export function parseState(wire: WireState): ScheduleState {
  const dayEnd = parseTime(wire.limits.day_end, 1440) ?? 1440;
  const limits: Limits = {
    stepMinutes: wire.limits.step_minutes,
    maxPeriods: wire.limits.max_periods,
    dayEnd,
  };
  const days = {} as Record<Weekday, DayState>;
  for (const weekday of WEEKDAYS) {
    const day = wire.days[weekday];
    days[weekday] = {
      status: day.status,
      periods: toPeriods(day.periods, dayEnd),
      requested: toPeriods(day.requested, dayEnd),
      pendingSince: day.pending_since,
    };
  }
  return {
    limits,
    days,
    readAt: wire.week_program_read_at,
    dayTemperature: wire.day_temperature,
    nightTemperature: wire.night_temperature,
    linkUp: wire.link_up,
    reachable: wire.reachable,
  };
}

const DAY_STATUSES: readonly string[] = [
  "unknown",
  "saved",
  "queued",
  "sending",
  "unconfirmed",
  "error",
];
// Generous bounds for what the thermostat reports, so that a value like 0 or a million
// cannot make the card divide by zero or draw without end.
const MAX_STEP_MINUTES = 1440;
const MAX_PERIODS = 100;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCount(value: unknown, maximum: number): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 1 && value <= maximum;
}

function isNumberOrNull(value: unknown): boolean {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isTextOrNull(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function isRanges(value: unknown): boolean {
  return (
    value === null ||
    (Array.isArray(value) &&
      value.every(
        (range) =>
          isRecord(range) && typeof range.start === "string" && typeof range.end === "string",
      ))
  );
}

/**
 * Return whether data from the server has the form the card relies on.
 *
 * The websocket messages are not trusted: a message of another form would otherwise
 * fail in the middle of a render and leave the card empty.
 */
export function isWireState(value: unknown): value is WireState {
  if (!isRecord(value) || !isRecord(value.limits) || !isRecord(value.days)) {
    return false;
  }
  const { limits, days } = value;
  return (
    isCount(limits.step_minutes, MAX_STEP_MINUTES) &&
    isCount(limits.max_periods, MAX_PERIODS) &&
    typeof limits.day_end === "string" &&
    WEEKDAYS.every((weekday) => {
      const day = days[weekday];
      return (
        isRecord(day) &&
        typeof day.status === "string" &&
        DAY_STATUSES.includes(day.status) &&
        isRanges(day.periods) &&
        isRanges(day.requested) &&
        isTextOrNull(day.pending_since)
      );
    }) &&
    isTextOrNull(value.week_program_read_at) &&
    isNumberOrNull(value.day_temperature) &&
    isNumberOrNull(value.night_temperature) &&
    typeof value.link_up === "boolean" &&
    typeof value.reachable === "boolean"
  );
}

export function isClosed(event: unknown): event is ClosedEvent {
  return isRecord(event) && event.closed === true;
}

/**
 * Subscribe to the week program of a thermostat.
 *
 * The result stops the subscription. The server sends the state at once and then
 * whenever it changes, and a last event `closed` when the entity goes away. An event
 * of another form goes to `onInvalid` and changes nothing else.
 */
export function subscribeSchedule(
  hass: Hass,
  entityId: string,
  onState: (state: ScheduleState) => void,
  onClosed: () => void,
  onInvalid: () => void,
): Promise<() => void> {
  return hass.connection.subscribeMessage<unknown>(
    (event) => {
      if (isClosed(event)) {
        onClosed();
      } else if (isWireState(event)) {
        onState(parseState(event));
      } else {
        onInvalid();
      }
    },
    { type: "culfw/schedule/subscribe", entity_id: entityId },
  );
}

export function setSchedule(
  hass: Hass,
  entityId: string,
  days: Record<string, TextRange[]>,
): Promise<SetResult> {
  return hass.callWS<SetResult>({
    type: "culfw/schedule/set",
    entity_id: entityId,
    days,
  });
}

export function refreshSchedule(
  hass: Hass,
  entityId: string,
  days?: readonly Weekday[],
): Promise<{ days: Weekday[] }> {
  return hass.callWS<{ days: Weekday[] }>({
    type: "culfw/schedule/refresh",
    entity_id: entityId,
    ...(days === undefined ? {} : { days }),
  });
}

/** Return the error of a rejected websocket call in a known shape. */
export function asApiError(reason: unknown): ApiError {
  if (typeof reason === "object" && reason !== null) {
    const candidate = reason as Record<string, unknown>;
    const error: ApiError = {};
    if (typeof candidate.code === "string") {
      error.code = candidate.code;
    }
    if (typeof candidate.message === "string") {
      error.message = candidate.message;
    }
    if (typeof candidate.translation_key === "string") {
      error.translation_key = candidate.translation_key;
    }
    if (typeof candidate.translation_placeholders === "object") {
      error.translation_placeholders = candidate.translation_placeholders as Record<
        string,
        string
      > | null;
    }
    return error;
  }
  return { message: typeof reason === "string" ? reason : undefined };
}
