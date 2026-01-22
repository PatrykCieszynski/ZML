export const WINDOW_TYPES = ["main", "map", "hud"] as const;

export type WindowType = (typeof WINDOW_TYPES)[number];

export function isWindowType(x: unknown): x is WindowType {
    return typeof x === "string" && (WINDOW_TYPES as readonly string[]).includes(x);
}

// Optional: stricter helper if you prefer throwing early in main process.
export function assertWindowType(x: unknown, ctx: string = "windowType"): asserts x is WindowType {
    if (!isWindowType(x)) {
        throw new Error(`Invalid ${ctx}: ${String(x)}`);
    }
}
