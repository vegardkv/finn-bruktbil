from __future__ import annotations

from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, Field

from ..db import DEFAULT_DB_PATH

T = TypeVar("T", bound=BaseModel)


class FetchIdsConfig(BaseModel):
    base_url: str
    limit: int = Field(default=200, ge=1)
    max_pages: int = Field(default=25, ge=1)
    db: Path | None = None
    fetched_by: str = Field(default="finn_search")
    headless: bool = True

    @property
    def resolved_db_path(self) -> Path:
        return Path(self.db) if self.db else Path(DEFAULT_DB_PATH)


class DownloadConfig(BaseModel):
    limit: int = Field(default=25, ge=1)
    stale_hours: int | None = Field(default=None, ge=1)
    random_order: bool = False
    db: Path | None = None
    headless: bool = True
    parse_aux_data: bool = Field(default=False, description="Enable parsing of auxiliary data (tire sets, trim level) using OpenAI API")

    @property
    def resolved_db_path(self) -> Path:
        return Path(self.db) if self.db else Path(DEFAULT_DB_PATH)


class AnalyzeConfig(BaseModel):
    db: Path | None = None
    streamlit_args: list[str] = Field(default_factory=list)

    @property
    def resolved_db_path(self) -> Path | None:
        return Path(self.db) if self.db else None


def load_config(path: str | Path, model_cls: Type[T]) -> T:
    config_path = Path(path)
    raw = config_path.read_text(encoding="utf-8")
    if hasattr(model_cls, "model_validate_json"):
        return model_cls.model_validate_json(raw)
    return model_cls.parse_raw(raw)
