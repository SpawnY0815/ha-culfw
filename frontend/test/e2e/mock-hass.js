// A stand-in for the Home Assistant frontend: the objects that the card talks to
// and a server that behaves like the websocket commands of the integration.
(() => {
  const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
  const ENTITY = "climate.living_room";

  // The card wraps itself in ha-card, which only exists in Home Assistant.
  class MockHaCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" }).innerHTML =
        "<style>:host{display:block;background:var(--card-background-color);" +
        "border-radius:12px;border:1px solid var(--divider-color)}</style><slot></slot>";
    }
  }
  customElements.define("ha-card", MockHaCard);

  const range = (start, end) => ({ start, end });
  const saved = (ranges) => ({
    status: "saved",
    periods: ranges,
    requested: null,
    pending_since: null,
  });

  function defaultDays() {
    const workday = saved([range("06:00", "09:00")]);
    const weekend = saved([range("07:30", "24:00")]);
    return {
      monday: saved([range("06:00", "08:30"), range("17:00", "22:00")]),
      tuesday: saved([range("06:00", "08:30")]),
      wednesday: structuredClone(workday),
      thursday: structuredClone(workday),
      friday: structuredClone(workday),
      saturday: structuredClone(weekend),
      sunday: structuredClone(weekend),
    };
  }

  function unknownDays() {
    return Object.fromEntries(
      WEEKDAYS.map((day) => [
        day,
        { status: "unknown", periods: null, requested: null, pending_since: null },
      ]),
    );
  }

  class MockServer {
    constructor(options) {
      this.calls = [];
      this.listeners = new Set();
      this.subscriptions = 0;
      this.failNext = null;
      this.failSubscribe = null;
      this.state = {
        limits: { step_minutes: 10, max_periods: 2, day_end: "24:00" },
        days: options.unknown ? unknownDays() : defaultDays(),
        week_program_read_at: options.unknown ? null : "2026-10-20T08:00:00+00:00",
        day_temperature: 21,
        night_temperature: 17,
        link_up: true,
        reachable: true,
        ...options.state,
      };
      for (const [day, value] of Object.entries(options.days ?? {})) {
        Object.assign(this.state.days[day], value);
      }
    }

    wire() {
      return structuredClone(this.state);
    }

    // Change the state of the server like a telegram or a status change would.
    push(patch) {
      const { days, ...rest } = patch;
      Object.assign(this.state, rest);
      if (days) {
        for (const [day, value] of Object.entries(days)) {
          Object.assign(this.state.days[day], value);
        }
      }
      for (const listener of this.listeners) {
        listener(this.wire());
      }
    }

    // Send an event as it is, also one that the server would never send.
    pushRaw(event) {
      for (const listener of this.listeners) {
        listener(structuredClone(event));
      }
    }

    close() {
      for (const listener of [...this.listeners]) {
        listener({ closed: true });
      }
      this.listeners.clear();
    }

    async call(message) {
      this.calls.push(structuredClone(message));
      if (this.failNext) {
        const error = this.failNext;
        this.failNext = null;
        throw error;
      }
      if (message.type === "culfw/schedule/set") {
        const sent = Object.keys(message.days);
        for (const day of sent) {
          this.state.days[day].status = "queued";
          this.state.days[day].requested = structuredClone(message.days[day]);
          this.state.days[day].pending_since = "2026-10-20T10:00:00+00:00";
        }
        this.push({});
        return { sent, unchanged: [] };
      }
      if (message.type === "culfw/schedule/refresh") {
        return { days: message.days ?? WEEKDAYS };
      }
      throw { code: "unknown_command", message: "Unknown command." };
    }

    async subscribe(callback, message) {
      this.calls.push(structuredClone(message));
      if (this.failSubscribe) {
        throw this.failSubscribe;
      }
      this.subscriptions += 1;
      this.listeners.add(callback);
      queueMicrotask(() => callback(this.wire()));
      return () => {
        this.listeners.delete(callback);
      };
    }
  }

  // Mount a card with a mock server. Options: language, width, unknown, days, state.
  window.mountCard = async (options = {}) => {
    const server = new MockServer(options);
    const hass = {
      language: options.language ?? "en",
      states: {
        [ENTITY]: { state: "auto", attributes: { friendly_name: "Living room" } },
      },
      entities: { [ENTITY]: { platform: "culfw" } },
      callWS: (message) => server.call(message),
      connection: { subscribeMessage: (callback, message) => server.subscribe(callback, message) },
    };
    const card = document.createElement("fht-schedule-card");
    if (options.width) {
      card.style.width = `${options.width}px`;
      card.style.display = "block";
    }
    card.setConfig({ type: "custom:fht-schedule-card", entity: ENTITY });
    card.hass = hass;
    document.getElementById("root").replaceChildren(card);
    window.__server = server;
    window.__hass = hass;
    window.__card = card;
    await card.updateComplete;
  };
})();
