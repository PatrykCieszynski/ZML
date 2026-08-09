from __future__ import annotations

import platform
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from zml_ocr_worker.runtime.paths import get_tessdata_dir
from zml_ocr_worker.runtime.tesserocr import preload_tesserocr_preserving_sigint_handler


def run_doctor(*, output: TextIO = sys.stdout) -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(
        (
            "python",
            sys.version_info >= (3, 13),
            f"{platform.python_version()} ({sys.executable})",
        )
    )
    checks.append(("platform", sys.platform == "win32", platform.platform()))
    checks.append(_run_check("tessdata", _check_tessdata))
    checks.append(_run_check("tesserocr", _check_tesserocr))

    for name, passed, detail in checks:
        state = "ok" if passed else "error"
        print(f"{state:5} {name}: {detail}", file=output)

    return 0 if all(passed for _, passed, _ in checks) else 1


def _run_check(name: str, check: Callable[[], str]) -> tuple[str, bool, str]:
    try:
        return name, True, check()
    except Exception as exc:
        return name, False, str(exc)


def _check_tessdata() -> str:
    tessdata_dir = get_tessdata_dir()
    required = [tessdata_dir / "eng.traineddata", tessdata_dir / "osd.traineddata"]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing {', '.join(missing)} in {tessdata_dir}")
    return str(tessdata_dir)


def _check_tesserocr() -> str:
    module = preload_tesserocr_preserving_sigint_handler()
    version = getattr(module, "__version__", "unknown")
    module_path = getattr(module, "__file__", None)
    return f"{version} ({Path(module_path) if module_path else 'built-in'})"
