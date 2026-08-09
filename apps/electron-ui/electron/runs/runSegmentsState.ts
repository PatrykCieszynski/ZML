import {
    isRunSegmentEndedEventWire,
    isRunSegmentStartedEventWire,
    runSegmentDtoFromStartedEventWire,
    runSegmentDtoWithEndedEvent,
    type AgentEventEnvelope,
    type RunDto,
    type RunSegmentDto,
} from "@desktop/shared";

import { pushStatePatch } from "../ipc/pushStatePatch.ts";
import { runtime } from "../runtime.ts";

export function replaceActiveRun(activeRun: RunDto | null): void {
    runtime.activeRun = activeRun;
    pushStatePatch({ activeRun });
}

export function replaceRunSegments(segments: readonly RunSegmentDto[]): void {
    runtime.runSegments = sortSegments([...segments]);
    pushStatePatch({ runSegments: runtime.runSegments });
}

export function applyRunEvent(event: AgentEventEnvelope<string, unknown>): void {
    if (event.type === "RunSegmentStartedEvent" && isRunSegmentStartedEventWire(event.payload)) {
        const payload = event.payload;
        if (runtime.activeRun !== null && runtime.activeRun.runId !== payload.run_id) return;
        upsertRunSegment(runSegmentDtoFromStartedEventWire(payload, event.createdTsMs));
        return;
    }

    if (event.type === "RunSegmentEndedEvent" && isRunSegmentEndedEventWire(event.payload)) {
        const payload = event.payload;
        if (runtime.activeRun !== null && runtime.activeRun.runId !== payload.run_id) return;
        updateRunSegment(payload.segment_id, (segment) =>
            runSegmentDtoWithEndedEvent(segment, payload, event.createdTsMs),
        );
    }
}

function upsertRunSegment(segment: RunSegmentDto): void {
    const withoutCurrent = runtime.runSegments.filter((item) => item.segmentId !== segment.segmentId);
    runtime.runSegments = sortSegments([segment, ...withoutCurrent]);
    pushStatePatch({ runSegments: runtime.runSegments });
}

function updateRunSegment(
    segmentId: string,
    update: (segment: RunSegmentDto) => RunSegmentDto,
): void {
    let changed = false;
    runtime.runSegments = runtime.runSegments.map((segment) => {
        if (segment.segmentId !== segmentId) return segment;
        changed = true;
        return update(segment);
    });

    if (!changed) return;
    runtime.runSegments = sortSegments(runtime.runSegments);
    pushStatePatch({ runSegments: runtime.runSegments });
}

function sortSegments(segments: RunSegmentDto[]): RunSegmentDto[] {
    return segments.sort((a, b) => a.segmentIndex - b.segmentIndex);
}
