from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src" / "zml_backend"


def test_game_bridge_declares_only_protocol_as_ocr_dependency() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    dependency_text = "\n".join(dependencies)

    assert "zml-ocr-protocol" in dependency_text
    forbidden_dependencies = (
        "zml-ocr-worker",
        "mss",
        "numpy",
        "opencv-python",
        "pywin32",
        "tesserocr",
    )
    assert all(package not in dependency_text for package in forbidden_dependencies)


def test_game_bridge_source_never_imports_ocr_worker_package() -> None:
    offenders = [
        path.relative_to(PROJECT_ROOT)
        for path in SOURCE_ROOT.rglob("*.py")
        if "zml_ocr_worker" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_backend_ocr_runtime_contains_only_process_lifecycle_code() -> None:
    runtime_dir = SOURCE_ROOT / "runtime" / "ocr_worker"
    assert {path.name for path in runtime_dir.glob("*.py")} == {
        "__init__.py",
        "process_transport.py",
        "supervisor.py",
    }

    runtime_source = "\n".join(
        path.read_text(encoding="utf-8") for path in runtime_dir.glob("*.py")
    )
    forbidden_imports = (
        "zml_backend.application",
        "zml_backend.domain",
        "zml_backend.events",
        "zml_backend.inputs",
    )
    assert all(module not in runtime_source for module in forbidden_imports)
