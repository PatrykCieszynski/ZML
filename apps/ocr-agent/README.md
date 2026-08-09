# ZML OCR Agent

Standalone Windows screen-capture and OCR component for Z Mining Log.

The agent owns the native OCR stack and emits versioned NDJSON messages on
stdout. Logs are written to stderr. Game Bridge always runs it as a managed
child process and never imports this Python package.

```powershell
uv run zml-ocr-agent --version
uv run zml-ocr-agent doctor
uv run zml-ocr-agent stdio
just package
```

In `stdio` mode the first stdout line is a protocol `hello` message. The process
emits periodic heartbeats, accepts protocol commands on stdin, and exits on a
`shutdown` command or EOF. It waits for a complete revisioned `apply_config`
snapshot before starting capture and OCR. Repeating the same revision with the
same values is idempotent; stale revisions and conflicting values for an already
applied revision are rejected. Game Bridge owns the desired snapshot and sends
it again after every process restart.

The OCR Agent and Game Bridge runtimes are pinned to Python 3.13 because the
Windows `tesserocr` dependency is distributed as a CPython 3.13 wheel.

`just package` creates `dist/zml-ocr-agent/zml-ocr-agent.exe` together with its
private native OCR libraries and tessdata. Game Bridge packaging intentionally
does not contain those files.

The application is organized around the OCR pipeline rather than backend DDD
layers:

- `capture/`: Windows capture and capture models;
- `pipelines/`: position/finder preprocessing, recognition, and observations;
- `runtime/`: stdio command loop, runner lifecycle, message creation, profiling,
  native Tesseract initialization, and runtime paths;
- `config.py`: applied OCR configuration and ROI profile conversion;
- `cli.py`, `doctor.py`, and `finder_debug.py`: process entrypoints and tools.
