import { LitElement, css, html, nothing } from "lit";
import type { PropertyValues } from "lit";
import {
  addPeriodAt,
  clamp,
  formatTime,
  movePeriod,
  removePeriod,
  resizeEnd,
  resizeStart,
} from "./model";
import type { Limits, Period } from "./types";

type DragKind = "start" | "end" | "move" | "create";

interface Drag {
  kind: DragKind;
  index: number;
  pointerId: number;
  startX: number;
  origin: Period[];
  /** Distance from the pointer to the edge or start that is dragged, in minutes. */
  grab: number;
  moved: boolean;
}

export type TrackLabel = (kind: "start" | "end" | "move", index: number) => string;

const KEY_STEP_HOURS = 60;
// A touch that moves less than this is a tap and not the start of a drag.
const DRAG_THRESHOLD_PX = 6;

/** The hour labels above one or more tracks. */
export class FhtTimeAxis extends LitElement {
  static override properties = {
    limits: { attribute: false },
    step: { type: Number },
  };

  declare limits: Limits;
  declare step: number;

  constructor() {
    super();
    this.limits = { stepMinutes: 10, maxPeriods: 2, dayEnd: 1440 };
    this.step = 360;
  }

  static override styles = css`
    :host {
      display: block;
    }
    .axis {
      position: relative;
      height: 1.2em;
      margin-block-end: 2px;
      font-size: var(--ha-font-size-xs, 0.75rem);
      color: var(--secondary-text-color);
      direction: ltr;
    }
    .tick {
      position: absolute;
      transform: translateX(-50%);
      white-space: nowrap;
    }
    .tick:first-child {
      transform: none;
    }
    .tick:last-child {
      transform: translateX(-100%);
    }
  `;

  protected override render() {
    const ticks: number[] = [];
    for (let minute = 0; minute <= this.limits.dayEnd; minute += this.step) {
      ticks.push(minute);
    }
    return html`<div class="axis" aria-hidden="true">
      ${ticks.map(
        (minute) =>
          html`<span class="tick" style="left:${(minute / this.limits.dayEnd) * 100}%"
            >${String(minute / 60).padStart(2, "0")}</span
          >`,
      )}
    </div>`;
  }
}

/**
 * The 24 hour track of one day with its heating periods.
 *
 * Every period is a bar with a handle on each end. The handles are sliders that a
 * keyboard can move in steps, and a drag on the bar moves the whole period. A tap
 * on free space adds a period. The track lets a vertical swipe scroll the page.
 */
export class FhtDayTrack extends LitElement {
  static override properties = {
    periods: { attribute: false },
    limits: { attribute: false },
    labeler: { attribute: false },
    interactive: { type: Boolean },
    large: { type: Boolean },
    unknown: { type: Boolean },
    pending: { type: Boolean },
    axis: { type: Boolean },
    axisStep: { type: Number, attribute: "axis-step" },
    trackLabel: { type: String, attribute: "track-label" },
    _bubble: { state: true },
  };

  declare periods: Period[];
  declare limits: Limits;
  declare labeler: TrackLabel;
  declare interactive: boolean;
  declare large: boolean;
  declare unknown: boolean;
  declare pending: boolean;
  declare axis: boolean;
  declare axisStep: number;
  declare trackLabel: string;
  declare _bubble: { minute: number } | null;

  private _drag: Drag | null = null;

  constructor() {
    super();
    this.periods = [];
    this.limits = { stepMinutes: 10, maxPeriods: 2, dayEnd: 1440 };
    this.labeler = (kind, index) => `${kind} ${index + 1}`;
    this.interactive = false;
    this.large = false;
    this.unknown = false;
    this.pending = false;
    this.axis = false;
    this.axisStep = 360;
    this.trackLabel = "";
    this._bubble = null;
  }

