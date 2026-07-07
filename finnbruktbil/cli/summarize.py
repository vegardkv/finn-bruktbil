from __future__ import annotations

import argparse
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..db import load_ads_dataframe
from .config import CarConstraints, ConstraintType, load_config

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd


# --- Per-constraint evaluators -------------------------------------------------
#
# Each evaluator answers "does this car satisfy the constraint value?" as a
# tri-state: ``True`` (satisfied), ``False`` (data present but fails), or ``None``
# (the field is missing, so the constraint can't be judged). They also encapsulate
# the mapping from English config field names to the Norwegian DataFrame columns.
# Adding a new constraint = add a field to ``CarConstraints`` + a ``_eval_*`` fn +
# one registry line below; the scoring/aggregation loop stays untouched.


def _notna(value: Any) -> bool:
    import pandas as pd

    return value is not None and not pd.isna(value)


def _alnum(value: Any) -> str:
    """Lowercase and strip all non-alphanumeric chars, so "GT-Line" == "gt line"."""

    return re.sub(r"[^0-9a-z]", "", str(value).lower())


def _eval_max_price(car: pd.Series, value: Any) -> bool | None:
    price = car.get("totalpris")
    return price <= value if _notna(price) else None


def _eval_min_price(car: pd.Series, value: Any) -> bool | None:
    price = car.get("totalpris")
    return price >= value if _notna(price) else None


def _eval_number_of_seats(car: pd.Series, value: Any) -> bool | None:
    seats = car.get("seter")
    return seats >= value if _notna(seats) else None


def _eval_trim_level(car: pd.Series, value: Any) -> bool | None:
    trim = car.get("trim_level")
    if not _notna(trim):
        return None
    return _alnum(trim) == _alnum(value)


def _eval_imported(car: pd.Series, value: Any) -> bool | None:
    imported = car.get("imported")
    return bool(imported) == bool(value) if _notna(imported) else None


def _eval_max_mileage(car: pd.Series, value: Any) -> bool | None:
    mileage = car.get("kilometerstand_km")
    return mileage <= value if _notna(mileage) else None


# Groups of interchangeable color terms (spelling / Norwegian variants). A color
# constraint value is expanded to its group, then any alias is substring-matched
# against the color description, so "grey" also catches "gray"/"grå". Values not
# in any group match only themselves.
COLOR_ALIASES: tuple[tuple[str, ...], ...] = (
    ("black", "svart"),
    ("white", "hvit"),
    ("grey", "gray", "grå", "gra"),
    ("silver", "sølv", "solv"),
    ("blue", "blå", "bla"),
    ("red", "rød", "rod"),
    ("green", "grønn", "gronn"),
)


def _color_aliases(value: str) -> tuple[str, ...]:
    value = value.strip().lower()
    for group in COLOR_ALIASES:
        if value in group:
            return group
    return (value,)


def _eval_color(car: pd.Series, value: Any) -> bool | None:
    # Substring match against the free-text color description, so "grey" catches
    # "Pebble Grey Metallic" (plus its aliases via COLOR_ALIASES). Falls back to the
    # normalized "farge" code when the description is missing or doesn't match.
    aliases = _color_aliases(str(value))
    has_data = False
    for source in (car.get("fargebeskrivelse"), car.get("farge")):
        if not _notna(source):
            continue
        has_data = True
        text = str(source).lower()
        if any(alias in text for alias in aliases):
            return True
    return False if has_data else None


# Registry: config field name -> evaluator.
CONSTRAINT_EVALUATORS: dict[str, Callable[[pd.Series, Any], bool | None]] = {
    "max_price": _eval_max_price,
    "min_price": _eval_min_price,
    "number_of_seats": _eval_number_of_seats,
    "trim_level": _eval_trim_level,
    "imported": _eval_imported,
    "max_mileage": _eval_max_mileage,
    "color": _eval_color,
}


# --- Scoring -------------------------------------------------------------------


def _active_constraints(config: CarConstraints) -> list[tuple[str, Any, ConstraintType]]:
    """The constraints that are set on the config, as ``(field, value, type)``."""

    active = []
    for field in CONSTRAINT_EVALUATORS:
        constraint = getattr(config, field)
        if constraint is None:
            continue
        value, ctype = constraint
        active.append((field, value, ctype))
    return active


