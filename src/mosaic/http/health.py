"""Process-availability HTTP operation."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Stable machine-readable health document."""

    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the Mosaic application process is available."""
    return HealthResponse()


__all__ = ["router"]
