from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from zml_game_bridge.api.routes.mining_tools import (
    create_mining_tool_profile,
    delete_mining_tool_profile,
    get_active_mining_tools,
    list_mining_tool_profiles,
    set_active_mining_tools,
)
from zml_game_bridge.api.schemas.mining_tools import (
    CreateMiningToolProfileRequestDto,
    SetActiveMiningToolsRequestDto,
)
from zml_game_bridge.runtime.mining.mining_setup import MiningSetupService
from zml_game_bridge.runtime.mining.tools import MiningToolService
from zml_game_bridge.runtime.runtime_commands import RuntimeCommand


class _RuntimeStub:
    def __init__(self, service: MiningToolService) -> None:
        self.mining_tool_service = service
        self._setup = MiningSetupService(tool_service=service)

    def execute_runtime_command[T](
        self,
        command: RuntimeCommand[T],
        *,
        timeout_s: float = 5.0,
    ) -> T:
        del timeout_s
        return self._setup.process_command(command).value


def test_mining_tool_routes_create_list_and_set_active_tools(tmp_path: Path) -> None:
    service = MiningToolService(path=tmp_path / "mining_tools.json")
    runtime: Any = _RuntimeStub(service)

    finder = create_mining_tool_profile(
        CreateMiningToolProfileRequestDto(
            kind="finder",
            name="Finder",
            decay_mpec=1_000,
            markup_percent="100",
            radius_m=55.0,
        ),
        runtime,
    )
    extractor = create_mining_tool_profile(
        CreateMiningToolProfileRequestDto(
            kind="extractor",
            name="Extractor",
            decay_mpec=100,
            markup_percent="125",
        ),
        runtime,
    )

    profiles = list_mining_tool_profiles(service)
    active = set_active_mining_tools(
        SetActiveMiningToolsRequestDto(
            finder_id=finder.tool_id,
            amp_id=None,
            extractor_id=extractor.tool_id,
            finder_range_enhancer_count=1,
        ),
        runtime,
    )

    assert [profile.name for profile in profiles] == ["Finder", "Extractor"]
    assert active.finder_id == finder.tool_id
    assert active.extractor_id == extractor.tool_id
    assert active.finder_range_enhancer_count == 1
    assert active.effective_finder_radius_m == 55.55
    assert active.extraction_cost_mpec == 125
    assert get_active_mining_tools(service) == active


def test_mining_tool_routes_delete_tool_and_clear_active_state(tmp_path: Path) -> None:
    service = MiningToolService(path=tmp_path / "mining_tools.json")
    runtime: Any = _RuntimeStub(service)
    finder = create_mining_tool_profile(
        CreateMiningToolProfileRequestDto(
            kind="finder",
            name="Finder",
            decay_mpec=1_000,
            radius_m=55.0,
        ),
        runtime,
    )
    set_active_mining_tools(
        SetActiveMiningToolsRequestDto(
            finder_id=finder.tool_id,
            finder_range_enhancer_count=1,
        ),
        runtime,
    )

    delete_mining_tool_profile(finder.tool_id, runtime)

    assert list_mining_tool_profiles(service) == []
    active = get_active_mining_tools(service)
    assert active.finder_id is None
    assert active.finder_range_enhancer_count == 0


def test_mining_tool_routes_delete_unknown_tool_returns_404(tmp_path: Path) -> None:
    service = MiningToolService(path=tmp_path / "mining_tools.json")
    runtime: Any = _RuntimeStub(service)

    try:
        delete_mining_tool_profile("missing-tool", runtime)
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected missing tool HTTPException")
