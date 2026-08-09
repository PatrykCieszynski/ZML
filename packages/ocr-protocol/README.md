# ZML OCR Protocol

Small versioned wire contract shared by Backend and the standalone OCR
Agent. Version 1 uses strict Pydantic DTOs serialized as UTF-8 NDJSON over
stdin/stdout.

The package owns only:

- message DTOs and their structural validation;
- protocol version and `hello` handshake fields;
- direction-specific encode/decode helpers;
- protocol codec errors and stable serialization fixtures.

It must not import either application, load settings, start processes, perform
screen capture, interpret OCR results as mining behavior, or depend on native
OCR libraries. Backend owns process supervision and domain mapping. OCR
Agent owns capture, recognition pipelines, and application of OCR config.
