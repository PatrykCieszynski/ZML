from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from zml_ocr_protocol import (
    AgentToBridgeMessage,
    BridgeToAgentMessage,
    decode_agent_message,
    decode_bridge_message,
    encode_message,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SOURCE_DIR = Path(__file__).parents[1] / "src" / "zml_ocr_protocol"


@pytest.mark.parametrize(
    ("filename", "decoder"),
    [
        ("agent_messages.ndjson", decode_agent_message),
        ("bridge_messages.ndjson", decode_bridge_message),
    ],
)
def test_fixture_lines_have_stable_canonical_encoding(
    filename: str,
    decoder: Callable[[bytes], AgentToBridgeMessage | BridgeToAgentMessage],
) -> None:
    lines = (FIXTURE_DIR / filename).read_bytes().splitlines(keepends=True)
    assert lines
    for checkout_line in lines:
        canonical_line = (
            checkout_line[:-2] + b"\n" if checkout_line.endswith(b"\r\n") else checkout_line
        )
        assert encode_message(decoder(canonical_line)) == canonical_line


def test_import_does_not_load_native_ocr_dependencies() -> None:
    code = """
import sys
import zml_ocr_protocol

blocked = {"cv2", "mss", "numpy", "tesserocr", "win32api", "win32gui"}
loaded = blocked.intersection(sys.modules)
if loaded:
    raise SystemExit(f"native OCR modules loaded: {sorted(loaded)}")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_protocol_source_does_not_import_either_application() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE_DIR.glob("*.py"))

    assert "zml_game_bridge" not in source
    assert "zml_ocr_agent" not in source
