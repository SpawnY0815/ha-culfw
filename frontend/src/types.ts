export const WEEKDAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
] as const;

export type Weekday = (typeof WEEKDAYS)[number];

/** Minutes after midnight. The end of a day is 1440, shown as 24:00. */
export interface Period {
  start: number;
  end: number;
}

export type DayStatus = "unknown" | "saved" | "queued" | "sending" | "unconfirmed" | "error";

export interface Limits {
  stepMinutes: number;
  maxPeriods: number;
  dayEnd: number;
}

export interface DayState {
  status: DayStatus;
  /** What the thermostat reported, null while the day was never read. */
  periods: Period[] | null;
  /** What is on its way, set while the day is queued or sending. */
  requested: Period[] | null;
  pendingSince: string | null;
}

export interface ScheduleState {
  limits: Limits;
  days: Record<Weekday, DayState>;
  readAt: string | null;
  dayTemperature: number | null;
  nightTemperature: number | null;
  linkUp: boolean;
  reachable: boolean;
}

/** Unsaved periods of the days that the user edited. */
export type Draft = Partial<Record<Weekday, Period[]>>;

export interface CardConfig {
  type?: string;
  entity: string;
  name?: unknown;
}

export interface EntityState {
  state: string;
  attributes: Record<string, unknown>;
}

/** The part of the Home Assistant frontend object that the card uses. */
export interface Hass {
  language: string;
  states: Record<string, EntityState | undefined>;
  entities?: Record<string, { platform?: string } | undefined>;
  callWS<T>(message: Record<string, unknown>): Promise<T>;
  connection: {
    subscribeMessage<T>(
      callback: (message: T) => void,
      message: Record<string, unknown>,
    ): Promise<() => void>;
  };
  formatEntityName?(state: EntityState, name?: unknown): string;
}
