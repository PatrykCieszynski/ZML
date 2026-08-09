from __future__ import annotations

import queue
import threading
from pathlib import Path

import pytest

from zml_backend.inputs.chat.tailer import tail_lines
from zml_backend.testing.chat_writer import ChatLogWriter


def _start_tailer_thread(
    *,
    path: Path,
    start_at_end: bool,
    poll_interval_s: float = 0.01,
) -> tuple[threading.Thread, threading.Event, queue.Queue[str]]:
    stop_event = threading.Event()
    out: queue.Queue[str] = queue.Queue()

    def worker() -> None:
        for line in tail_lines(
            path,
            start_at_end=start_at_end,
            poll_interval_s=poll_interval_s,
            stop_event=stop_event,
        ):
            out.put(line)

    t = threading.Thread(target=worker, name="test-chat-tailer", daemon=True)
    t.start()
    return t, stop_event, out


def _q_get(q: queue.Queue[str], timeout_s: float = 1.0) -> str:
    try:
        return q.get(timeout=timeout_s)
    except queue.Empty as e:
        raise AssertionError("Timed out waiting for a tailed line") from e


def _q_expect_no_item(q: queue.Queue[str], timeout_s: float = 0.2) -> None:
    try:
        item = q.get(timeout=timeout_s)
    except queue.Empty:
        return
    raise AssertionError(f"Expected no item, but got: {item!r}")


def _wait_until_tailer_observes_new_lines(
    *,
    path: Path,
    out: queue.Queue[str],
    timeout_s: float = 2.0,
) -> None:
    """
    Synchronize tests with a tailer running in start_at_end mode.

    The tailer may start after the first appended line and skip it due to
    start_at_end=True. Keep appending sentinel lines until one is observed.
    """
    prefix = "__TAILER_READY__"
    writer = ChatLogWriter(path)
    attempts = max(1, int(timeout_s / 0.05))

    for attempt in range(attempts):
        marker = f"{prefix}{attempt}"
        writer.append(marker)

        try:
            item = out.get(timeout=0.05)
        except queue.Empty:
            continue

        if not item.startswith(prefix):
            raise AssertionError(f"Unexpected line while waiting for tailer readiness: {item!r}")

        _drain_tailer_ready_markers(out, prefix=prefix)
        return

    raise AssertionError("Timed out waiting until tailer observes new lines")


def _drain_tailer_ready_markers(q: queue.Queue[str], *, prefix: str) -> None:
    while True:
        try:
            item = q.get(timeout=0.05)
        except queue.Empty:
            return

        if not item.startswith(prefix):
            raise AssertionError(f"Unexpected non-readiness line: {item!r}")


@pytest.fixture()
def chat_log(tmp_path: Path) -> Path:
    return tmp_path / "chat.log"


def test_reads_existing_lines_when_start_at_end_false(chat_log: Path) -> None:
    w = ChatLogWriter(chat_log)
    w.append("L1")
    w.append("L2")

    t, stop, out = _start_tailer_thread(path=chat_log, start_at_end=False)
    try:
        assert _q_get(out) == "L1"
        assert _q_get(out) == "L2"
    finally:
        stop.set()
        t.join(timeout=1)


def test_ignores_existing_lines_when_start_at_end_true(chat_log: Path) -> None:
    w = ChatLogWriter(chat_log)
    w.append("OLD1")
    w.append("OLD2")

    t, stop, out = _start_tailer_thread(path=chat_log, start_at_end=True)
    try:
        _wait_until_tailer_observes_new_lines(path=chat_log, out=out)

        w.append("NEW1")
        assert _q_get(out) == "NEW1"
    finally:
        stop.set()
        t.join(timeout=1)


def test_emits_lines_appended_later(chat_log: Path) -> None:
    w = ChatLogWriter(chat_log)

    t, stop, out = _start_tailer_thread(path=chat_log, start_at_end=True)
    try:
        _wait_until_tailer_observes_new_lines(path=chat_log, out=out)

        w.append("A")
        w.append("B")
        assert _q_get(out) == "A"
        assert _q_get(out) == "B"
    finally:
        stop.set()
        t.join(timeout=1)


def test_does_not_emit_partial_line_until_newline(chat_log: Path) -> None:
    """
    Chat logs can be written in chunks. Tailing must only emit complete lines.
    """
    chat_log.parent.mkdir(parents=True, exist_ok=True)
    chat_log.write_text("", encoding="utf-8")

    t, stop, out = _start_tailer_thread(path=chat_log, start_at_end=False)
    try:
        with chat_log.open("a", encoding="utf-8", newline="\n") as f:
            f.write("PARTIAL")
            f.flush()

        _q_expect_no_item(out, timeout_s=0.2)

        with chat_log.open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n")
            f.flush()

        assert _q_get(out) == "PARTIAL"
    finally:
        stop.set()
        t.join(timeout=1)


def test_start_at_end_true_does_not_emit_partial_line_until_newline(
    chat_log: Path,
) -> None:
    """
    start_at_end=True ignores existing content, but newly appended partial lines
    must still be buffered until a newline is written.
    """
    w = ChatLogWriter(chat_log)
    w.append("OLD")

    t, stop, out = _start_tailer_thread(path=chat_log, start_at_end=True)
    try:
        _wait_until_tailer_observes_new_lines(path=chat_log, out=out)

        with chat_log.open("a", encoding="utf-8", newline="\n") as f:
            f.write("PARTIAL")
            f.flush()

        _q_expect_no_item(out, timeout_s=0.2)

        with chat_log.open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n")
            f.flush()

        assert _q_get(out) == "PARTIAL"
    finally:
        stop.set()
        t.join(timeout=1)
