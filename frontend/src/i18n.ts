import type { Weekday } from "./types";
import { WEEKDAYS } from "./types";

type Params = Record<string, string | number>;

const en = {
  "card.title": "Week program",
  "card.stateUnknown": "Thermostat {entity} was not found.",
  "card.loading": "Loading the week program…",
  "temp.day": "Day",
  "temp.night": "Night",
  "temp.unknown": "unknown",
  "reach.ok": "Thermostat reachable",
  "reach.silent": "Thermostat not responding",
  "reach.link": "Radio stick disconnected",
  "reach.queueHint": "Changes wait in the queue and are sent when the thermostat answers.",
  "reach.linkHint": "Changes wait in the queue and are sent when the radio stick is back.",
  "status.unknown": "Not read",
  "status.saved": "Saved",
  "status.queued": "Queued",
  "status.sending": "Sending",
  "status.unconfirmed": "Not confirmed",
  "status.error": "Error",
  "status.edited": "Edited",
  "action.save": "Save",
  "action.saveCount": "Save ({count})",
  "action.discard": "Discard",
  "action.read": "Read now",
  "action.readWeek": "Read week",
  "action.readDay": "Read this day",
  "action.resend": "Send again",
  "action.editEmpty": "Edit an empty program",
  "action.copy": "Copy to other days…",
  "action.clear": "Clear day",
  "action.reset": "Reset day",
  "action.add": "Add heating period",
  "action.remove": "Remove",
  "action.merge": "Merge touching periods",
  "action.back": "Back to the week",
  "action.cancel": "Cancel",
  "action.copyApply": "Copy",
  "action.overwrite": "Overwrite",
  "action.retry": "Try again",
  "action.dismiss": "Dismiss",
  "preset.weekdays": "Weekdays",
  "preset.weekend": "Weekend",
  "preset.all": "All days",
  "empty.title": "The week program has not been read yet.",
  "empty.body":
    "The thermostat sends it in 28 radio telegrams, so reading the whole week takes about 35 minutes.",
  "empty.requested": "Reading was requested. The days appear here as the thermostat reports them.",
  "load.error": "The week program could not be loaded: {message}",
  "list.noHeating": "Night temperature all day",
  "list.unknown": "Not read yet",
  "legend.heating": "Heating period (day temperature)",
  "legend.night": "Night temperature",
  "legend.unknown": "Not read",
  "legend.pending": "On its way",
  "footer.clean": "No changes.",
  "footer.changed": "{count, plural, one {# day changed} other {# days changed}}",
  "footer.hint": "Each day takes about 2 minutes to reach the thermostat.",
  "day.unknownHint": "This day was never read. Saving replaces the whole day in the thermostat.",
  "day.pendingHint": "This day is on its way to the thermostat.",
  "day.editor": "Edit {day}",
  "field.start": "Start",
  "field.end": "End",
  "field.period": "Period {n}",
  "field.earlier": "10 minutes earlier",
  "field.later": "10 minutes later",
  "aria.start": "{day}, period {n}, start",
  "aria.end": "{day}, period {n}, end",
  "aria.move": "{day}, period {n}, move",
  "aria.track": "{day}, heating periods",
  "aria.row": "{day}: {summary}, {status}",
  "aria.startField": "{day}, period {n}, start time",
  "aria.endField": "{day}, period {n}, end time",
  "aria.startEarlier": "{day}, period {n}, start 10 minutes earlier",
  "aria.startLater": "{day}, period {n}, start 10 minutes later",
  "aria.endEarlier": "{day}, period {n}, end 10 minutes earlier",
  "aria.endLater": "{day}, period {n}, end 10 minutes later",
  "aria.remove": "{day}, remove period {n}",
  "announce.sent": "Sent to the thermostat: {days}.",
  "announce.unchanged": "Already up to date: {days}.",
  "announce.read": "Reading was requested.",
  "announce.discarded": "Changes discarded.",
  "announce.copied": "Copied to {days}.",
  "copy.title": "Copy {day} to other days",
  "copy.body": "The copies are changes that you still have to save.",
  "confirm.title": "Overwrite days that were never read?",
  "confirm.body":
    "The days {days} were never read from the thermostat. Saving replaces them completely.",
  "error.save": "Saving failed: {message}",
  "error.read": "Reading failed: {message}",
  "error.unauthorized": "You are not allowed to change this thermostat.",
  "error.unsupported":
    "The integration does not know the week program commands. Update the integration and reload the page.",
  "error.unknown": "Something went wrong.",
  "error.invalid": "The data from Home Assistant has an unexpected form.",
  "err.schedule_time_invalid":
    "{day}: {value} is not a time of day. Write it as HH:MM, for example 06:30, and use 24:00 for the end of the day.",
  "err.schedule_time_step":
    "{day}: {value} is not a multiple of {step} minutes. The thermostat switches in steps of {step} minutes.",
  "err.schedule_too_many_ranges":
    "{day}: {count} time ranges are too many. The thermostat takes at most {max_ranges} ranges per day.",
  "err.schedule_range_backwards":
    "{day}: the range from {start} to {end} must end after it starts. Use 24:00 for midnight at the end of the day.",
  "err.schedule_ranges_overlap":
    "{day}: the ranges from {first_start} to {first_end} and from {second_start} to {second_end} overlap.",
  "err.schedule_partly_sent":
    "Only part of the week program was sent. The days {sent} are on their way, and the days {unsent} were not sent. Set those days again.",
  "err.schedule_entity_unknown":
    "{entity_id} is not the climate entity of a thermostat of this integration.",
  "err.send_unknown_device":
    "The thermostat {code} has not been heard yet, so nothing can be sent to it. Wait until it transmits, which can take a few minutes.",
  "err.send_device_silent":
    "The thermostat {code} has been silent for {minutes} minutes, so it would never collect the command. Check its batteries and its distance to the radio stick.",
  "err.send_device_unconfirmed":
    "The thermostat {code} never echoed a command of this radio stick, so nothing is sent to it on its own.",
  "err.send_device_unresponsive":
    "The thermostat {code} did not echo the last messages, so only commands that you ask for are sent to it.",
  "err.send_not_connected":
    "The radio stick is not connected, its state is {state}. It connects again automatically.",
  "err.send_no_credit":
    "The 1% radio budget is used up. It has {credit} ms left and needs {minimum} ms. Try again in a few minutes.",
  "err.send_credit_exhausted":
    "The 1% radio budget stayed below {minimum} ms for {minutes} minutes, so the command was not sent. Try again in a few minutes.",
  "err.send_buffer_full":
    "The buffer of the radio stick has {free} bytes free, but the command needs {needed} bytes plus {reserve} bytes of reserve. Try again after the thermostats have collected the waiting commands.",
  "err.send_not_queued":
    "The radio stick did not take the {count} commands, because its buffer overflowed. Try again in a few minutes.",
  "err.send_blocked":
    "The command was not sent, because the radio stick does not allow it. This is a bug of the integration, so please report it.",
  "err.send_cul_error":
    "The radio stick did not answer the command, and its state is {state}. Check that it is connected and try again.",
} as const;

