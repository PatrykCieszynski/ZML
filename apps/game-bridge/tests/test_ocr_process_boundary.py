from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src" / "zml_game_bridge"


def test_game_bridge_has_no_python_dependency_on_ocr_agent() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    uv_sources = pyproject["tool"]["uv"]["sources"]

    assert "zml-ocr-protocol" in "\n".join(dependencies)
    assert all("zml-ocr-agent" not in dependency for dependency in dependencies)
    assert "zml-ocr-agent" not in uv_sources


def test_game_bridge_source_never_imports_ocr_agent_package() -> None:
    offenders = [
        path.relative_to(PROJECT_ROOT)
        for path in SOURCE_ROOT.rglob("*.py")
        if "zml_ocr_agent" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_game_bridge_lock_has_no_ocr_agent_or_native_ocr_dependencies() -> None:
    lockfile = (PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8")
    forbidden_packages = (
        'name = "zml-ocr-agent"',
        'name = "mss"',
        'name = "numpy"',
        'name = "opencv-python"',
        'name = "pywin32"',
        'name = "tesserocr"',
    )

    assert all(package not in lockfile for package in forbidden_packages)


def test_backend_ocr_runtime_contains_only_process_lifecycle_code() -> None:
    runtime_dir = SOURCE_ROOT / "runtime" / "ocr_agent"
    assert {path.name for path in runtime_dir.glob("*.py")} == {
        "__init__.py",
        "process_transport.py",
        "supervisor.py",
    }

    runtime_source = "\n".join(
        path.read_text(encoding="utf-8") for path in runtime_dir.glob("*.py")
    )
    forbidden_imports = (
        "zml_game_bridge.application",
        "zml_game_bridge.domain",
        "zml_game_bridge.events",
        "zml_game_bridge.inputs",
    )
    assert all(module not in runtime_source for module in forbidden_imports)
