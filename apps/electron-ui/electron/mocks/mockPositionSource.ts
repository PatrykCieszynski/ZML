import { MAP_CONFIG, type OcrPositionEvent } from "@zml/shared";

import type { PositionSourceOptions, StopPositionSource } from "../agent/positionSource.ts";
import { readMockIntervalMs, readMockNumber } from "./mockConfig.ts";

const DEFAULT_INTERVAL_MS = 500;
const MIN_INTERVAL_MS = 100;
const DEFAULT_STEP = 18;
const DEFAULT_RADIUS = 160;
const MIN_RADIUS = 30;
const PLANET = MAP_CONFIG.planets.calypso;

type WalkerState = {
    homeX: number;
    homeY: number;
    x: number;
    y: number;
    heading: number;
    tick: number;
    step: number;
    radius: number;
};

function clamp(value: number, min: number, max: number): number {
    return Math.min(max, Math.max(min, value));
}

function normalizeAngle(angle: number): number {
    let normalized = angle;
    while (normalized > Math.PI) normalized -= Math.PI * 2;
    while (normalized < -Math.PI) normalized += Math.PI * 2;
    return normalized;
}

function createWalker(): WalkerState {
    const centerX = Math.round((PLANET.minLon + PLANET.maxLon) / 2);
    const centerY = Math.round((PLANET.minLat + PLANET.maxLat) / 2);
    const homeX = clamp(readMockNumber("ZML_MOCK_POSITION_X", centerX), PLANET.minLon, PLANET.maxLon);
    const homeY = clamp(readMockNumber("ZML_MOCK_POSITION_Y", centerY), PLANET.minLat, PLANET.maxLat);
    const step = Math.max(1, readMockNumber("ZML_MOCK_POSITION_STEP", DEFAULT_STEP));
    const radius = Math.max(MIN_RADIUS, readMockNumber("ZML_MOCK_POSITION_RADIUS", DEFAULT_RADIUS));

    return {
        homeX,
        homeY,
        x: homeX,
        y: homeY,
        heading: -0.35,
        tick: 0,
        step,
        radius,
    };
}

function advanceWalker(walker: WalkerState): void {
    const dxHome = walker.homeX - walker.x;
    const dyHome = walker.homeY - walker.y;
    const distanceFromHome = Math.hypot(dxHome, dyHome);

    const naturalTurn = Math.sin(walker.tick * 0.31) * 0.045 + Math.cos(walker.tick * 0.11) * 0.025;
    walker.heading = normalizeAngle(walker.heading + naturalTurn);

    if (distanceFromHome > walker.radius) {
        const homeHeading = Math.atan2(dyHome, dxHome);
        const turnToHome = normalizeAngle(homeHeading - walker.heading);
        walker.heading = normalizeAngle(walker.heading + clamp(turnToHome, -0.18, 0.18));
    }

    const pace = walker.step * (0.82 + Math.sin(walker.tick * 0.23) * 0.12);
    walker.x = clamp(walker.x + Math.cos(walker.heading) * pace, PLANET.minLon, PLANET.maxLon);
    walker.y = clamp(walker.y + Math.sin(walker.heading) * pace, PLANET.minLat, PLANET.maxLat);
    walker.tick += 1;
}

function buildPositionEvent(seq: number, walker: WalkerState, tsMs: number): OcrPositionEvent {
    return {
        type: "ocr.position",
        seq,
        tsMs,
        payload: {
            tsMs,
            position: {
                planetName: PLANET.name,
                x: Math.round(walker.x),
                y: Math.round(walker.y),
                z: null,
            },
        },
    };
}

export function startMockPositionSource(opts: PositionSourceOptions): StopPositionSource {
    const intervalMs = readMockIntervalMs("ZML_MOCK_POSITION_INTERVAL_MS", DEFAULT_INTERVAL_MS, MIN_INTERVAL_MS);
    const walker = createWalker();
    let seq = 0;

    opts.onStatus("connecting");
    opts.onStatus("connected");

    const emitPosition = () => {
        opts.onEvent(buildPositionEvent(++seq, walker, Date.now()));
        advanceWalker(walker);
    };

    emitPosition();

    const timer = setInterval(emitPosition, intervalMs);

    return () => {
        clearInterval(timer);
        opts.onStatus("disconnected");
    };
}
