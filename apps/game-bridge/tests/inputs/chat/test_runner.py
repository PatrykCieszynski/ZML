# tests/inputs/chat/test_runner.py
from __future__ import annotations

import threading

from zml_game_bridge.inputs.chat.model import ChannelType, ChatLine
from zml_game_bridge.inputs.chat.events import ResourceDepleted
from zml_game_bridge.inputs.chat import runner as chat_runner


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


def test_chat_runner_emits_event(monkeypatch) -> None:
    # Tailer yields exactly one line
    monkeypatch.setattr(chat_runner, "tail_lines", lambda *a, **k: iter(["RAW"]))

    # Parser returns a ChatLine
    monkeypatch.setattr(chat_runner, "parse_chat_line", lambda raw: _mk_line("This resource is depleted"))

    # Interpreter returns a domain event
    monkeypatch.setattr(
        chat_runner,
        "interpret_chat_line",
        lambda line: ResourceDepleted(
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
    chat_runner.start_chat_input(path=None, event_sink=sink, stop_event=stop, start_at_end=True)  # type: ignore[arg-type]

    assert len(out) == 1
    assert isinstance(out[0], ResourceDepleted)