export type StringKey = keyof typeof en;

const de: Record<StringKey, string> = {
  "card.title": "Wochenprogramm",
  "card.stateUnknown": "Das Thermostat {entity} wurde nicht gefunden.",
  "card.loading": "Das Wochenprogramm wird geladen …",
  "temp.day": "Tag",
  "temp.night": "Nacht",
  "temp.unknown": "unbekannt",
  "reach.ok": "Thermostat erreichbar",
  "reach.silent": "Thermostat meldet sich nicht",
  "reach.link": "Funkstick getrennt",
  "reach.queueHint":
    "Änderungen warten in der Warteschlange und werden gesendet, sobald das Thermostat antwortet.",
  "reach.linkHint":
    "Änderungen warten in der Warteschlange und werden gesendet, sobald der Funkstick wieder da ist.",
  "status.unknown": "Nicht gelesen",
  "status.saved": "Gespeichert",
  "status.queued": "Wartet",
  "status.sending": "Wird gesendet",
  "status.unconfirmed": "Nicht bestätigt",
  "status.error": "Fehler",
  "status.edited": "Geändert",
  "action.save": "Speichern",
  "action.saveCount": "Speichern ({count})",
  "action.discard": "Verwerfen",
  "action.read": "Jetzt abrufen",
  "action.readWeek": "Woche abrufen",
  "action.readDay": "Diesen Tag abrufen",
  "action.resend": "Erneut senden",
  "action.editEmpty": "Leeres Programm bearbeiten",
  "action.copy": "Auf andere Tage kopieren …",
  "action.clear": "Tag leeren",
  "action.reset": "Tag zurücksetzen",
  "action.add": "Heizphase hinzufügen",
  "action.remove": "Entfernen",
  "action.merge": "Aneinandergrenzende Phasen verbinden",
  "action.back": "Zurück zur Woche",
  "action.cancel": "Abbrechen",
  "action.copyApply": "Kopieren",
  "action.overwrite": "Überschreiben",
  "action.retry": "Erneut versuchen",
  "action.dismiss": "Schließen",
  "preset.weekdays": "Werktage",
  "preset.weekend": "Wochenende",
  "preset.all": "Alle Tage",
  "empty.title": "Das Wochenprogramm wurde noch nicht gelesen.",
  "empty.body":
    "Das Thermostat sendet es in 28 Funktelegrammen, der Abruf der ganzen Woche dauert deshalb etwa 35 Minuten.",
  "empty.requested":
    "Der Abruf wurde angefordert. Die Tage erscheinen hier, sobald das Thermostat sie meldet.",
  "load.error": "Das Wochenprogramm konnte nicht geladen werden: {message}",
  "list.noHeating": "Den ganzen Tag Nachttemperatur",
  "list.unknown": "Noch nicht gelesen",
  "legend.heating": "Heizphase (Tagestemperatur)",
  "legend.night": "Nachttemperatur",
  "legend.unknown": "Nicht gelesen",
  "legend.pending": "Unterwegs",
  "footer.clean": "Keine Änderungen.",
  "footer.changed": "{count, plural, one {# Tag geändert} other {# Tage geändert}}",
  "footer.hint": "Jeder Tag braucht etwa 2 Minuten bis zum Thermostat.",
  "day.unknownHint":
    "Dieser Tag wurde noch nie gelesen. Speichern ersetzt den ganzen Tag im Thermostat.",
  "day.pendingHint": "Dieser Tag ist auf dem Weg zum Thermostat.",
  "day.editor": "{day} bearbeiten",
  "field.start": "Beginn",
  "field.end": "Ende",
  "field.period": "Phase {n}",
  "field.earlier": "10 Minuten früher",
  "field.later": "10 Minuten später",
  "aria.start": "{day}, Phase {n}, Beginn",
  "aria.end": "{day}, Phase {n}, Ende",
  "aria.move": "{day}, Phase {n}, verschieben",
  "aria.track": "{day}, Heizphasen",
  "aria.row": "{day}: {summary}, {status}",
  "aria.startField": "{day}, Phase {n}, Beginn als Uhrzeit",
  "aria.endField": "{day}, Phase {n}, Ende als Uhrzeit",
  "aria.startEarlier": "{day}, Phase {n}, Beginn 10 Minuten früher",
  "aria.startLater": "{day}, Phase {n}, Beginn 10 Minuten später",
  "aria.endEarlier": "{day}, Phase {n}, Ende 10 Minuten früher",
  "aria.endLater": "{day}, Phase {n}, Ende 10 Minuten später",
  "aria.remove": "{day}, Phase {n} entfernen",
  "announce.sent": "An das Thermostat gesendet: {days}.",
  "announce.unchanged": "Schon aktuell: {days}.",
  "announce.read": "Der Abruf wurde angefordert.",
  "announce.discarded": "Änderungen verworfen.",
  "announce.copied": "Kopiert nach {days}.",
  "copy.title": "{day} auf andere Tage kopieren",
  "copy.body": "Die Kopien sind Änderungen, die du noch speichern musst.",
  "confirm.title": "Tage überschreiben, die nie gelesen wurden?",
  "confirm.body":
    "Die Tage {days} wurden nie vom Thermostat gelesen. Speichern ersetzt sie vollständig.",
  "error.save": "Speichern fehlgeschlagen: {message}",
  "error.read": "Abruf fehlgeschlagen: {message}",
  "error.unauthorized": "Du darfst dieses Thermostat nicht ändern.",
  "error.unsupported":
    "Die Integration kennt die Befehle des Wochenprogramms nicht. Aktualisiere die Integration und lade die Seite neu.",
  "error.unknown": "Etwas ist schiefgelaufen.",
  "error.invalid": "Die Daten von Home Assistant haben eine unerwartete Form.",
  "err.schedule_time_invalid":
    "{day}: {value} ist keine Uhrzeit. Schreibe sie als HH:MM, zum Beispiel 06:30, und nimm 24:00 für das Tagesende.",
  "err.schedule_time_step":
    "{day}: {value} ist kein Vielfaches von {step} Minuten. Das Thermostat schaltet in Schritten von {step} Minuten.",
  "err.schedule_too_many_ranges":
    "{day}: {count} Zeitbereiche sind zu viele. Das Thermostat nimmt höchstens {max_ranges} Bereiche pro Tag.",
  "err.schedule_range_backwards":
    "{day}: Der Bereich von {start} bis {end} muss nach seinem Beginn enden. Nimm 24:00 für Mitternacht am Tagesende.",
  "err.schedule_ranges_overlap":
    "{day}: Die Bereiche von {first_start} bis {first_end} und von {second_start} bis {second_end} überlappen sich.",
  "err.schedule_partly_sent":
    "Nur ein Teil des Wochenprogramms wurde gesendet. Die Tage {sent} sind unterwegs, die Tage {unsent} wurden nicht gesendet. Setze diese Tage noch einmal.",
  "err.schedule_entity_unknown":
    "{entity_id} ist nicht die Klima-Entität eines Thermostats dieser Integration.",
  "err.send_unknown_device":
    "Das Thermostat {code} wurde noch nicht gehört, deshalb kann ihm nichts gesendet werden. Warte, bis es sendet, das kann einige Minuten dauern.",
  "err.send_device_silent":
    "Das Thermostat {code} ist seit {minutes} Minuten still und würde den Befehl nie abholen. Prüfe seine Batterien und den Abstand zum Funkstick.",
  "err.send_device_unconfirmed":
    "Das Thermostat {code} hat nie einen Befehl dieses Funksticks bestätigt, deshalb wird ihm nichts von selbst gesendet.",
  "err.send_device_unresponsive":
    "Das Thermostat {code} hat die letzten Nachrichten nicht bestätigt, deshalb bekommt es nur noch Befehle, die du anforderst.",
  "err.send_not_connected":
    "Der Funkstick ist nicht verbunden, sein Zustand ist {state}. Er verbindet sich von selbst wieder.",
  "err.send_no_credit":
    "Das 1-%-Sendebudget ist aufgebraucht. Es hat noch {credit} ms und braucht {minimum} ms. Versuche es in einigen Minuten noch einmal.",
  "err.send_credit_exhausted":
    "Das 1-%-Sendebudget blieb {minutes} Minuten unter {minimum} ms, deshalb wurde der Befehl nicht gesendet. Versuche es in einigen Minuten noch einmal.",
  "err.send_buffer_full":
    "Der Puffer des Funksticks hat {free} Byte frei, aber der Befehl braucht {needed} Byte plus {reserve} Byte Reserve. Versuche es noch einmal, wenn die Thermostate die wartenden Befehle abgeholt haben.",
  "err.send_not_queued":
    "Der Funkstick hat die {count} Befehle nicht angenommen, weil sein Puffer übergelaufen ist. Versuche es in einigen Minuten noch einmal.",
  "err.send_blocked":
    "Der Befehl wurde nicht gesendet, weil der Funkstick ihn nicht erlaubt. Das ist ein Fehler der Integration, bitte melde ihn.",
  "err.send_cul_error":
    "Der Funkstick hat den Befehl nicht beantwortet, sein Zustand ist {state}. Prüfe, ob er verbunden ist, und versuche es noch einmal.",
};

