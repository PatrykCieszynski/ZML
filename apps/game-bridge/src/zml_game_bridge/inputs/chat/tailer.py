from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

# TODO: read in fixed-size chunks (avoid unbounded read())
# TODO: guard buffer growth if no newline appears

def tail_lines(
    path: Path,
    *,
    start_at_end: bool,
    poll_interval_s: float = 0.05,
    stop_event: threading.Event | None = None,
    encoding: str = "utf-8",
) -> Iterator[str]:
    if stop_event is None:
        stop_event = threading.Event()

    buf = ""
    offset = 0

    # IMPORTANT:
    # If file did NOT exist when tailer started, we must NOT skip
    # the first lines written after creation.
    should_skip_existing_once = start_at_end and path.exists()

    while not stop_event.is_set():
        if not path.exists():
            time.sleep(poll_interval_s)
            continue

        try:
            with path.open("r", encoding=encoding, errors="replace", newline="") as f:
                if should_skip_existing_once:
                    f.seek(0, 2)  # end
                    offset = f.tell()
                    should_skip_existing_once = False
                else:
                    f.seek(offset, 0)

                while not stop_event.is_set():
                    chunk = f.read()
                    if not chunk:
                        # Optional: truncation detection
                        try:
                            size_now = path.stat().st_size
                        except FileNotFoundError:
                            break

                        if size_now < offset:
                            buf = ""
                            offset = 0
                            break

                        time.sleep(poll_interval_s)
                        continue

                    buf += chunk
                    offset = f.tell()

                    while True:
                        nl = buf.find("\n")
                        if nl < 0:
                            break
                        line = buf[:nl]
                        buf = buf[nl + 1 :]

                        if line.endswith("\r"):
                            line = line[:-1]
                        yield line

        except OSError:
            time.sleep(poll_interval_s)
            continue
