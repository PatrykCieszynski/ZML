from __future__ import annotations

import json
from typing import Any

import pytest

from zml_backend.persistence.cloud_sync import PendingCloudClaim
from zml_backend.runtime.cloud_sync import CloudSyncClient, CloudSyncProtocolError


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.status = 200
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _claim(claim_id: str) -> PendingCloudClaim:
    return PendingCloudClaim(
        claim_id=claim_id,
        planet_name="Calypso",
        x=65_000,
        y=80_000,
        resource_name="Belkar Stone",
        size_index=12,
        observed_ts_ms=1_700_000_000_000,
    )


def test_cloud_sync_client_posts_existing_zml_claim_shape(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request, *, timeout: float):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            {
                "accepted": 1,
                "alreadyPresent": 0,
                "rejected": 0,
                "results": [
                    {"claimId": "claim-1", "status": "accepted", "reason": None},
                ],
            }
        )

    monkeypatch.setattr("zml_backend.runtime.cloud_sync.urlopen", fake_urlopen)

    outcomes = CloudSyncClient(
        base_url="http://localhost:8080/",
        token="zml_secret",
    ).upload_claims([_claim("claim-1")])

    assert captured == {
        "url": "http://localhost:8080/api/v1/sync/claims",
        "authorization": "Bearer zml_secret",
        "timeout": 10.0,
        "payload": {
            "claims": [
                {
                    "claimId": "claim-1",
                    "planetName": "Calypso",
                    "x": 65_000,
                    "y": 80_000,
                    "resourceName": "Belkar Stone",
                    "sizeIndex": 12,
                    "observedTsMs": 1_700_000_000_000,
                }
            ]
        },
    }
    assert [(item.claim_id, item.status, item.reason) for item in outcomes] == [
        ("claim-1", "accepted", None)
    ]


def test_cloud_sync_client_rejects_partial_batch_response(monkeypatch) -> None:
    def fake_urlopen(request, *, timeout: float):
        _ = request, timeout
        return _FakeResponse(
            {
                "accepted": 1,
                "alreadyPresent": 0,
                "rejected": 0,
                "results": [
                    {"claimId": "claim-1", "status": "accepted", "reason": None},
                ],
            }
        )

    monkeypatch.setattr("zml_backend.runtime.cloud_sync.urlopen", fake_urlopen)

    client = CloudSyncClient(base_url="http://localhost:8080", token="zml_secret")
    with pytest.raises(CloudSyncProtocolError, match="did not resolve every submitted claim"):
        client.upload_claims([_claim("claim-1"), _claim("claim-2")])
