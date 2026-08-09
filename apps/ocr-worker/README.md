# ZML OCR Worker

Standalone Windows screen-capture and OCR component for Z Mining Log.

The agent owns the native OCR stack and emits versioned NDJSON messages on
stdout. Logs are written to stderr. Backend always runs it as a managed
child process and never imports this Python package.

```powershell
uv run zml-ocr-worker --version
uv run zml-ocr-worker doctor
uv run zml-ocr-worker stdio
just package
```

In `stdio` mode the first stdout line is a protocol `hello` message. The process
emits periodic heartbeats, accepts protocol commands on stdin, and exits on a
`shutdown` command or EOF. It waits for a complete revisioned `apply_config`
snapshot before starting capture and OCR. Repeating the same revision with the
same values is idempotent; stale revisions and conflicting values for an already
applied revision are rejected. Backend owns the desired snapshot and sends
it again after every process restart.

The OCR Worker and Backend runtimes are pinned to Python 3.13 because the
Windows `tesserocr` dependency is distributed as a CPython 3.13 wheel.

`just package` creates `dist/zml-ocr-worker/zml-ocr-worker.exe` together with its
private native OCR libraries and tessdata. Backend packaging intentionally
does not contain those files.

The application is organized around the OCR pipeline rather than backend DDD
layers:

- `capture/`: Windows capture and capture models;
- `pipelines/`: position/finder preprocessing, recognition, and observations;
- `runtime/`: stdio command loop, runner lifecycle, message creation, profiling,
  native Tesseract initialization, and runtime paths;
- `config.py`: applied OCR configuration and ROI profile conversion;
- `cli.py`, `doctor.py`, and `finder_debug.py`: process entrypoints and tools.
