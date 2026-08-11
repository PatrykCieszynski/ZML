from __future__ import annotations

import argparse
import logging
from pathlib import Path

from zml_ocr_worker import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zml-ocr-worker")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("doctor", help="Validate the native OCR runtime and tessdata")
    subcommands.add_parser("stdio", help="Run the NDJSON process protocol on stdin/stdout")

    locate_ui = subcommands.add_parser(
        "locate-ui",
        help="Locate Compass and Finder regions in a captured Entropia client frame",
    )
    locate_ui.add_argument("image", type=Path, help="Full Entropia client screenshot")
    locate_ui.add_argument(
        "--annotated",
        type=Path,
        default=None,
        help="Optional output path for an annotated preview image",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    match args.command:
        case "doctor":
            from zml_ocr_worker.doctor import run_doctor

            return run_doctor()
        case "stdio":
            from zml_ocr_worker.runtime.stdio import run_stdio

            return run_stdio()
        case "locate-ui":
            from zml_ocr_worker.calibration.debug import run_calibration_debug

            return run_calibration_debug(args.image, annotated_path=args.annotated)
    raise RuntimeError(f"Unsupported command: {args.command}")
