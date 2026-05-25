from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import cast

from zml_game_bridge.events.base import EventBase, SignalBase
from zml_game_bridge.runtime.channels import EventChannel, RuntimeInputChannel
from zml_game_bridge.runtime.input_coordinator import InputCoordinator
from zml_game_bridge.runtime.runtime_commands import (
    RuntimeCommand,
    RuntimeCommandRequest,
    RuntimeCommandResult,
    UnsupportedRuntimeCommandError,
)


@dataclass(frozen=True, slots=True)
class DurableDummyEvent(EventBase):
    x: int


@dataclass(frozen=True, slots=True)
class TransientDummySignal(SignalBase):
    x: int


@dataclass(frozen=True, slots=True)
class DummyCommand(RuntimeCommand[int]):
    x: int


class FakeInputProcessor:
    def process_signal(self, signal: SignalBase) -> list[EventBase]:
        if isinstance(signal, TransientDummySignal):
            return [DurableDummyEvent(signal.x + 1)]
        return []

    def process_command[T](self, command: RuntimeCommand[T]) -> RuntimeCommandResult[T]:
        if isinstance(command, DummyCommand):
            return cast(RuntimeCommandResult[T], RuntimeCommandResult(command.x + 1))
        raise UnsupportedRuntimeCommandError(type(command).__name__)


def test_input_coordinator_routes_derived_event_to_writer_queue_without_publishing_signal() -> None:
    incoming = RuntimeInputChannel(maxsize=10)
    pending_events = EventChannel(maxsize=10)
    worker = InputCoordinator(
        pending_inputs=incoming,
        pending_events=pending_events,
        input_processor=FakeInputProcessor(),
    )

    stop = threading.Event()
    thread = threading.Thread(target=worker.run, kwargs={"stop_event": stop}, daemon=True)
    thread.start()

    incoming.emit(TransientDummySignal(41))

    derived = pending_events.take(timeout_s=1.0)

    stop.set()
    incoming.close()
    thread.join(timeout=1.0)

    assert derived == DurableDummyEvent(42)


def test_input_coordinator_drops_internal_signal_when_no_event_is_derived() -> None:
    incoming = RuntimeInputChannel(maxsize=10)
    pending_events = EventChannel(maxsize=10)
    worker = InputCoordinator(
        pending_inputs=incoming,
        pending_events=pending_events,
    )

    stop = threading.Event()
    thread = threading.Thread(target=worker.run, kwargs={"stop_event": stop}, daemon=True)
    thread.start()

    incoming.emit(TransientDummySignal(1))
    event = pending_events.take(timeout_s=0.2)

    stop.set()
    incoming.close()
    thread.join(timeout=1.0)

    assert event is None


def test_input_coordinator_processes_runtime_command_response() -> None:
    incoming = RuntimeInputChannel(maxsize=10)
    pending_events = EventChannel(maxsize=10)
    worker = InputCoordinator(
        pending_inputs=incoming,
        pending_events=pending_events,
        input_processor=FakeInputProcessor(),
    )

    stop = threading.Event()
    thread = threading.Thread(target=worker.run, kwargs={"stop_event": stop}, daemon=True)
    thread.start()

    request = RuntimeCommandRequest(DummyCommand(41))
    incoming.emit(request)
    result = request.result(timeout_s=1.0)

    stop.set()
    incoming.close()
    thread.join(timeout=1.0)

    assert result == 42