  static override styles = css`
    :host {
      display: block;
      --handle-in: 6px;
      --handle-out: 10px;
      --track-height: 28px;
      touch-action: pan-y;
    }
    :host([large]) {
      --handle-in: 8px;
      --handle-out: 36px;
      --track-height: 60px;
    }
    .track {
      position: relative;
      height: var(--track-height);
      direction: ltr;
      border-radius: var(--ha-border-radius-sm, 4px);
      background: var(--secondary-background-color, rgba(127, 127, 127, 0.15));
      outline: 1px solid var(--divider-color, rgba(127, 127, 127, 0.4));
      outline-offset: -1px;
      touch-action: pan-y;
      user-select: none;
      -webkit-user-select: none;
    }
    .track.unknown {
      background-image: repeating-linear-gradient(
        135deg,
        transparent 0 6px,
        var(--divider-color, rgba(127, 127, 127, 0.4)) 6px 8px
      );
    }
    .unknown-mark {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      font-size: var(--ha-font-size-s, 0.875rem);
      color: var(--secondary-text-color);
      pointer-events: none;
    }
    .gridline {
      position: absolute;
      top: 0;
      bottom: 0;
      width: 1px;
      background: var(--divider-color, rgba(127, 127, 127, 0.4));
      opacity: 0.5;
      pointer-events: none;
    }
    .bar:focus-visible {
      outline: 2px solid var(--ha-color-focus, var(--primary-text-color));
      outline-offset: 2px;
    }
    .bar {
      position: absolute;
      top: 3px;
      bottom: 3px;
      min-width: 3px;
      box-sizing: border-box;
      border-radius: var(--ha-border-radius-sm, 4px);
      background: var(--primary-color);
      border: 2px solid var(--primary-color);
      touch-action: pan-y;
    }
    .interactive .bar {
      cursor: grab;
    }
    .pending .bar {
      background-image: repeating-linear-gradient(
        135deg,
        transparent 0 5px,
        var(--card-background-color, #fff) 5px 7px
      );
    }
    .handle {
      position: absolute;
      top: 0;
      bottom: 0;
      width: calc(var(--handle-in) + var(--handle-out));
      display: flex;
      align-items: center;
      touch-action: none;
      cursor: ew-resize;
      z-index: 2;
    }
    /* The hit area reaches mostly outside of the bar, so that the middle of a
       short bar stays free for moving it with a finger. */
    .handle.start {
      transform: translateX(calc(-1 * var(--handle-out)));
    }
    .handle.end {
      transform: translateX(calc(-1 * var(--handle-in)));
    }
    .handle::before {
      content: "";
      width: 6px;
      height: 70%;
      border-radius: 3px;
      background: var(--text-primary-color, #fff);
      border: 1px solid var(--primary-color);
      box-sizing: border-box;
    }
    .handle.start::before {
      margin-inline-start: calc(var(--handle-out) - 3px);
    }
    .handle.end::before {
      margin-inline-start: calc(var(--handle-in) - 3px);
    }
    .handle:focus-visible {
      outline: 2px solid var(--ha-color-focus, var(--primary-text-color));
      outline-offset: 1px;
    }
    .handle:focus-visible::before,
    .handle.active::before {
      background: var(--primary-text-color);
    }
    .bubble {
      position: absolute;
      bottom: calc(100% + 6px);
      transform: translateX(-50%);
      padding: 2px 8px;
      border-radius: var(--ha-border-radius-md, 8px);
      background: var(--primary-text-color);
      color: var(--card-background-color, #fff);
      font-size: var(--ha-font-size-m, 1rem);
      font-variant-numeric: tabular-nums;
      pointer-events: none;
      white-space: nowrap;
      z-index: 3;
    }
    :host([large]) .bubble {
      bottom: calc(100% + 28px);
      font-size: 1.25rem;
      padding: 4px 12px;
    }
  `;

  protected override updated(changed: PropertyValues<this>): void {
    if (changed.has("large")) {
      this.toggleAttribute("large", this.large);
    }
  }

  private get _track(): HTMLElement {
    return this.renderRoot.querySelector(".track") as HTMLElement;
  }

  private _minuteAt(clientX: number): number {
    const rect = this._track.getBoundingClientRect();
    return ((clientX - rect.left) / rect.width) * this.limits.dayEnd;
  }

  private _percent(minute: number): string {
    return `${(minute / this.limits.dayEnd) * 100}%`;
  }

