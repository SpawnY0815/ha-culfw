import { LitElement, html, nothing } from "lit";
import type { PropertyValues, TemplateResult } from "lit";
import { live } from "lit/directives/live.js";
import "./day-track";
import type { TrackLabel } from "./day-track";
import {
  copyTargets,
  dirtyDays,
  formatTime,
  hasTouching,
  mergeTouching,
  parseTime,
  periodsEqual,
  removePeriod,
  resizeEnd,
  resizeStart,
  shownPeriods,
  sortPeriods,
  suggestPeriod,
  toWire,
  validateDay,
} from "./model";
import type { CopyPreset, ValidationError } from "./model";
import { dayName, dayShort, describeError, pickLanguage, t } from "./i18n";
import type { Language, StringKey } from "./i18n";
import { cardStyles } from "./styles";
import { WEEKDAYS } from "./types";
import type { CardConfig, DayStatus, Draft, Hass, Period, ScheduleState, Weekday } from "./types";
import { asApiError, refreshSchedule, setSchedule, subscribeSchedule } from "./ws";

type Dialog = { kind: "copy"; source: Weekday } | { kind: "confirm"; days: Weekday[] };

interface Banner {
  kind: "error" | "info";
  text: string;
}

interface FieldError {
  text: string;
  message: string;
}

const NARROW_BELOW_PX = 540;
const RESUBSCRIBE_DELAY_MS = 1000;
const CHIP_ICONS: Record<DayStatus | "edited", string> = {
  unknown: "?",
  saved: "✓",
  queued: "…",
  sending: "↗",
  unconfirmed: "!",
  error: "✕",
  edited: "✎",
};

export class FhtScheduleCard extends LitElement {
  static override properties = {
    _state: { state: true },
    _draft: { state: true },
    _selected: { state: true },
    _narrow: { state: true },
    _banner: { state: true },
    _loadError: { state: true },
    _busy: { state: true },
    _announce: { state: true },
    _dialog: { state: true },
    _copyTo: { state: true },
    _fieldErrors: { state: true },
    _readRequested: { state: true },
    _editEmpty: { state: true },
    _config: { state: true },
  };

  declare _state: ScheduleState | null;
  declare _draft: Draft;
  declare _selected: Weekday | null;
  declare _narrow: boolean;
  declare _banner: Banner | null;
  declare _loadError: string | null;
  declare _busy: boolean;
  declare _announce: string;
  declare _dialog: Dialog | null;
  declare _copyTo: Weekday[];
  declare _fieldErrors: Record<string, FieldError>;
  declare _readRequested: boolean;
  declare _editEmpty: boolean;
  declare _config: CardConfig | null;

  private _hass: Hass | undefined;
  private _unsubscribe: (() => void) | null = null;
  private _subscribing = false;
  private _token = 0;
  private _retryTimer: ReturnType<typeof setTimeout> | undefined;
  private _observer: ResizeObserver | undefined;
  /** Set by Home Assistant while the card is shown in the card editor. */
  preview = false;

  constructor() {
    super();
    this._state = null;
    this._draft = {};
    this._selected = null;
    this._narrow = false;
    this._banner = null;
    this._loadError = null;
    this._busy = false;
    this._announce = "";
    this._dialog = null;
    this._copyTo = [];
    this._fieldErrors = {};
    this._readRequested = false;
    this._editEmpty = false;
    this._config = null;
  }

  static override styles = cardStyles;

  setConfig(config: CardConfig): void {
    if (typeof config?.entity !== "string" || !config.entity.startsWith("climate.")) {
      throw new Error("You need to define a climate entity of the culfw integration.");
    }
    if (this._config?.entity !== config.entity) {
      this._stop();
      this._state = null;
      this._draft = {};
      this._selected = null;
      this._loadError = null;
    }
    this._config = config;
    this._ensureSubscription();
  }

