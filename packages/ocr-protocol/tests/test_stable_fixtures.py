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
    for line in lines:
        assert encode_message(decoder(line)) == line


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
