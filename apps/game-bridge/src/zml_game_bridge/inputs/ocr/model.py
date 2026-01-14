from dataclasses import dataclass

from zml_game_bridge.common.models import WorldPos


@dataclass(frozen=True, slots=True)
class OcrPosition:
    ts_ms: int
    position: WorldPos