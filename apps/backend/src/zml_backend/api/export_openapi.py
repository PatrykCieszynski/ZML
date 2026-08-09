from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from zml_backend.api.app import create_app


def build_openapi_schema() -> dict[str, Any]:
    return create_app().openapi()


def export_openapi_schema(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_openapi_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI schema as JSON.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_openapi_schema(args.output)


if __name__ == "__main__":
    main()
