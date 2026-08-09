from __future__ import annotations

from fastapi import APIRouter

from zml_backend.api.dependencies import RuntimeDep
from zml_backend.api.schemas.health import HealthDto

router = APIRouter()


@router.get("/health", response_model=HealthDto)
def health(runtime: RuntimeDep) -> HealthDto:
    return HealthDto.model_validate(runtime.health())
