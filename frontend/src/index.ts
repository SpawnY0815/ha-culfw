import { FhtScheduleCard } from "./card";
import { pickerText, pickLanguage } from "./i18n";
import type { Hass } from "./types";

const TAG = "fht-schedule-card";

declare global {
  interface Window {
    customCards?: Record<string, unknown>[];
  }
}

// The module can load twice, once as a dashboard resource and once as an extra
// module of the frontend, and a custom element can only be defined once.
if (!customElements.get(TAG)) {
  customElements.define(TAG, FhtScheduleCard);
}

/**
 * Return the language of Home Assistant when the card picker asks for the text.
 *
 * The picker shows the name and description as they are and has no hook for a
 * translation, so the entry below reads them through getters at the moment the
 * picker opens. By then the frontend has its user and its language. The language of
 * the document is the fallback for a page where the frontend is not there (yet).
 */
function pickerLanguage() {
  const frontend = document.querySelector("home-assistant") as { hass?: Hass } | null;
  return pickLanguage(frontend?.hass?.language || document.documentElement.lang);
}

window.customCards = window.customCards ?? [];
if (!window.customCards.some((card) => card.type === TAG)) {
  window.customCards.push({
    type: TAG,
    get name() {
      return pickerText(pickerLanguage()).name;
    },
    get description() {
      return pickerText(pickerLanguage()).description;
    },
    preview: false,
    documentationURL: "https://github.com/SpawnY0815/ha-culfw",
    getEntitySuggestion: (hass: Hass, entityId: string) =>
      entityId.startsWith("climate.") && hass.entities?.[entityId]?.platform === "culfw"
        ? { config: { type: `custom:${TAG}`, entity: entityId } }
        : null,
  });
}
