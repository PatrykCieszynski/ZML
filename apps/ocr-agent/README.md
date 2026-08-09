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
`shutdown` command or EOF. `ZML_OCR_PROFILE_PATH` selects the startup ROI profile;
revisioned live configuration is handled in the next migration step.
