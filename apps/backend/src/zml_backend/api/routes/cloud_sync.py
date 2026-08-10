from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from zml_backend.api.dependencies import RuntimeDep

router = APIRouter(prefix="/api/v1/runtime/cloud-sync", tags=["runtime"])


class CloudSyncConfigRequest(BaseModel):
    base_url: str | None = None
    token: str | None = None


@router.put("", status_code=status.HTTP_204_NO_CONTENT)
def configure_cloud_sync(request: CloudSyncConfigRequest, runtime: RuntimeDep) -> None:
    base_url = _normalize_optional(request.base_url)
    token = _normalize_optional(request.token)
    if (base_url is None) != (token is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cloud sync base URL and token must be configured together",
        )
    if base_url is not None and not base_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cloud sync base URL must use HTTP or HTTPS",
        )

    runtime.configure_cloud_sync(base_url=base_url, token=token)


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
