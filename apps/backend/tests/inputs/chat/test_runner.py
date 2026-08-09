# tests/inputs/chat/test_runner.py
from __future__ import annotations

import threading
from pathlib import Path

from zml_backend.inputs.chat import runner as chat_runner
from zml_backend.inputs.chat.model import ChannelType, ChatLine
from zml_backend.inputs.chat.signals import ResourceDepletedSignal


def _mk_line(message: str) -> ChatLine:
    # Keep it deterministic; only the fields used by interpreter/events matter here.
    from datetime import datetime

    raw = f"2026-01-10 12:37:50 [System] [] {message}"
    return ChatLine(
        event_dt=datetime(2026, 1, 10, 12, 37, 50),
        channel_type=ChannelType.SYSTEM,
        channel_token="System",
        speaker="",
        message=message,
        raw=raw,
    )


def test_chat_runner_emits_signal(monkeypatch, tmp_path: Path) -> None:
    # Tailer yields exactly one line
    monkeypatch.setattr(chat_runner, "tail_lines", lambda *a, **k: iter(["RAW"]))

    # Parser returns a ChatLine
    monkeypatch.setattr(
        chat_runner, "parse_chat_line", lambda raw: _mk_line("This resource is depleted")
    )

    # Interpreter returns a domain event
    monkeypatch.setattr(
        chat_runner,
        "interpret_chat_line",
        lambda line: ResourceDepletedSignal(
            event_dt=line.event_dt,
            channel_type=line.channel_type,
            channel_token=line.channel_token,
            raw=line.raw,
        ),
    )

    out = []

    def sink(ev) -> None:
        out.append(ev)

    stop = threading.Event()
    chat_runner.start_chat_input(
        path=tmp_path / "chat.log",
        signal_sink=sink,
        stop_event=stop,
        start_at_end=True,
    )

    assert len(out) == 1
    assert isinstance(out[0], ResourceDepletedSignal)