  private _emit(periods: Period[]): void {
    this.dispatchEvent(
      new CustomEvent<{ periods: Period[] }>("periods-change", {
        detail: { periods },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _begin(event: PointerEvent, kind: DragKind, index: number, grab: number): void {
    if (!this.interactive || (event.pointerType === "mouse" && event.button !== 0)) {
      return;
    }
    this._drag = {
      kind,
      index,
      pointerId: event.pointerId,
      startX: event.clientX,
      origin: this.periods.map((period) => ({ ...period })),
      grab,
      moved: false,
    };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  private _onHandleDown(event: PointerEvent, index: number, edge: "start" | "end"): void {
    event.stopPropagation();
    const period = this.periods[index] as Period;
    const edgeMinute = edge === "start" ? period.start : period.end;
    this._begin(event, edge, index, edgeMinute - this._minuteAt(event.clientX));
    if (this._drag !== null) {
      this._drag.moved = true;
      this._bubble = { minute: edgeMinute };
    }
  }

  private _onBarDown(event: PointerEvent, index: number): void {
    event.stopPropagation();
    const period = this.periods[index] as Period;
    this._begin(event, "move", index, period.start - this._minuteAt(event.clientX));
  }

  private _onTrackDown(event: PointerEvent): void {
    this._begin(event, "create", -1, 0);
  }

  private _onMove(event: PointerEvent): void {
    const drag = this._drag;
    if (drag === null || event.pointerId !== drag.pointerId) {
      return;
    }
    if (!drag.moved) {
      if (Math.abs(event.clientX - drag.startX) < DRAG_THRESHOLD_PX) {
        return;
      }
      drag.moved = true;
    }
    if (drag.kind === "create") {
      return;
    }
    const minute = this._minuteAt(event.clientX) + drag.grab;
    const limits = this.limits;
    let next: Period[];
    if (drag.kind === "start") {
      next = resizeStart(drag.origin, drag.index, minute, limits);
    } else if (drag.kind === "end") {
      next = resizeEnd(drag.origin, drag.index, minute, limits);
    } else {
      next = movePeriod(drag.origin, drag.index, minute, limits);
    }
    const period = next[drag.index] as Period;
    this._bubble = { minute: drag.kind === "end" ? period.end : period.start };
    if (JSON.stringify(next) !== JSON.stringify(this.periods)) {
      this._emit(next);
    }
  }

  private _onUp(event: PointerEvent): void {
    const drag = this._drag;
    if (drag === null || event.pointerId !== drag.pointerId) {
      return;
    }
    this._drag = null;
    this._bubble = null;
    if (drag.kind === "create" && !drag.moved) {
      const added = addPeriodAt(this.periods, this._minuteAt(event.clientX), this.limits);
      if (added !== null) {
        this._emit(added);
      }
    }
  }

  private _onCancel(event: PointerEvent): void {
    const drag = this._drag;
    if (drag === null || event.pointerId !== drag.pointerId) {
      return;
    }
    this._drag = null;
    this._bubble = null;
    if (drag.moved && drag.kind !== "create") {
      this._emit(drag.origin);
    }
  }

  private _onKey(event: KeyboardEvent, index: number, edge: "start" | "end" | "move"): void {
    const period = this.periods[index];
    if (period === undefined) {
      return;
    }
    const limits = this.limits;
    const edgeMinute = edge === "end" ? period.end : period.start;
    const big = event.shiftKey ? KEY_STEP_HOURS : limits.stepMinutes;
    let target: number;
    switch (event.key) {
      case "ArrowLeft":
      case "ArrowDown":
        target = edgeMinute - big;
        break;
      case "ArrowRight":
      case "ArrowUp":
        target = edgeMinute + big;
        break;
      case "Home":
        target = 0;
        break;
      case "End":
        target = limits.dayEnd;
        break;
      case "Delete":
      case "Backspace":
        event.preventDefault();
        this._emit(removePeriod(this.periods, index));
        setTimeout(() => this._focusAny(), 0);
        return;
      default:
        return;
    }
    event.preventDefault();
    let next: Period[];
    if (edge === "start") {
      next = resizeStart(this.periods, index, target, limits);
    } else if (edge === "end") {
      next = resizeEnd(this.periods, index, target, limits);
    } else {
      next = movePeriod(this.periods, index, target, limits);
    }
    if (JSON.stringify(next) !== JSON.stringify(this.periods)) {
      this._emit(next);
    }
  }

  private _focusAny(): void {
    const target = this.renderRoot.querySelector<HTMLElement>(".handle") ?? this._track;
    target.focus();
  }

  protected override render() {
    const editable = this.interactive;
    return html`
      ${
        this.axis
          ? html`<fht-time-axis .limits=${this.limits} .step=${this.axisStep}></fht-time-axis>`
          : nothing
      }
      <div
        class="track ${editable ? "interactive" : ""} ${this.unknown ? "unknown" : ""} ${this.pending ? "pending" : ""}"
        tabindex=${editable && this.periods.length === 0 ? "-1" : nothing}
        role=${editable ? "group" : nothing}
        aria-label=${editable ? this.trackLabel : nothing}
        aria-hidden=${editable ? nothing : "true"}
        @pointerdown=${(event: PointerEvent) => this._onTrackDown(event)}
        @pointermove=${(event: PointerEvent) => this._onMove(event)}
        @pointerup=${(event: PointerEvent) => this._onUp(event)}
        @pointercancel=${(event: PointerEvent) => this._onCancel(event)}
      >
        ${this._gridlines()}
        ${
          this.unknown && this.periods.length === 0
            ? html`<span class="unknown-mark">?</span>`
            : nothing
        }
        ${this.periods.map((period, index) => this._renderBar(period, index, editable))}
        ${
          this._bubble === null
            ? nothing
            : html`<span
                class="bubble"
                style="left:${this._percent(clamp(this._bubble.minute, 0, this.limits.dayEnd))}"
                >${formatTime(this._bubble.minute)}</span
              >`
        }
      </div>
    `;
  }

  private _gridlines() {
    const lines: number[] = [];
    for (let minute = this.axisStep; minute < this.limits.dayEnd; minute += this.axisStep) {
      lines.push(minute);
    }
    return lines.map(
      (minute) => html`<span class="gridline" style="left:${this._percent(minute)}"></span>`,
    );
  }

  private _renderBar(period: Period, index: number, editable: boolean) {
    const { limits } = this;
    const previous = this.periods[index - 1]?.end ?? 0;
    const next = this.periods[index + 1]?.start ?? limits.dayEnd;
    const length = period.end - period.start;
    // The bar is a control of its own, not only a drawing: a browser lets a finger
    // that lands on a bar pick the control nearest to it, and without a control here
    // every touch near a handle would grab the handle.
    return html`
      <div
        class="bar"
        style="left:${this._percent(period.start)};width:${this._percent(length)}"
        role=${editable ? "slider" : nothing}
        tabindex=${editable ? "0" : nothing}
        aria-label=${editable ? this.labeler("move", index) : nothing}
        aria-orientation=${editable ? "horizontal" : nothing}
        aria-valuemin=${editable ? previous : nothing}
        aria-valuemax=${editable ? next - length : nothing}
        aria-valuenow=${editable ? period.start : nothing}
        aria-valuetext=${
          editable ? `${formatTime(period.start)}–${formatTime(period.end)}` : nothing
        }
        @pointerdown=${(event: PointerEvent) => this._onBarDown(event, index)}
        @keydown=${(event: KeyboardEvent) => this._onKey(event, index, "move")}
      ></div>
      ${
        editable
          ? html`${this._renderHandle(period, index, "start", this.labeler)}${this._renderHandle(
              period,
              index,
              "end",
              this.labeler,
            )}`
          : nothing
      }
    `;
  }

  private _renderHandle(period: Period, index: number, edge: "start" | "end", label: TrackLabel) {
    const value = edge === "start" ? period.start : period.end;
    const { limits } = this;
    const previous = this.periods[index - 1]?.end ?? 0;
    const next = this.periods[index + 1]?.start ?? limits.dayEnd;
    const min = edge === "start" ? previous : period.start + limits.stepMinutes;
    const max = edge === "start" ? period.end - limits.stepMinutes : next;
    const side = `left:${this._percent(value)}`;
    return html`<div
      class="handle ${edge} ${this._drag?.index === index && this._drag.kind === edge ? "active" : ""}"
      role="slider"
      tabindex="0"
      style=${side}
      aria-label=${label(edge, index)}
      aria-orientation="horizontal"
      aria-valuemin=${min}
      aria-valuemax=${max}
      aria-valuenow=${value}
      aria-valuetext=${formatTime(value)}
      @pointerdown=${(event: PointerEvent) => this._onHandleDown(event, index, edge)}
      @keydown=${(event: KeyboardEvent) => this._onKey(event, index, edge)}
    ></div>`;
  }
}

if (!customElements.get("fht-time-axis")) {
  customElements.define("fht-time-axis", FhtTimeAxis);
}
if (!customElements.get("fht-day-track")) {
  customElements.define("fht-day-track", FhtDayTrack);
}
