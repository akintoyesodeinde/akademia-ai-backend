from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str = "-"
    details: dict[str, Any] | list[Any] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
