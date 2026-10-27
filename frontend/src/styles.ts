import { css } from "lit";

// Only variables that the Home Assistant developer documentation lists are used:
// the theme variables of the themes guide, the card variables, the spacing,
// radius and font tokens and the focus color.
export const cardStyles = css`
  :host {
    display: block;
  }
  ha-card {
    display: block;
    overflow: hidden;
  }
  .root {
    padding: var(--ha-space-4, 16px);
    display: grid;
    gap: var(--ha-space-3, 12px);
    color: var(--primary-text-color);
    font-size: var(--ha-font-size-m, 1rem);
  }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--ha-space-2, 8px) var(--ha-space-4, 16px);
  }
  .title {
    margin: 0;
    font-size: var(--ha-card-header-font-size, 1.25rem);
    font-weight: var(--ha-font-weight-medium, 500);
    color: var(--ha-card-header-color, var(--primary-text-color));
  }
  .subtitle {
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 0.875rem);
  }
  .facts {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
  }
  .temp {
    font-variant-numeric: tabular-nums;
  }
  .temp-label {
    color: var(--secondary-text-color);
    margin-inline-end: 4px;
  }
  .reach {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--ha-font-size-s, 0.875rem);
  }
  .reach::before {
    content: "";
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--success-color);
  }
  .reach.silent::before {
    background: var(--warning-color);
  }
  .reach.link::before {
    background: var(--error-color);
  }
  .banner {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--ha-space-2, 8px);
    padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
    border-radius: var(--ha-border-radius-md, 8px);
    border: 1px solid var(--warning-color);
    border-inline-start-width: 6px;
  }
  .banner.error {
    border-color: var(--error-color);
  }
  .banner.info {
    border-color: var(--info-color, var(--primary-color));
  }
  .banner p {
    margin: 0;
  }
  button {
    font: inherit;
    color: var(--primary-text-color);
    background: transparent;
    border: 1px solid var(--divider-color);
    border-radius: var(--ha-border-radius-md, 8px);
    padding: 0 var(--ha-space-3, 12px);
    min-height: 40px;
    cursor: pointer;
  }
  button.primary {
    background: var(--primary-color);
    border-color: var(--primary-color);
    color: var(--text-primary-color, #fff);
  }
  button.danger {
    border-color: var(--error-color);
  }
  button.small {
    min-height: 32px;
    padding: 0 var(--ha-space-2, 8px);
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  button:focus-visible,
  input:focus-visible {
    outline: 2px solid var(--ha-color-focus, var(--primary-text-color));
    outline-offset: 2px;
  }
  .axis-row,
  .day-row {
    display: grid;
    grid-template-columns: 3.2em minmax(0, 1fr) 17.5em;
    align-items: center;
    gap: var(--ha-space-1, 4px) var(--ha-space-2, 8px);
  }
  .grid {
    display: grid;
    gap: var(--ha-space-2, 8px);
  }
  .day-row {
    padding: 2px 0;
    border-radius: var(--ha-border-radius-md, 8px);
  }
  .day-row.selected {
    background: var(--secondary-background-color);
  }
  .day-label {
    text-align: start;
    font-weight: var(--ha-font-weight-medium, 500);
    min-height: 32px;
    padding: 0 4px;
    border: none;
    background: transparent;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ha-space-2, 8px);
    justify-content: flex-end;
  }
  .summary {
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 0.875rem);
    font-variant-numeric: tabular-nums;
  }
  .narrow .day-row {
    grid-template-columns: 2.6em minmax(0, 1fr);
    width: 100%;
    text-align: start;
    background: transparent;
    border: 1px solid var(--divider-color);
    padding: var(--ha-space-2, 8px);
    min-height: 0;
  }
  .narrow .meta {
    grid-column: 2;
    justify-content: space-between;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 8px;
    border-radius: 999px;
    border: 1px solid currentcolor;
    font-size: var(--ha-font-size-s, 0.875rem);
    white-space: nowrap;
    color: var(--secondary-text-color);
  }
  .chip-saved {
    color: var(--success-color);
  }
  .chip-queued,
  .chip-sending,
  .chip-edited {
    color: var(--primary-color);
  }
  .chip-unconfirmed {
    color: var(--warning-color);
  }
  .chip-error {
    color: var(--error-color);
  }
  .chip-text {
    color: var(--primary-text-color);
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ha-space-2, 8px) var(--ha-space-4, 16px);
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 0.875rem);
  }
  .legend span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .swatch {
    width: 18px;
    height: 10px;
    border-radius: 3px;
    border: 2px solid var(--primary-color);
    background: var(--primary-color);
  }
  .swatch.night {
    background: var(--secondary-background-color);
    border-color: var(--divider-color);
  }
  .swatch.unknown {
    background: repeating-linear-gradient(135deg, transparent 0 3px, var(--divider-color) 3px 5px);
    border-color: var(--divider-color);
  }
  .swatch.pending {
    background: repeating-linear-gradient(
      135deg,
      transparent 0 3px,
      var(--card-background-color, #fff) 3px 5px
    );
    background-color: var(--primary-color);
  }
  .editor {
    display: grid;
    gap: var(--ha-space-3, 12px);
    padding: var(--ha-space-3, 12px);
    border: 1px solid var(--divider-color);
    border-radius: var(--ha-border-radius-lg, 12px);
  }
  .editor-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ha-space-2, 8px);
    justify-content: space-between;
  }
  .editor-head h3 {
    margin: 0;
    font-size: var(--ha-font-size-l, 1.125rem);
    font-weight: var(--ha-font-weight-medium, 500);
  }
  .hint {
    margin: 0;
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 0.875rem);
  }
  .periods {
    display: grid;
    gap: var(--ha-space-3, 12px);
  }
  fieldset {
    margin: 0;
    padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
    border: 1px solid var(--divider-color);
    border-radius: var(--ha-border-radius-md, 8px);
    display: grid;
    gap: var(--ha-space-2, 8px);
  }
  legend {
    padding: 0 4px;
    color: var(--secondary-text-color);
  }
  .fields {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ha-space-3, 12px) var(--ha-space-4, 16px);
    align-items: flex-end;
  }
  .field {
    display: grid;
    gap: 2px;
  }
  .field-label {
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 0.875rem);
  }
  .stepper {
    display: flex;
    gap: 4px;
  }
  .stepper button {
    min-width: 44px;
    padding: 0;
  }
  input[type="text"] {
    font: inherit;
    width: 5.5em;
    min-height: 40px;
    text-align: center;
    box-sizing: border-box;
    color: var(--primary-text-color);
    background: var(--card-background-color);
    border: 1px solid var(--divider-color);
    border-radius: var(--ha-border-radius-md, 8px);
    font-variant-numeric: tabular-nums;
  }
  input[aria-invalid="true"] {
    border-color: var(--error-color);
  }
  .field-error {
    color: var(--error-color);
    font-size: var(--ha-font-size-s, 0.875rem);
    margin: 0;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ha-space-2, 8px);
  }
  .footer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--ha-space-2, 8px) var(--ha-space-4, 16px);
    padding-top: var(--ha-space-3, 12px);
    border-top: 1px solid var(--divider-color);
  }
  .footer-text {
    display: grid;
    gap: 2px;
  }
  .empty {
    display: grid;
    gap: var(--ha-space-3, 12px);
    justify-items: start;
    padding: var(--ha-space-4, 16px) 0;
  }
  .empty p {
    margin: 0;
  }
  dialog {
    max-width: min(28rem, calc(100vw - 32px));
    padding: var(--ha-space-4, 16px);
    color: var(--primary-text-color);
    background: var(--card-background-color);
    border: 1px solid var(--divider-color);
    border-radius: var(--ha-border-radius-lg, 12px);
  }
  dialog::backdrop {
    background: rgba(0, 0, 0, 0.5);
  }
  dialog h3 {
    margin: 0 0 var(--ha-space-2, 8px);
    font-size: var(--ha-font-size-l, 1.125rem);
  }
  .checks {
    display: grid;
    gap: var(--ha-space-1, 4px);
    margin: var(--ha-space-3, 12px) 0;
  }
  .checks label {
    display: flex;
    align-items: center;
    gap: var(--ha-space-2, 8px);
    min-height: 40px;
  }
  .checks input {
    width: 20px;
    height: 20px;
  }
  .presets {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ha-space-2, 8px);
  }
  .dialog-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--ha-space-2, 8px);
    margin-top: var(--ha-space-3, 12px);
  }
`;