const WEEKDAY_NAMES: Record<string, Record<Weekday, string>> = {
  en: {
    monday: "Monday",
    tuesday: "Tuesday",
    wednesday: "Wednesday",
    thursday: "Thursday",
    friday: "Friday",
    saturday: "Saturday",
    sunday: "Sunday",
  },
  de: {
    monday: "Montag",
    tuesday: "Dienstag",
    wednesday: "Mittwoch",
    thursday: "Donnerstag",
    friday: "Freitag",
    saturday: "Samstag",
    sunday: "Sonntag",
  },
};

const WEEKDAY_SHORT: Record<string, Record<Weekday, string>> = {
  en: {
    monday: "Mon",
    tuesday: "Tue",
    wednesday: "Wed",
    thursday: "Thu",
    friday: "Fri",
    saturday: "Sat",
    sunday: "Sun",
  },
  de: {
    monday: "Mo",
    tuesday: "Di",
    wednesday: "Mi",
    thursday: "Do",
    friday: "Fr",
    saturday: "Sa",
    sunday: "So",
  },
};

export type Language = "en" | "de";

/** Pick the language of the card from the language of Home Assistant. */
export function pickLanguage(language: string | undefined): Language {
  return (language ?? "").toLowerCase().startsWith("de") ? "de" : "en";
}

