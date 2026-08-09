from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from zml_ocr_protocol import BridgeToAgentMessage, encode_message


class OcrProcessTransport(Protocol):
    @property
    def pid(self) -> int: ...

    def start(self) -> None: ...

    def read_stdout_line(self) -> bytes: ...

    def read_stderr_line(self) -> bytes: ...

    def send(self, message: BridgeToAgentMessage) -> None: ...

    def poll(self) -> int | None: ...

    def wait(self, *, timeout_s: float) -> int | None: ...

    def close_stdin(self) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


@dataclass(frozen=True, slots=True)
class OcrWorkerProcessConfig:
    command: tuple[str, ...]
    environment: Mapping[str, str]
    cwd: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", normalize_command(self.command))


class StdioOcrProcessTransport:
    def __init__(self, config: OcrWorkerProcessConfig) -> None:
        self._config = config
        self._process: subprocess.Popen[bytes] | None = None
        self._write_lock = threading.Lock()

    @property
    def pid(self) -> int:
        return self._require_process().pid

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("OCR Worker transport is already started")
        if not self._config.command:
            raise ValueError("OCR Worker command cannot be empty")

        environment = dict(os.environ)
        environment.update(self._config.environment)
        self._process = subprocess.Popen(
            list(self._config.command),
            cwd=self._config.cwd,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def read_stdout_line(self) -> bytes:
        process = self._require_process()
        if process.stdout is None:
            raise RuntimeError("OCR Worker stdout pipe is unavailable")
        return process.stdout.readline()

    def read_stderr_line(self) -> bytes:
        process = self._require_process()
        if process.stderr is None:
            raise RuntimeError("OCR Worker stderr pipe is unavailable")
        return process.stderr.readline()

    def send(self, message: BridgeToAgentMessage) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise RuntimeError("OCR Worker stdin pipe is unavailable")
        encoded = encode_message(message)
        with self._write_lock:
            process.stdin.write(encoded)
            process.stdin.flush()

    def poll(self) -> int | None:
        return self._require_process().poll()

    def wait(self, *, timeout_s: float) -> int | None:
        try:
            return self._require_process().wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return None

    def close_stdin(self) -> None:
        process = self._require_process()
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()

    def terminate(self) -> None:
        process = self._require_process()
        if process.poll() is None:
            process.terminate()

    def kill(self) -> None:
        process = self._require_process()
        if process.poll() is None:
            process.kill()

    def _require_process(self) -> subprocess.Popen[bytes]:
        if self._process is None:
            raise RuntimeError("OCR Worker transport is not started")
        return self._process


def normalize_command(command: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(part for part in command if part.strip())
    if not normalized:
        raise ValueError("OCR Worker command cannot be empty")
    return normalized
