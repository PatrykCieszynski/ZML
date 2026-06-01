from __future__ import annotations

from collections.abc import Callable

from zml_game_bridge.domain.position import WorldPos

PositionProvider = Callable[[], WorldPos | None]