  set hass(hass: Hass) {
    const previous = this._hass;
    this._hass = hass;
    const entity = this._config?.entity;
    if (
      previous === undefined ||
      previous.language !== hass.language ||
      (entity !== undefined && previous.states[entity] !== hass.states[entity])
    ) {
      this.requestUpdate();
    }
    this._ensureSubscription();
  }

  get hass(): Hass | undefined {
    return this._hass;
  }

  getCardSize(): number {
    return 9;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  static getStubConfig(
    hass: Hass,
    entities: string[],
    entitiesFallback: string[],
  ): { entity: string } {
    const own = [...entities, ...entitiesFallback].find(
      (id) => id.startsWith("climate.") && hass.entities?.[id]?.platform === "culfw",
    );
    return { entity: own ?? "" };
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { filter: { domain: "climate", integration: "culfw" } } },
        },
        {
          name: "name",
          selector: { entity_name: {} },
          context: { entity: "entity" },
        },
      ],
      // Keys that the form does not edit, like grid_options and visibility, stay in
      // the configuration, so only values the form cannot show are refused.
      assertConfig: (config: Record<string, unknown>) => {
        for (const key of ["entity", "name"]) {
          if (config[key] !== undefined && typeof config[key] !== "string") {
            throw new Error(`'${key}' must be a string.`);
          }
        }
      },
    };
  }

  override connectedCallback(): void {
    super.connectedCallback();
    this._observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (width > 0) {
        this._narrow = width < NARROW_BELOW_PX;
      }
    });
    this._observer.observe(this);
    this._ensureSubscription();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this._observer?.disconnect();
    this._stop();
  }

  protected override updated(changed: PropertyValues<this>): void {
    if (changed.has("_dialog") && this._dialog !== null) {
      const dialog = this.renderRoot.querySelector("dialog");
      if (dialog !== null && !dialog.open) {
        dialog.showModal();
      }
    }
  }

  private get _language(): Language {
    return pickLanguage(this._hass?.language);
  }

  private _t(key: StringKey, params: Record<string, string | number> = {}): string {
    return t(this._language, key, params);
  }

  private _day(weekday: Weekday): string {
    return dayName(this._language, weekday);
  }

  private _stop(): void {
    this._token += 1;
    clearTimeout(this._retryTimer);
    this._retryTimer = undefined;
    this._subscribing = false;
    this._unsubscribe?.();
    this._unsubscribe = null;
  }

  private _ensureSubscription(): void {
    const entity = this._config?.entity;
    const hass = this._hass;
    if (
      !this.isConnected ||
      entity === undefined ||
      hass === undefined ||
      hass.states[entity] === undefined ||
      this._unsubscribe !== null ||
      this._subscribing ||
      this._retryTimer !== undefined ||
      this._loadError !== null
    ) {
      return;
    }
    void this._subscribe(hass, entity);
  }

  private async _subscribe(hass: Hass, entity: string): Promise<void> {
    const token = ++this._token;
    this._subscribing = true;
    try {
      const unsubscribe = await subscribeSchedule(
        hass,
        entity,
        (state) => {
          if (token === this._token) {
            this._state = state;
            this._loadError = null;
            if (WEEKDAYS.some((day) => state.days[day].periods !== null)) {
              this._readRequested = false;
            }
          }
        },
        () => {
          if (token === this._token) {
            this._unsubscribe?.();
            this._unsubscribe = null;
            this._retryTimer = setTimeout(() => {
              this._retryTimer = undefined;
              this._ensureSubscription();
            }, RESUBSCRIBE_DELAY_MS);
          }
        },
        () => {
          if (token === this._token) {
            this._loadError = this._t("error.invalid");
          }
        },
      );
      if (token === this._token) {
        this._unsubscribe = unsubscribe;
      } else {
        unsubscribe();
      }
    } catch (reason) {
      if (token === this._token) {
        this._loadError = describeError(this._language, asApiError(reason));
      }
    } finally {
      if (token === this._token) {
        this._subscribing = false;
      }
    }
  }

  private _retry(): void {
    this._stop();
    this._loadError = null;
    this._ensureSubscription();
  }

  private _periodsOf(weekday: Weekday): Period[] {
    const state = this._state as ScheduleState;
    return this._draft[weekday] ?? shownPeriods(state.days[weekday]) ?? [];
  }

  private _isDirty(weekday: Weekday): boolean {
    return this._state !== null && dirtyDays(this._draft, this._state.days).includes(weekday);
  }

  private _edit(weekday: Weekday, periods: Period[]): void {
    const state = this._state as ScheduleState;
    const shown = shownPeriods(state.days[weekday]);
    const next = { ...this._draft };
    const sorted = sortPeriods(periods);
    if (shown !== null && periodsEqual(sorted, shown)) {
      delete next[weekday];
    } else {
      next[weekday] = sorted;
    }
    this._draft = next;
    this._banner = null;
    this._clearFieldErrors(weekday);
  }

  private _clearFieldErrors(weekday: Weekday): void {
    const remaining = Object.fromEntries(
      Object.entries(this._fieldErrors).filter(([key]) => !key.startsWith(`${weekday}-`)),
    );
    this._fieldErrors = remaining;
  }

  private _onTrackChange(weekday: Weekday, event: CustomEvent<{ periods: Period[] }>): void {
    this._selected = weekday;
    this._edit(weekday, event.detail.periods);
  }

  private _status(weekday: Weekday): DayStatus | "edited" {
    const state = this._state as ScheduleState;
    return this._isDirty(weekday) ? "edited" : state.days[weekday].status;
  }

  private _summary(weekday: Weekday): string {
    const state = this._state as ScheduleState;
    const day = state.days[weekday];
    const draft = this._draft[weekday];
    if (draft === undefined && shownPeriods(day) === null) {
      return this._t("list.unknown");
    }
    const periods = this._periodsOf(weekday);
    if (periods.length === 0) {
      return this._t("list.noHeating");
    }
    return periods
      .map((period) => `${formatTime(period.start)}–${formatTime(period.end)}`)
      .join(" · ");
  }

  private _chip(status: DayStatus | "edited"): TemplateResult {
    return html`<span class="chip chip-${status}"
      ><span aria-hidden="true">${CHIP_ICONS[status]}</span
      ><span class="chip-text">${this._t(`status.${status}`)}</span></span
    >`;
  }

  private _labeler(weekday: Weekday): TrackLabel {
    return (kind, index) => this._t(`aria.${kind}`, { day: this._day(weekday), n: index + 1 });
  }

  private _validation(error: ValidationError, weekday: Weekday): string {
    return describeError(
      this._language,
      { translation_key: error.key, translation_placeholders: error.params },
      { day: this._day(weekday) },
    );
  }

  protected override render(): TemplateResult {
    const hass = this._hass;
    const config = this._config;
    if (hass === undefined || config === null) {
      return html``;
    }
    const entity = hass.states[config.entity];
    return html`<ha-card>
      <div class="root ${this._narrow ? "narrow" : ""}">
        ${
          entity === undefined
            ? html`<div class="banner error" role="alert">
                ${this._t("card.stateUnknown", { entity: config.entity })}
              </div>`
            : this._renderBody()
        }
        <div class="sr-only" role="status" aria-live="polite">${this._announce}</div>
      </div>
      ${this._renderDialog()}
    </ha-card>`;
  }

  private _title(): string {
    const hass = this._hass as Hass;
    const config = this._config as CardConfig;
    const entity = hass.states[config.entity];
    if (entity === undefined) {
      return config.entity;
    }
    if (hass.formatEntityName !== undefined) {
      return hass.formatEntityName(entity, config.name);
    }
    const friendly = entity.attributes.friendly_name;
    return typeof config.name === "string" && config.name
      ? config.name
      : typeof friendly === "string"
        ? friendly
        : config.entity;
  }

  private _renderBody(): TemplateResult {
    const state = this._state;
    if (this._loadError !== null) {
      return html`${this._renderHeader(null)}
        <div class="banner error" role="alert">
          <p>${this._t("load.error", { message: this._loadError })}</p>
          <button @click=${() => this._retry()}>${this._t("action.retry")}</button>
        </div>`;
    }
    if (state === null) {
      return html`${this._renderHeader(null)}
        <p class="hint">${this._t("card.loading")}</p>`;
    }
    const allUnknown = WEEKDAYS.every(
      (day) => shownPeriods(state.days[day]) === null && this._draft[day] === undefined,
    );
    const empty = allUnknown && !this._editEmpty;
    const editorOpen = this._selected !== null && !empty;
    return html`
      ${this._renderHeader(state)} ${this._renderBanners(state)}
      ${
        empty
          ? this._renderEmpty()
          : this._narrow && editorOpen
            ? this._renderEditor(this._selected as Weekday, state)
            : html`${this._renderGrid(state)}
              ${editorOpen ? this._renderEditor(this._selected as Weekday, state) : nothing}
              ${this._renderLegend()}`
      }
      ${empty ? nothing : this._renderFooter(state)}
    `;
  }

  private _renderHeader(state: ScheduleState | null): TemplateResult {
    const number = new Intl.NumberFormat(this._language, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });
    const temperature = (value: number | null) =>
      value === null ? this._t("temp.unknown") : `${number.format(value)} °C`;
    const reach =
      state === null
        ? nothing
        : html`<span class="reach ${state.linkUp ? (state.reachable ? "ok" : "silent") : "link"}">
            ${
              state.linkUp
                ? state.reachable
                  ? this._t("reach.ok")
                  : this._t("reach.silent")
                : this._t("reach.link")
            }
          </span>`;
    return html`<div class="header">
      <div>
        <h2 class="title">${this._title()}</h2>
        <div class="subtitle">${this._t("card.title")}</div>
      </div>
      ${
        state === null
          ? nothing
          : html`<div class="facts">
              <span class="temp"
                ><span class="temp-label">${this._t("temp.day")}</span
                >${temperature(state.dayTemperature)}</span
              >
              <span class="temp"
                ><span class="temp-label">${this._t("temp.night")}</span
                >${temperature(state.nightTemperature)}</span
              >
              ${reach}
              <button class="small" @click=${() => void this._read()}>
                ${this._t("action.readWeek")}
              </button>
            </div>`
      }
    </div>`;
  }

  private _renderBanners(state: ScheduleState): TemplateResult {
    return html`
      ${
        !state.linkUp
          ? html`<div class="banner" role="status">
              <p>${this._t("reach.link")}. ${this._t("reach.linkHint")}</p>
            </div>`
          : !state.reachable
            ? html`<div class="banner" role="status">
                <p>${this._t("reach.silent")}. ${this._t("reach.queueHint")}</p>
              </div>`
            : nothing
      }
      ${
        this._banner === null
          ? nothing
          : html`<div class="banner ${this._banner.kind}" role="alert">
              <p>${this._banner.text}</p>
              <button class="small" @click=${() => (this._banner = null)}>
                ${this._t("action.dismiss")}
              </button>
            </div>`
      }
    `;
  }

  private _renderEmpty(): TemplateResult {
    return html`<div class="empty">
      <p><strong>${this._t("empty.title")}</strong></p>
      <p>${this._readRequested ? this._t("empty.requested") : this._t("empty.body")}</p>
      <div class="actions">
        <button class="primary" ?disabled=${this._busy} @click=${() => void this._read()}>
          ${this._t("action.read")}
        </button>
        <button @click=${() => (this._editEmpty = true)}>${this._t("action.editEmpty")}</button>
      </div>
    </div>`;
  }

  private _renderGrid(state: ScheduleState): TemplateResult {
    const step = this._narrow ? 360 : 180;
    return html`<div class="grid" role="group" aria-label=${this._t("card.title")}>
      ${
        this._narrow
          ? nothing
          : html`<div class="axis-row" aria-hidden="true">
              <span></span>
              <fht-time-axis .limits=${state.limits} .step=${step}></fht-time-axis>
              <span></span>
            </div>`
      }
      ${WEEKDAYS.map((weekday) => this._renderRow(weekday, state, step))}
    </div>`;
  }

  private _renderRow(weekday: Weekday, state: ScheduleState, step: number): TemplateResult {
    const day = state.days[weekday];
    const status = this._status(weekday);
    const unknown = shownPeriods(day) === null && this._draft[weekday] === undefined;
    const pending = day.status === "queued" || day.status === "sending";
    const selected = this._selected === weekday;
    const track = html`<fht-day-track
      .periods=${this._periodsOf(weekday)}
      .limits=${state.limits}
      .labeler=${this._labeler(weekday)}
      .axisStep=${step}
      ?interactive=${!this._narrow}
      ?unknown=${unknown}
      ?pending=${pending}
      track-label=${this._t("aria.track", { day: this._day(weekday) })}
      @periods-change=${(event: CustomEvent<{ periods: Period[] }>) =>
        this._onTrackChange(weekday, event)}
    ></fht-day-track>`;
    const meta = html`<span class="meta">
      <span class="summary">${this._summary(weekday)}</span>${this._chip(status)}
    </span>`;
    if (this._narrow) {
      return html`<button
        class="day-row"
        aria-label=${this._t("aria.row", {
          day: this._day(weekday),
          summary: this._summary(weekday),
          status: this._t(`status.${status}`),
        })}
        @click=${() => (this._selected = weekday)}
      >
        <span class="day-label" aria-hidden="true">${dayShort(this._language, weekday)}</span>
        ${track}${meta}
      </button>`;
    }
    return html`<div class="day-row ${selected ? "selected" : ""}">
      <button
        class="day-label"
        aria-pressed=${selected ? "true" : "false"}
        aria-label=${this._day(weekday)}
        @click=${() => (this._selected = selected ? null : weekday)}
      >
        ${dayShort(this._language, weekday)}
      </button>
      ${track}${meta}
    </div>`;
  }

  private _renderLegend(): TemplateResult {
    return html`<div class="legend" aria-hidden="true">
      <span><i class="swatch"></i>${this._t("legend.heating")}</span>
      <span><i class="swatch night"></i>${this._t("legend.night")}</span>
      <span><i class="swatch pending"></i>${this._t("legend.pending")}</span>
      <span><i class="swatch unknown"></i>${this._t("legend.unknown")}</span>
    </div>`;
  }

  private _renderEditor(weekday: Weekday, state: ScheduleState): TemplateResult {
    const periods = this._periodsOf(weekday);
    const day = state.days[weekday];
    const status = this._status(weekday);
    const dirty = this._isDirty(weekday);
    const drafted = this._draft[weekday] !== undefined;
    const unknown = shownPeriods(day) === null;
    const waiting = day.status === "queued" || day.status === "sending";
    const canAdd = suggestPeriod(periods, state.limits) !== null;
    const resendable =
      !dirty && (day.status === "unconfirmed" || day.status === "error") && day.periods !== null;
    return html`<section
      class="editor"
      aria-label=${this._t("day.editor", { day: this._day(weekday) })}
    >
      <div class="editor-head">
        <h3>${this._day(weekday)}</h3>
        ${this._chip(status)}
        ${
          this._narrow
            ? html`<button class="small" @click=${() => (this._selected = null)}>
                ${this._t("action.back")}
              </button>`
            : nothing
        }
      </div>
      ${
        this._narrow
          ? html`<fht-day-track
              large
              interactive
              axis
              .axisStep=${180}
              .periods=${periods}
              .limits=${state.limits}
              .labeler=${this._labeler(weekday)}
              ?unknown=${unknown && !drafted}
              ?pending=${waiting}
              track-label=${this._t("aria.track", { day: this._day(weekday) })}
              @periods-change=${(event: CustomEvent<{ periods: Period[] }>) =>
                this._onTrackChange(weekday, event)}
            ></fht-day-track>`
          : nothing
      }
      ${unknown ? html`<p class="hint">${this._t("day.unknownHint")}</p>` : nothing}
      ${waiting ? html`<p class="hint">${this._t("day.pendingHint")}</p>` : nothing}
      <div class="periods">
        ${periods.map((period, index) => this._renderFields(weekday, period, index, state))}
      </div>
      <div class="actions">
        <button ?disabled=${!canAdd} @click=${() => this._add(weekday)}>
          ${this._t("action.add")}
        </button>
        ${
          hasTouching(periods)
            ? html`<button @click=${() => this._edit(weekday, mergeTouching(periods))}>
                ${this._t("action.merge")}
              </button>`
            : nothing
        }
        <button ?disabled=${periods.length === 0} @click=${() => this._edit(weekday, [])}>
          ${this._t("action.clear")}
        </button>
        <button ?disabled=${!drafted} @click=${() => this._reset(weekday)}>
          ${this._t("action.reset")}
        </button>
        <button ?disabled=${unknown && !drafted} @click=${() => this._openCopy(weekday)}>
          ${this._t("action.copy")}
        </button>
        ${
          unknown || day.status === "unconfirmed"
            ? html`<button @click=${() => void this._read([weekday])}>
                ${this._t("action.readDay")}
              </button>`
            : nothing
        }
        ${
          resendable
            ? html`<button @click=${() => void this._resend(weekday)}>
                ${this._t("action.resend")}
              </button>`
            : nothing
        }
      </div>
    </section>`;
  }

  private _renderFields(
    weekday: Weekday,
    period: Period,
    index: number,
    state: ScheduleState,
  ): TemplateResult {
    const n = index + 1;
    const day = this._day(weekday);
    const field = (edge: "start" | "end") => {
      const key = `${weekday}-${index}-${edge}`;
      const error = this._fieldErrors[key];
      const value = edge === "start" ? period.start : period.end;
      const step = state.limits.stepMinutes;
      const move = (delta: number) => {
        const periods = this._periodsOf(weekday);
        this._edit(
          weekday,
          edge === "start"
            ? resizeStart(periods, index, value + delta, state.limits)
            : resizeEnd(periods, index, value + delta, state.limits),
        );
      };
      return html`<div class="field">
        <span class="field-label">${this._t(`field.${edge}`)}</span>
        <div class="stepper">
          <button
            aria-label=${this._t(edge === "start" ? "aria.startEarlier" : "aria.endEarlier", { day, n })}
            @click=${() => move(-step)}
          >
            −
          </button>
          <input
            type="text"
            inputmode="numeric"
            autocomplete="off"
            aria-label=${this._t(edge === "start" ? "aria.startField" : "aria.endField", { day, n })}
            aria-invalid=${error === undefined ? "false" : "true"}
            aria-describedby=${error === undefined ? nothing : `error-${key}`}
            .value=${live(error?.text ?? formatTime(value))}
            @change=${(event: Event) =>
              this._onField(weekday, index, edge, (event.target as HTMLInputElement).value)}
          />
          <button
            aria-label=${this._t(edge === "start" ? "aria.startLater" : "aria.endLater", { day, n })}
            @click=${() => move(step)}
          >
            +
          </button>
        </div>
        ${
          error === undefined
            ? nothing
            : html`<p class="field-error" id="error-${key}" role="alert">${error.message}</p>`
        }
      </div>`;
    };
    return html`<fieldset>
      <legend>${this._t("field.period", { n })}</legend>
      <div class="fields">
        ${field("start")}${field("end")}
        <button
          class="danger"
          aria-label=${this._t("aria.remove", { day, n })}
          @click=${() => this._edit(weekday, removePeriod(this._periodsOf(weekday), index))}
        >
          ${this._t("action.remove")}
        </button>
      </div>
    </fieldset>`;
  }

  private _onField(weekday: Weekday, index: number, edge: "start" | "end", text: string): void {
    const state = this._state as ScheduleState;
    const key = `${weekday}-${index}-${edge}`;
    const without = { ...this._fieldErrors };
    delete without[key];
    const minutes = parseTime(text, state.limits.dayEnd);
    const periods = this._periodsOf(weekday);
    const current = periods[index];
    if (current === undefined) {
      return;
    }
    const candidate = periods.map((period, position) =>
      position === index ? { ...period, [edge]: minutes ?? Number.NaN } : { ...period },
    );
    const problem =
      minutes === null
        ? ({ key: "schedule_time_invalid", params: { value: text } } as ValidationError)
        : validateDay(candidate, state.limits);
    if (problem !== null) {
      this._fieldErrors = {
        ...without,
        [key]: { text, message: this._validation(problem, weekday) },
      };
      return;
    }
    this._fieldErrors = without;
    this._edit(weekday, candidate);
  }

  private _add(weekday: Weekday): void {
    const state = this._state as ScheduleState;
    const next = suggestPeriod(this._periodsOf(weekday), state.limits);
    if (next !== null) {
      this._edit(weekday, next);
    }
  }

  private _reset(weekday: Weekday): void {
    const next = { ...this._draft };
    delete next[weekday];
    this._draft = next;
    this._clearFieldErrors(weekday);
  }

  private _renderFooter(state: ScheduleState): TemplateResult {
    const dirty = dirtyDays(this._draft, state.days);
    const count = dirty.length;
    return html`<div class="footer">
      <div class="footer-text">
        <span>${count === 0 ? this._t("footer.clean") : this._t("footer.changed", { count })}</span>
        <span class="hint">${this._t("footer.hint")}</span>
      </div>
      <div class="actions">
        <button ?disabled=${count === 0 || this._busy} @click=${() => this._discard()}>
          ${this._t("action.discard")}
        </button>
        <button class="primary" ?disabled=${count === 0 || this._busy} @click=${() => this._save()}>
          ${count === 0 ? this._t("action.save") : this._t("action.saveCount", { count })}
        </button>
      </div>
    </div>`;
  }

  private _discard(): void {
    this._draft = {};
    this._fieldErrors = {};
    this._banner = null;
    this._announce = this._t("announce.discarded");
  }

  private _save(): void {
    const state = this._state as ScheduleState;
    const dirty = dirtyDays(this._draft, state.days);
    for (const weekday of dirty) {
      const problem = validateDay(this._draft[weekday] ?? [], state.limits);
      if (problem !== null) {
        this._banner = { kind: "error", text: this._validation(problem, weekday) };
        return;
      }
    }
    const unread = dirty.filter((weekday) => shownPeriods(state.days[weekday]) === null);
    if (unread.length > 0) {
      this._dialog = { kind: "confirm", days: unread };
      return;
    }
    void this._commit(dirty);
  }

  private async _commit(weekdays: Weekday[]): Promise<void> {
    await this._send(weekdays, this._draft);
  }

  private async _resend(weekday: Weekday): Promise<void> {
    const state = this._state as ScheduleState;
    await this._send([weekday], { [weekday]: shownPeriods(state.days[weekday]) ?? [] });
  }

  private async _send(weekdays: Weekday[], source: Draft): Promise<void> {
    const hass = this._hass as Hass;
    const entity = (this._config as CardConfig).entity;
    this._busy = true;
    this._banner = null;
    try {
      const result = await setSchedule(hass, entity, toWire(source, weekdays));
      const next = { ...this._draft };
      for (const weekday of [...result.sent, ...result.unchanged]) {
        delete next[weekday];
      }
      this._draft = next;
      const names = (days: Weekday[]) => days.map((day) => this._day(day)).join(", ");
      const parts: string[] = [];
      if (result.sent.length > 0) {
        parts.push(this._t("announce.sent", { days: names(result.sent) }));
      }
      if (result.unchanged.length > 0) {
        parts.push(this._t("announce.unchanged", { days: names(result.unchanged) }));
      }
      this._announce = parts.join(" ");
    } catch (reason) {
      this._banner = {
        kind: "error",
        text: this._t("error.save", { message: describeError(this._language, asApiError(reason)) }),
      };
    } finally {
      this._busy = false;
    }
  }

  private async _read(weekdays?: Weekday[]): Promise<void> {
    const hass = this._hass as Hass;
    const entity = (this._config as CardConfig).entity;
    this._busy = true;
    this._banner = null;
    try {
      await refreshSchedule(hass, entity, weekdays);
      this._readRequested = true;
      this._announce = this._t("announce.read");
    } catch (reason) {
      this._banner = {
        kind: "error",
        text: this._t("error.read", { message: describeError(this._language, asApiError(reason)) }),
      };
    } finally {
      this._busy = false;
    }
  }

  private _openCopy(source: Weekday): void {
    this._copyTo = copyTargets("weekdays", source);
    this._dialog = { kind: "copy", source };
  }

  private _closeDialog(): void {
    this.renderRoot.querySelector("dialog")?.close();
  }

  private _applyCopy(source: Weekday): void {
    const periods = this._periodsOf(source);
    for (const weekday of this._copyTo) {
      this._edit(
        weekday,
        periods.map((period) => ({ ...period })),
      );
    }
    this._announce = this._t("announce.copied", {
      days: this._copyTo.map((day) => this._day(day)).join(", "),
    });
    this._closeDialog();
  }

  private _renderDialog(): TemplateResult | typeof nothing {
    const dialog = this._dialog;
    if (dialog === null) {
      return nothing;
    }
    if (dialog.kind === "copy") {
      return this._renderCopyDialog(dialog.source);
    }
    return html`<dialog
      role="alertdialog"
      aria-labelledby="dialog-title"
      @close=${() => (this._dialog = null)}
    >
      <h3 id="dialog-title">${this._t("confirm.title")}</h3>
      <p>
        ${this._t("confirm.body", {
          days: dialog.days.map((day) => this._day(day)).join(", "),
        })}
      </p>
      <div class="dialog-actions">
        <button @click=${() => this._closeDialog()}>${this._t("action.cancel")}</button>
        <button
          class="primary"
          @click=${() => {
            this._closeDialog();
            void this._commit(dirtyDays(this._draft, (this._state as ScheduleState).days));
          }}
        >
          ${this._t("action.overwrite")}
        </button>
      </div>
    </dialog>`;
  }

  private _renderCopyDialog(source: Weekday): TemplateResult {
    const preset = (name: CopyPreset) =>
      html`<button class="small" @click=${() => (this._copyTo = copyTargets(name, source))}>
        ${this._t(`preset.${name}`)}
      </button>`;
    return html`<dialog aria-labelledby="dialog-title" @close=${() => (this._dialog = null)}>
      <h3 id="dialog-title">${this._t("copy.title", { day: this._day(source) })}</h3>
      <p class="hint">${this._t("copy.body")}</p>
      <div class="presets">${preset("weekdays")}${preset("weekend")}${preset("all")}</div>
      <div class="checks">
        ${WEEKDAYS.filter((weekday) => weekday !== source).map(
          (weekday) =>
            html`<label>
              <input
                type="checkbox"
                .checked=${this._copyTo.includes(weekday)}
                @change=${(event: Event) => {
                  const checked = (event.target as HTMLInputElement).checked;
                  this._copyTo = checked
                    ? WEEKDAYS.filter((day) => day === weekday || this._copyTo.includes(day))
                    : this._copyTo.filter((day) => day !== weekday);
                }}
              />
              ${this._day(weekday)}
            </label>`,
        )}
      </div>
      <div class="dialog-actions">
        <button @click=${() => this._closeDialog()}>${this._t("action.cancel")}</button>
        <button
          class="primary"
          ?disabled=${this._copyTo.length === 0}
          @click=${() => this._applyCopy(source)}
        >
          ${this._t("action.copyApply")}
        </button>
      </div>
    </dialog>`;
  }
}
