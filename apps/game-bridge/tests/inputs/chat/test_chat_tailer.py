from __future__ import annotations

import queue
import threading
from pathlib import Path

import pytest

from zml_game_bridge.inputs.chat.tailer import tail_lines
from zml_game_bridge.testing.chat_writer import ChatLogWriter


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
        _q_expect_no_item(out, timeout_s=0.2)
        w.append("NEW1")
        assert _q_get(out) == "NEW1"
    finally:
        stop.set()
        t.join(timeout=1)


def test_emits_lines_appended_later(chat_log: Path) -> None:
    w = ChatLogWriter(chat_log)

    t, stop, out = _start_tailer_thread(path=chat_log, start_at_end=True)
    try:
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
    w = ChatLogWriter(chat_log)

    t, stop, out = _start_tailer_thread(path=chat_log, start_at_end=True)
    try:
        # write partial without newline (bypass ChatLogWriter.append)
        chat_log.parent.mkdir(parents=True, exist_ok=True)
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
