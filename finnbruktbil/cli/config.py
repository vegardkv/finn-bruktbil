from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class FetchIdsConfig(BaseModel):
    base_url: str | None = None
    favorites_file: Path | None = None
    limit: int = Field(default=200, ge=1)
    max_pages: int = Field(default=25, ge=1)
    fetched_by: str = Field(default="finn_search")
    headless: bool = True


class DownloadConfig(BaseModel):
    limit: int = Field(default=25, ge=1)
    stale_hours: int | None = Field(default=None, ge=1)
    random_order: bool = False
    headless: bool = True
    parse_aux_data: bool = Field(default=False, description="Enable parsing of auxiliary data (tire sets, trim level) using OpenAI API")


class AnalyzeConfig(BaseModel):
    streamlit_args: list[str] = Field(default_factory=list)


class ConstraintType(StrEnum):
    soft = "soft"
    hard = "hard"


# A constraint is a ``(value, soft|hard)`` pair, or ``None`` when unset. In JSON
# this is a 2-element array, e.g. ``[800000, "hard"]``. ``bool`` is listed before
# ``int`` so JSON ``true``/``false`` is not coerced to an int (bool subclasses int).
Constraint = tuple[bool | int | str, ConstraintType] | None


class CarConstraints(BaseModel):
    merke: str  # e.g. "Kia", matched case-insensitively
    modell: str  # e.g. "EV9", matched case-insensitively
    max_price: Constraint = None
    min_price: Constraint = None
    number_of_seats: Constraint = None
    trim_level: Constraint = None
    imported: Constraint = None  # bool value
    max_mileage: Constraint = None  # km
    color: Constraint = None  # substring of the color description, e.g. "grey"
    # more constraints added here later


def load_config(path: str | Path, model_cls: Type[T]) -> T:
    config_path = Path(path)
    raw = config_path.read_text(encoding="utf-8")
    if hasattr(model_cls, "model_validate_json"):
        return model_cls.model_validate_json(raw)
    return model_cls.parse_raw(raw)
