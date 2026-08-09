from __future__ import annotations


class OcrProtocolError(Exception):
    """Base class for OCR protocol codec errors."""


class MalformedMessageError(OcrProtocolError):
    """Raised when a line is not a single UTF-8 JSON object."""


class MessageValidationError(OcrProtocolError):
    """Raised when JSON does not match the expected message schema."""


class MessageTooLargeError(OcrProtocolError):
    """Raised when an NDJSON line exceeds the configured byte limit."""

    def __init__(self, *, actual_bytes: int, max_bytes: int) -> None:
        self.actual_bytes = actual_bytes
        self.max_bytes = max_bytes
        super().__init__(f"OCR protocol line is {actual_bytes} bytes; maximum is {max_bytes}")


class UnsupportedProtocolVersionError(OcrProtocolError):
    """Raised before message validation when the wire version is incompatible."""

    def __init__(
        self,
        *,
        received_version: int,
        supported_versions: tuple[int, ...] = (1,),
    ) -> None:
        self.received_version = received_version
        self.supported_versions = supported_versions
        supported = ", ".join(str(version) for version in supported_versions)
        super().__init__(
            f"Unsupported OCR protocol version {received_version}; supported versions: {supported}"
        )
