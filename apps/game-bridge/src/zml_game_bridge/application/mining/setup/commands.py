from __future__ import annotations

from dataclasses import dataclass

from zml_game_bridge.application.mining.setup.tools import (
    ActiveMiningTools,
    MiningToolKind,
    MiningToolProfileRecord,
)
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.runtime.runtime_commands import RuntimeCommand


class MiningToolCommandError(Exception):
    """Base class for user-facing mining tool command failures."""


class MiningToolNotFoundError(MiningToolCommandError):
    def __init__(self, tool_id: str) -> None:
        super().__init__(f"Mining tool not found: {tool_id}")
        self.tool_id = tool_id


@dataclass(frozen=True, slots=True)
class CreateMiningToolProfileCommand(RuntimeCommand[MiningToolProfileRecord]):
    kind: MiningToolKind
    name: str
    decay_mpec: Mpec
    markup_percent: str = "100"
    radius_m: float | None = None


@dataclass(frozen=True, slots=True)
class DeleteMiningToolProfileCommand(RuntimeCommand[None]):
    tool_id: str


@dataclass(frozen=True, slots=True)
class SetActiveMiningToolsCommand(RuntimeCommand[ActiveMiningTools]):
    finder_id: str | None
    amp_id: str | None
    extractor_id: str | None
    finder_range_enhancer_count: int
