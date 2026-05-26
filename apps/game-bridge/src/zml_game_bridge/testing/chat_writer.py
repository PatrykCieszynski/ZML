from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ChatLogWriter:
    path: Path

    def append(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            if not line.endswith("\n"):
                line += "\n"
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
