from __future__ import annotations

from collections.abc import Callable

from zml_backend.domain.position import WorldPos

PositionProvider = Callable[[], WorldPos | None]
