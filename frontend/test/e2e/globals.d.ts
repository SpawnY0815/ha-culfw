export {};

declare global {
  interface Window {
    mountCard(options?: Record<string, unknown>): Promise<void>;
    __server: {
      calls: Record<string, unknown>[];
      subscriptions: number;
      failNext: unknown;
      failSubscribe: unknown;
      state: { days: Record<string, Record<string, unknown>> };
      push(patch: Record<string, unknown>): void;
      pushRaw(event: unknown): void;
      close(): void;
    };
    __hass: Record<string, unknown>;
    __card: HTMLElement & { hass: unknown; setConfig(config: unknown): void };
  }
}