/**
 * The name and description of the card in the card picker.
 *
 * The picker of the dashboard editor shows one fixed name and searches the name and
 * the description. Each text therefore also holds the name of the other language, so
 * that a search for either name finds the card.
 */
const PICKER: Record<Language, { name: string; description: string }> = {
  en: {
    name: "FHT week program",
    description:
      "Shows and edits the week heating program of an FHT80b thermostat (German: FHT Wochenprogramm).",
  },
  de: {
    name: "FHT Wochenprogramm",
    description:
      "Zeigt das Wochenheizprogramm eines FHT80b-Thermostats an und ändert es (englisch: FHT week program).",
  },
};

/** Return the text that the card picker shows for the card in a language. */
export function pickerText(language: Language): { name: string; description: string } {
  return PICKER[language];
}

const PLURAL = /\{(\w+), plural, one \{([^}]*)\} other \{([^}]*)\}\}/;

/** Return a text of the card with its placeholders filled in. */
export function t(language: Language, key: StringKey, params: Params = {}): string {
  let text: string = language === "de" ? de[key] : en[key];
  text = text.replace(PLURAL, (_match, name: string, one: string, other: string) => {
    const chosen = Number(params[name]) === 1 ? one : other;
    return chosen.replace("#", String(params[name]));
  });
  return text.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}

