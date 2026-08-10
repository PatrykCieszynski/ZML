from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from zml_backend.persistence.cloud_sync import (
    CloudClaimSyncStore,
    CloudRemoteStatus,
    CloudSyncOutcome,
    PendingCloudClaim,
)
from zml_backend.persistence.sqlite import open_read_connection
from zml_backend.runtime.channels import ChannelClosedError
from zml_backend.runtime.db_commands import DbCommand, DbCommandChannel

logger = logging.getLogger(__name__)


class CloudSyncError(Exception):
    pass


class CloudSyncHttpError(CloudSyncError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"Cloud sync HTTP request failed with status {status_code}")
        self.status_code = status_code


class CloudSyncTransportError(CloudSyncError):
    pass


class CloudSyncProtocolError(CloudSyncError):
    pass


class CloudSyncClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_s: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout_s = timeout_s

    def upload_claims(self, claims: list[PendingCloudClaim]) -> list[CloudSyncOutcome]:
        payload = {
            "claims": [
                {
                    "claimId": claim.claim_id,
                    "planetName": claim.planet_name,
                    "x": claim.x,
                    "y": claim.y,
                    "resourceName": claim.resource_name,
                    "sizeIndex": claim.size_index,
                    "observedTsMs": claim.observed_ts_ms,
                }
                for claim in claims
            ]
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(
            f"{self._base_url}/api/v1/sync/claims",
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "ZML-Desktop/0.1",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self._timeout_s) as response:
                status_code = int(response.status)
                response_body = response.read()
        except HTTPError as exc:
            raise CloudSyncHttpError(exc.code) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise CloudSyncTransportError("Cloud sync request could not reach the server") from exc

        if status_code < 200 or status_code >= 300:
            raise CloudSyncHttpError(status_code)

        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CloudSyncProtocolError("Cloud sync response was not valid JSON") from exc

        return _parse_outcomes(decoded, claims)


class CloudSyncWorker:
    def __init__(
        self,
        *,
        db_path: Path,
        pending_db_commands: DbCommandChannel,
        client: CloudSyncClient,
        interval_s: float,
        batch_size: int,
    ) -> None:
        self._db_path = db_path
        self._pending_db_commands = pending_db_commands
        self._client = client
        self._interval_s = max(5.0, interval_s)
        self._batch_size = max(1, min(250, batch_size))

    def run(self, *, stop_event: threading.Event) -> None:
        logger.info(
            "cloud_sync_started interval_s=%s batch_size=%s",
            self._interval_s,
            self._batch_size,
        )
        while not stop_event.is_set():
            try:
                synced_count = self.sync_once()
            except ChannelClosedError:
                if stop_event.is_set():
                    break
                logger.exception("cloud_sync_db_channel_closed")
            except CloudSyncHttpError as exc:
                logger.warning("cloud_sync_http_failed status_code=%s", exc.status_code)
            except CloudSyncTransportError:
                logger.warning("cloud_sync_transport_failed")
            except CloudSyncProtocolError:
                logger.exception("cloud_sync_protocol_failed")
            except Exception:
                logger.exception("cloud_sync_failed")
            else:
                if synced_count:
                    logger.info("cloud_sync_completed claims=%s", synced_count)

            stop_event.wait(self._interval_s)
        logger.info("cloud_sync_stopped")

    def sync_once(self) -> int:
        claims = self._read_pending_claims()
        if not claims:
            return 0

        outcomes = self._client.upload_claims(claims)
        command = RecordCloudSyncOutcomesCommand(
            outcomes=tuple(outcomes),
            updated_ts_ms=_now_ms(),
        )
        self._pending_db_commands.execute(command, timeout_s=10.0)
        return len(outcomes)

    def _read_pending_claims(self) -> list[PendingCloudClaim]:
        conn = open_read_connection(self._db_path)
        try:
            return CloudClaimSyncStore(conn).list_pending(limit=self._batch_size)
        finally:
            conn.close()


@dataclass(frozen=True, slots=True)
class RecordCloudSyncOutcomesCommand(DbCommand[None]):
    outcomes: tuple[CloudSyncOutcome, ...]
    updated_ts_ms: int

    def execute(self, conn: sqlite3.Connection) -> None:
        CloudClaimSyncStore(conn).record_outcomes(
            self.outcomes,
            updated_ts_ms=self.updated_ts_ms,
        )


def _parse_outcomes(
    payload: Any,
    claims: list[PendingCloudClaim],
) -> list[CloudSyncOutcome]:
    if not isinstance(payload, dict):
        raise CloudSyncProtocolError("Cloud sync response must be an object")
    response = cast(dict[str, object], payload)

    raw_results = response.get("results")
    if not isinstance(raw_results, list):
        raise CloudSyncProtocolError("Cloud sync response is missing results")
    results = cast(list[object], raw_results)

    expected_ids = {claim.claim_id for claim in claims}
    if len(expected_ids) != len(claims):
        raise CloudSyncProtocolError("Cloud sync batch contains duplicate local claim IDs")

    outcomes: list[CloudSyncOutcome] = []
    seen_ids: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            raise CloudSyncProtocolError("Cloud sync result item must be an object")
        result = cast(dict[str, object], item)

        claim_id = result.get("claimId")
        status = result.get("status")
        reason = result.get("reason")
        if not isinstance(claim_id, str) or claim_id not in expected_ids:
            raise CloudSyncProtocolError("Cloud sync response contains an unexpected claim ID")
        if claim_id in seen_ids:
            raise CloudSyncProtocolError("Cloud sync response contains a duplicate claim ID")
        if not isinstance(status, str) or status not in {"accepted", "already_present", "rejected"}:
            raise CloudSyncProtocolError("Cloud sync response contains an invalid status")
        if reason is not None and not isinstance(reason, str):
            raise CloudSyncProtocolError("Cloud sync response contains an invalid reason")

        seen_ids.add(claim_id)
        outcomes.append(
            CloudSyncOutcome(
                claim_id=claim_id,
                status=_remote_status(status),
                reason=reason,
            )
        )

    if seen_ids != expected_ids:
        raise CloudSyncProtocolError("Cloud sync response did not resolve every submitted claim")
    return outcomes


def _remote_status(value: str) -> CloudRemoteStatus:
    if value == "accepted":
        return "accepted"
    if value == "already_present":
        return "already_present"
    if value == "rejected":
        return "rejected"
    raise AssertionError(f"Unexpected cloud sync status: {value}")


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