def evaluate_car(
    car: pd.Series, active: list[tuple[str, Any, ConstraintType]]
) -> tuple[bool, int, dict[str, bool | None]]:
    """Return ``(passes_all_hard, soft_score, results)`` for a single car, where
    ``results`` maps each active constraint field to its tri-state evaluator output
    (``True`` satisfied, ``False`` fails, ``None`` missing data)."""

    passes_hard = True
    soft_score = 0
    results: dict[str, bool | None] = {}
    for field, value, ctype in active:
        result = CONSTRAINT_EVALUATORS[field](car, value)
        results[field] = result
        satisfied = result is True
        if ctype == ConstraintType.hard:
            passes_hard = passes_hard and satisfied
        elif satisfied:
            soft_score += 1
    return passes_hard, soft_score, results


@dataclass
class ConstraintStat:
    field: str
    ctype: ConstraintType
    value: Any
    satisfied: int  # cars for which the field is present and satisfies the constraint
    missing: int  # cars left out because the field is missing


@dataclass
class SummaryResult:
    model_count: int  # cars found for the requested make/model
    constraint_stats: list[ConstraintStat]
    feasible_sorted: list[tuple[pd.Series, int]]  # all time, (car, score) desc by score
    available_sorted: list[tuple[pd.Series, int]]  # currently available (status == "available")


def summarize_cars(config: CarConstraints) -> SummaryResult:
    """Filter scraped ads to the target model, drop hard-constraint failures,
    score the survivors by soft constraints met, and split by availability.
    Also tally, per constraint, how many cars satisfy it vs. lack the data."""

    active = _active_constraints(config)
    df = load_ads_dataframe()
    if df.empty:
        return SummaryResult(0, [], [], [])

    model_df = df[
        df["merke"].fillna("").str.strip().str.lower().eq(config.merke.strip().lower())
        & df["modell"].fillna("").str.strip().str.lower().eq(config.modell.strip().lower())
    ]

    tallies = {field: {"satisfied": 0, "missing": 0} for field, _, _ in active}
    feasible: list[tuple[pd.Series, int]] = []
    for _, car in model_df.iterrows():
        passes_hard, score, results = evaluate_car(car, active)
        for field, result in results.items():
            if result is None:
                tallies[field]["missing"] += 1
            elif result:
                tallies[field]["satisfied"] += 1
        if passes_hard:
            feasible.append((car, score))

    feasible.sort(key=lambda cs: cs[1], reverse=True)
    available = [(car, score) for car, score in feasible if car.get("status") == "available"]

    constraint_stats = [
        ConstraintStat(field, ctype, value, tallies[field]["satisfied"], tallies[field]["missing"])
        for field, value, ctype in active
    ]

    return SummaryResult(len(model_df), constraint_stats, feasible, available)


# --- Presentation --------------------------------------------------------------


def _format_car_line(car: pd.Series, score: int) -> str:
    title = car.get("title") or f"{car.get('merke', '')} {car.get('modell', '')}".strip()
    price = car.get("totalpris")
    price_str = f"{int(price)} kr" if _notna(price) else "pris ukjent"
    seats = car.get("seter")
    seats_str = f"{int(seats)} seter" if _notna(seats) else "? seter"
    ad_id = car.get("ad_id", "?")
    url = f"https://www.finn.no/mobility/item/{ad_id}"
    return f"score={score} | {title} | {price_str} | {seats_str} | {url}"


def _print_list(title: str, cars: list[tuple[pd.Series, int]]) -> None:
    print(f"\n{title} ({len(cars)}):")
    for car, score in cars:
        print(f"  {_format_car_line(car, score)}")


def print_summary(result: SummaryResult) -> None:
    print(f"{result.model_count} cars found for the given make/model")
    print(f"{len(result.feasible_sorted)} fit all hard constraints (all time)")
    print(f"{len(result.available_sorted)} currently available fit all hard constraints")

    if result.constraint_stats:
        print(f"\nPer-constraint (of {result.model_count} found cars):")
        for st in result.constraint_stats:
            print(f"  [{st.ctype}] {st.field}={st.value!r}: {st.satisfied} satisfied, {st.missing} missing data")

    _print_list("Best fits (all time)", result.feasible_sorted)
    _print_list("Best fits (currently available)", result.available_sorted)


# --- CLI wiring ----------------------------------------------------------------


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "summarize",
        help="Summarize feasible cars against constraints",
        description="Summarize scraped cars that satisfy a set of soft/hard constraints.",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Path to a JSON config file describing car constraints.",
    )
    parser.set_defaults(func=run)
    return parser


def run(args: argparse.Namespace) -> int:
    config = load_config(args.config, CarConstraints)
    result = summarize_cars(config)
    print_summary(result)
    return 0
