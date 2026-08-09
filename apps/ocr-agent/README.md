# ZML OCR Agent

Standalone Windows screen-capture and OCR component for Z Mining Log.

The agent owns the native OCR stack and emits versioned NDJSON messages on
stdout. Logs are written to stderr. Game Bridge currently also imports the same
runner through a temporary embedded adapter while subprocess supervision is
introduced incrementally.

```powershell
uv run zml-ocr-agent --version
uv run zml-ocr-agent doctor
uv run zml-ocr-agent stdio
```

In `stdio` mode the first stdout line is a protocol `hello` message. The process
accepts protocol commands on stdin and exits on a `shutdown` command or EOF.
