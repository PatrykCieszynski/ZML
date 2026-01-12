from zml_game_bridge.inputs.chat.model import ChannelKind
from zml_game_bridge.inputs.chat.parser import parse_chat_line


def test_parse_system_claim_found():
    raw = "2026-01-10 12:37:50 [System] [] You have claimed a resource! (Yellow Crystal)\n"
    cl = parse_chat_line(raw, seq=1, observed_wall_ts_ms=123)
    assert cl is not None
    assert cl.channel_kind == ChannelKind.SYSTEM
    assert cl.speaker == ""
    assert "claimed a resource" in cl.message


def test_skip_non_header_line():
    raw = "Time left before next batch: 21 hour(s), 47 minute(s).\n"
    cl = parse_chat_line(raw, seq=2, observed_wall_ts_ms=123)
    assert cl is None
