from __future__ import annotations

from pathlib import Path

from zml_game_bridge.application.mining.equipment.service import MiningEquipmentService
from zml_game_bridge.domain.mining_cost import calculate_drop_cost, calculate_extraction_cost
from zml_game_bridge.domain.money import Mpec, mpec_to_int


def test_mining_equipment_service_creates_active_loadout_and_persists_it(tmp_path: Path) -> None:
    path = tmp_path / "mining_tools.json"
    service = MiningEquipmentService(path=path)

    finder = service.create_profile(
        kind="finder",
        name="Finder",
        decay_mpec=Mpec(1_000),
        markup_percent="100",
        radius_m=55.0,
    )
    amp = service.create_profile(
        kind="amp",
        name="Amp",
        decay_mpec=Mpec(2_000),
        markup_percent="125",
    )
    extractor = service.create_profile(
        kind="extractor",
        name="Extractor",
        decay_mpec=Mpec(100),
        markup_percent="125",
    )

    service.set_active_tools(
        finder_id=finder.tool_id,
        amp_id=amp.tool_id,
        extractor_id=extractor.tool_id,
        finder_range_enhancer_count=2,
    )

    reloaded = MiningEquipmentService(path=path)
    active = reloaded.active_tools()
    profile = reloaded.get_equipment_profile()
    drop_cost = calculate_drop_cost(
        profile=profile,
        ocr_ammo_per_drop=1_000,
        ocr_probes_per_drop=None,
    )

    assert active.finder_id == finder.tool_id
    assert active.amp_id == amp.tool_id
    assert active.extractor_id == extractor.tool_id
    assert active.finder_range_enhancer_count == 2
    assert profile.finder.name == "Finder"
    assert profile.amp is not None
    assert profile.extractor is not None
    assert mpec_to_int(drop_cost.finder_decay_mpec) == 1_000
    assert mpec_to_int(drop_cost.finder_enhancer_decay_mpec) == 200
    assert mpec_to_int(drop_cost.amp_decay_mpec) == 2_500
    assert calculate_extraction_cost(profile) == Mpec(125)


def test_mining_equipment_service_rejects_wrong_kind_as_active_tool(tmp_path: Path) -> None:
    service = MiningEquipmentService(path=tmp_path / "mining_tools.json")
    amp = service.create_profile(
        kind="amp",
        name="Amp",
        decay_mpec=Mpec(2_000),
        markup_percent="125",
    )

    try:
        service.set_active_tools(
            finder_id=amp.tool_id,
            amp_id=None,
            extractor_id=None,
            finder_range_enhancer_count=0,
        )
    except ValueError as exc:
        assert "expected finder" in str(exc)
    else:
        raise AssertionError("Expected invalid active finder")


def test_mining_equipment_service_deletes_active_tool_and_clears_active_slot(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mining_tools.json"
    service = MiningEquipmentService(path=path)
    finder = service.create_profile(
        kind="finder",
        name="Finder",
        decay_mpec=Mpec(1_000),
        radius_m=55.0,
    )
    extractor = service.create_profile(
        kind="extractor",
        name="Extractor",
        decay_mpec=Mpec(100),
    )
    service.set_active_tools(
        finder_id=finder.tool_id,
        amp_id=None,
        extractor_id=extractor.tool_id,
        finder_range_enhancer_count=2,
    )

    assert service.delete_profile(finder.tool_id) is True

    active = service.active_tools()
    assert service.get_profile(finder.tool_id) is None
    assert active.finder_id is None
    assert active.extractor_id == extractor.tool_id
    assert active.finder_range_enhancer_count == 0

    reloaded = MiningEquipmentService(path=path)
    assert reloaded.get_profile(finder.tool_id) is None
    assert reloaded.active_tools().finder_id is None


def test_mining_equipment_service_delete_unknown_tool_returns_false(tmp_path: Path) -> None:
    service = MiningEquipmentService(path=tmp_path / "mining_tools.json")

    assert service.delete_profile("missing-tool") is False
