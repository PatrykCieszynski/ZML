const ENABLED_VALUES = new Set(["1", "true", "yes", "on"]);

export function isUiMockMode(env: Record<string, string | undefined> = process.env): boolean {
    const value = env.ZML_UI_MOCKS?.trim().toLowerCase();
    return value !== undefined && ENABLED_VALUES.has(value);
}

export function readMockIntervalMs(
    key: string,
    defaultValue: number,
    minValue: number,
    env: Record<string, string | undefined> = process.env,
): number {
    const raw = env[key];
    if (!raw) return defaultValue;

    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) return defaultValue;

    return Math.max(minValue, Math.floor(parsed));
}

export function readMockNumber(
    key: string,
    defaultValue: number,
    env: Record<string, string | undefined> = process.env,
): number {
    const raw = env[key];
    if (!raw) return defaultValue;

    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : defaultValue;
}