export function dayName(language: Language, weekday: Weekday): string {
  return WEEKDAY_NAMES[language]?.[weekday] ?? weekday;
}

export function dayShort(language: Language, weekday: Weekday): string {
  return WEEKDAY_SHORT[language]?.[weekday] ?? weekday;
}

function translateDay(language: Language, value: string): string {
  const english = WEEKDAY_NAMES.en as Record<Weekday, string>;
  const weekday = WEEKDAYS.find((name) => english[name] === value);
  return weekday === undefined ? value : dayName(language, weekday);
}

export interface ApiError {
  code?: string;
  message?: string;
  translation_key?: string | null;
  translation_placeholders?: Record<string, string> | null;
}

function isErrorKey(key: string): key is StringKey {
  return key in en;
}

/** Return the text for a validation error or an error of the websocket API. */
export function describeError(
  language: Language,
  error: ApiError | null | undefined,
  params: Params = {},
): string {
  const key = error?.translation_key;
  if (key && isErrorKey(`err.${key}`)) {
    const merged: Params = { ...(error?.translation_placeholders ?? {}), ...params };
    if (typeof merged.day === "string") {
      merged.day = translateDay(language, merged.day);
    }
    return t(language, `err.${key}` as StringKey, merged);
  }
  if (error?.code === "unauthorized") {
    return t(language, "error.unauthorized");
  }
  if (error?.code === "unknown_command") {
    return t(language, "error.unsupported");
  }
  return error?.message || t(language, "error.unknown");
}

/** Return the keys of one language, for the test that compares both. */
export function stringKeys(language: Language): string[] {
  return Object.keys(language === "de" ? de : en);
}
