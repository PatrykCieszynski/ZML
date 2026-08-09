from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import BinaryIO

from zml_ocr_protocol import ApplyConfigCommand, ShutdownCommand, decode_bridge_message


class Emitter:
    def __init__(self, output: BinaryIO) -> None:
        self._output = output
        self._lock = threading.Lock()
        self._sequence_id = 0

    def emit(
        self,
        message_type: str,
        payload: dict[str, object],
        *,
        observed_ts_ms: int | None = None,
    ) -> None:
        with self._lock:
            now_ms = time.time_ns() // 1_000_000
            message: dict[str, object] = {
                "protocol_version": 1,
                "type": message_type,
                "message_id": f"{self._sequence_id + 1:032x}",
                "sequence_id": self._sequence_id,
                "emitted_ts_ms": now_ms,
                "payload": payload,
            }
            if observed_ts_ms is not None:
                message["observed_ts_ms"] = observed_ts_ms
            self._sequence_id += 1
            self._output.write(json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n")
            self._output.flush()

    def malformed(self) -> None:
        with self._lock:
            self._output.write(b"{definitely-not-json}\n")
            self._output.flush()


def main() -> int:
    scenario = os.getenv("ZML_FAKE_OCR_SCENARIO", "happy")
    output = sys.stdout.buffer
    emitter = Emitter(output)
    stop_event = threading.Event()
    heartbeat_thread: threading.Thread | None = None

    if scenario == "stderr_flood":
        block = "x" * 1024
        for index in range(128):
            print(f"fake-stderr-{index:03d} {block}", file=sys.stderr, flush=True)

    emitter.emit(
        "hello",
        {
            "agent_version": "fake-1.0",
            "pid": os.getpid(),
            "started_ts_ms": time.time_ns() // 1_000_000,
            "capabilities": [
                "stdio",
                "position",
                "finder",
                "status",
                "heartbeat",
                "apply_config",
                "shutdown",
            ],
        },
    )

    applied_revision: int | None = None
    for line in sys.stdin.buffer:
        command = decode_bridge_message(line)
        if isinstance(command, ApplyConfigCommand):
            applied_revision = command.payload.revision
            emitter.emit(
                "command_result",
                {
                    "command_id": command.command_id,
                    "command_type": "apply_config",
                    "status": "ok",
                    "applied_revision": applied_revision,
                    "capture": None,
                    "error": None,
                },
            )
            if scenario == "crash_once" and _claim_first_crash():
                return 7
            if scenario == "malformed":
                emitter.malformed()
                continue
            if scenario == "no_heartbeat":
                continue

            state = "waiting_for_window" if scenario == "window_unavailable" else "running"
            capture_available = state == "running"
            emitter.emit(
                "status",
                {
                    "state": state,
                    "capture_available": capture_available,
                    "applied_revision": applied_revision,
                    "code": "window_unavailable" if not capture_available else None,
                    "detail": "window missing" if not capture_available else None,
                },
            )
            emitter.emit(
                "heartbeat",
                {
                    "state": state,
                    "capture_available": capture_available,
                    "applied_revision": applied_revision,
                },
            )
            if capture_available:
                now_ms = time.time_ns() // 1_000_000
                emitter.emit(
                    "position",
                    {
                        "position": {
                            "planet_name": "Calypso",
                            "x": 58_000,
                            "y": 84_000,
                            "z": None,
                        },
                        "confidence": None,
                        "roi_name": "compass",
                    },
                    observed_ts_ms=now_ms,
                )
                emitter.emit(
                    "finder_signal",
                    {
                        "kind": "finder_no_resources",
                        "raw_status_text": "No resources found",
                        "roi_name": "finder",
                        "debug": {},
                    },
                    observed_ts_ms=now_ms + 1,
                )
            if heartbeat_thread is None:
                heartbeat_thread = threading.Thread(
                    target=_emit_heartbeats,
                    kwargs={
                        "emitter": emitter,
                        "stop_event": stop_event,
                        "state": state,
                        "capture_available": capture_available,
                        "revision": applied_revision,
                    },
                    daemon=True,
                )
                heartbeat_thread.start()
            continue

        if isinstance(command, ShutdownCommand):
            if scenario == "ignore_shutdown":
                continue
            stop_event.set()
            emitter.emit(
                "command_result",
                {
                    "command_id": command.command_id,
                    "command_type": "shutdown",
                    "status": "ok",
                    "applied_revision": applied_revision,
                    "capture": None,
                    "error": None,
                },
            )
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=1.0)
            return 0

    stop_event.set()
    if heartbeat_thread is not None:
        heartbeat_thread.join(timeout=1.0)
    if scenario == "ignore_shutdown":
        while True:
            time.sleep(1.0)
    return 0


def _emit_heartbeats(
    *,
    emitter: Emitter,
    stop_event: threading.Event,
    state: str,
    capture_available: bool,
    revision: int,
) -> None:
    while not stop_event.wait(0.05):
        emitter.emit(
            "heartbeat",
            {
                "state": state,
                "capture_available": capture_available,
                "applied_revision": revision,
            },
        )


def _claim_first_crash() -> bool:
    marker_value = os.environ["ZML_FAKE_OCR_MARKER"]
    marker = Path(marker_value)
    try:
        marker.open("x", encoding="utf-8").close()
        return True
    except FileExistsError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
