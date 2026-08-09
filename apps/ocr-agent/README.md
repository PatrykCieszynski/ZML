# ZML OCR Agent

Standalone Windows screen-capture and OCR component for Z Mining Log.

The agent owns the native OCR stack and emits versioned NDJSON messages on
stdout. Logs are written to stderr. Game Bridge can run the agent as a managed
child with `ZML_OCR_TRANSPORT=agent`; the temporary embedded adapter remains the
default rollback path during migration.

```powershell
uv run zml-ocr-agent --version
uv run zml-ocr-agent doctor
uv run zml-ocr-agent stdio
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
