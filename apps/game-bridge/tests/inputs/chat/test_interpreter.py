from __future__ import annotations

from datetime import datetime

import pytest

from zml_game_bridge.inputs.chat.model import ChatLine, ChannelType
from zml_game_bridge.inputs.chat import interpreter as chat_interpreter
from zml_game_bridge.inputs.chat.events import (
    EnhancerBroke,
    ItemReceived,
    PlayerPosWaypoint,
    ResourceClaimed,
    ResourceDepleted,
    SkillGained,
)


def _mk_line(
    message: str,
    *,
    channel_type: ChannelType = ChannelType.SYSTEM,
    channel_token: str = "System",
    raw: str | None = None,
) -> ChatLine:
    dt = datetime(2026, 1, 10, 12, 0, 0)
    return ChatLine(
        event_dt=dt,
        channel_type=channel_type,
        channel_token=channel_token,
        speaker="",
        message=message,
        raw=raw or f"{dt.isoformat(sep=' ')} [{channel_token}] [] {message}",
    )


def test_interpret_system_item_received_parses_mpec_exact() -> None:
    line = _mk_line("You received Blue Crystal x (8) Value: 0.1600 PED")
    ev = chat_interpreter.interpret_chat_line(line)
    assert isinstance(ev, ItemReceived)
    assert ev.item_name == "Blue Crystal"
    assert ev.qty == 8
    assert ev.value_mpec == 16000


def test_interpret_system_item_received_rejects_lossy_mpec() -> None:
    # 0.0001 * 1000 = 0.1 -> not integral -> should refuse
    line = _mk_line("You received Shrapnel x (1) Value: 0.000001 PED")
    ev = chat_interpreter.interpret_chat_line(line)
    assert ev is None


def test_interpret_system_resource_claimed() -> None:
    line = _mk_line("You have claimed a resource! (Yellow Crystal)")
    ev = chat_interpreter.interpret_chat_line(line)
    assert isinstance(ev, ResourceClaimed)
    assert ev.resource_name == "Yellow Crystal"


def test_interpret_system_resource_depleted() -> None:
    line = _mk_line("This resource is depleted")
    ev = chat_interpreter.interpret_chat_line(line)
    assert isinstance(ev, ResourceDepleted)


def test_interpret_system_position_ping() -> None:
    line = _mk_line("[Planet Cyrene, 138260, 76275, 110, Waypoint]")
    ev = chat_interpreter.interpret_chat_line(line)
    assert isinstance(ev, PlayerPosWaypoint)
    assert ev.planet_name == "Planet Cyrene"
    assert (ev.x, ev.y, ev.z) == (138260, 76275, 110)


def test_interpret_system_position_ping_allows_negative_coords() -> None:
    line = _mk_line("[Calypso, -1, 0, -999, Waypoint]")
    ev = chat_interpreter.interpret_chat_line(line)
    assert isinstance(ev, PlayerPosWaypoint)
    assert (ev.x, ev.y, ev.z) == (-1, 0, -999)


def test_interpret_system_skill_gained_decimal() -> None:
    line = _mk_line("You have gained 0.0311 experience in your Extraction skill")
    ev = chat_interpreter.interpret_chat_line(line)
    assert isinstance(ev, SkillGained)
    assert ev.skill == "Extraction"
    assert str(ev.amount) == "0.0311"


def test_interpret_system_enhancer_broke_basic() -> None:
    line = _mk_line(
        "Your enhancer T2 Mining Excavator Speed Enhancer on your Genesis Star Excavator, Improved, TWEN Edition broke."
        " You have 413 enhancers remaining on the item."
    )
    ev = chat_interpreter.interpret_chat_line(line)
    assert isinstance(ev, EnhancerBroke)
    assert ev.enhancer_name == "T2 Mining Excavator Speed Enhancer"
    assert ev.item_name == "Genesis Star Excavator, Improved, TWEN Edition"
    assert ev.remaining == 413


def test_interpret_system_enhancer_broke_with_optional_received_segment_still_parses() -> None:
    line = _mk_line(
        "Your enhancer T2 Mining Excavator Speed Enhancer on your Genesis Star Excavator, Improved, TWEN Edition broke."
        " You have 413 enhancers remaining on the item."
        " You received 0.2000 PED Shrapnel."
    )
    ev = chat_interpreter.interpret_chat_line(line)
    assert isinstance(ev, EnhancerBroke)
    assert ev.remaining == 413


def test_interpret_non_system_channel_returns_none() -> None:
    line = _mk_line(
        "You have claimed a resource! (Yellow Crystal)",
        channel_type=ChannelType.GLOBALS,
        channel_token="Globals",
    )
    assert chat_interpreter.interpret_chat_line(line) is None


def test_interpret_system_skips_matcher_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom:
        def match(self, _s: str):
            raise RuntimeError("boom")

    # Force _try_match_enhancer_broke to explode inside matcher loop
    monkeypatch.setattr(chat_interpreter, "RE_ENHANCER_BROKE", Boom(), raising=True)

    line = _mk_line("This resource is depleted")
    ev = chat_interpreter.interpret_chat_line(line)
    assert isinstance(ev, ResourceDepleted)
