"""Generate a single static HTML report (summarize tables + Plotly charts).

The output is a self-contained ``index.html`` suitable for GitHub Pages: it reuses
``summarize_cars`` for the tables and the shared chart helpers in ``plots.py`` for
three interactive Plotly figures, pre-filtered to the configured make/model.
"""

from __future__ import annotations

import argparse
import html
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from ..db import load_ads_dataframe
from ..plots import (
    PlotOptions,
    _linear_fit,
    _regression_trace,
    add_derived_columns,
    make_price_scatter,
    perform_ols_analysis,
)
from .config import ReportConfig, load_config
from .summarize import ConstraintStat, SummaryResult, _notna, filter_model, summarize_cars

if TYPE_CHECKING:  # pragma: no cover - typing only
    import plotly.graph_objects as go

logger = logging.getLogger(__name__)

FINN_ITEM_URL = "https://www.finn.no/mobility/item/{ad_id}"

# Points are colored by availability (available / sold / unknown); see
# DISCRETE_COLOR_MODES["status_numeric"] in plots.py.
PLOT_OPTS = PlotOptions(color_column="status_numeric", size_column="None")

STYLE = """<style>
  :root { color-scheme: light dark; }
  body {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    max-width: 1100px; margin: 0 auto; padding: 1.5rem; line-height: 1.5;
  }
  h1 { margin-bottom: 0.2rem; }
  .generated { color: #666; font-size: 0.9rem; margin-top: 0; }
  .headline { display: flex; flex-wrap: wrap; gap: 1rem; margin: 1.2rem 0; }
  .headline .card {
    flex: 1 1 180px; border: 1px solid #ddd; border-radius: 8px; padding: 0.8rem 1rem;
  }
  .headline .num { font-size: 1.8rem; font-weight: 600; }
  .headline .label { color: #666; font-size: 0.85rem; }
  table { border-collapse: collapse; width: 100%; margin: 0.5rem 0 1.5rem; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e5e5e5; }
  th { background: rgba(127, 127, 127, 0.12); }
  tbody tr:nth-child(even) { background: rgba(127, 127, 127, 0.05); }
  .note { color: #666; font-style: italic; margin: 0.5rem 0 1.5rem; }
  .chart { margin: 0.5rem 0 1.5rem; }
  .chart .caption { color: #666; font-size: 0.85rem; margin-top: 0.2rem; }
</style>"""


def _fmt_price(value: Any) -> str:
    return f"{int(value):,} kr".replace(",", " ") if _notna(value) else "—"


def _fmt_int(value: Any) -> str:
    return f"{int(value)}" if _notna(value) else "—"


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _render_headline(summary: SummaryResult) -> str:
    cards = [
        (summary.model_count, "cars found for make/model"),
        (len(summary.feasible_sorted), "fit all hard constraints (all time)"),
        (len(summary.available_sorted), "currently available &amp; feasible"),
    ]
    items = "".join(
        f'<div class="card"><div class="num">{num}</div><div class="label">{label}</div></div>' for num, label in cards
    )
    return f'<div class="headline">{items}</div>'


def _render_constraint_table(stats: list[ConstraintStat], model_count: int) -> str:
    if not stats:
        return ""
    rows = "".join(
        "<tr>"
        f"<td>{_esc(st.ctype)}</td>"
        f"<td>{_esc(st.field)}</td>"
        f"<td>{_esc(st.value)}</td>"
        f"<td>{st.satisfied}</td>"
        f"<td>{st.missing}</td>"
        "</tr>"
        for st in stats
    )
    return (
        f"<h2>Constraints (of {model_count} found cars)</h2>"
        "<table><thead><tr>"
        "<th>Type</th><th>Constraint</th><th>Value</th><th>Satisfied</th><th>Missing data</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _render_car_table(title: str, cars: list[tuple[pd.Series, int]]) -> str:
    header = f"<h2>{_esc(title)} ({len(cars)})</h2>"
    if not cars:
        return header + '<p class="note">No matching cars.</p>'

    rows = []
    for car, score in cars:
        ad_id = car.get("ad_id")
        car_title = car.get("title") or f"{car.get('merke', '')} {car.get('modell', '')}".strip()
        if _notna(ad_id):
            link = FINN_ITEM_URL.format(ad_id=ad_id)
            title_cell = f'<a href="{_esc(link)}" target="_blank" rel="noopener">{_esc(car_title)}</a>'
        else:
            title_cell = _esc(car_title)
        rows.append(
            "<tr>"
            f"<td>{score}</td>"
            f"<td>{title_cell}</td>"
            f"<td>{_fmt_price(car.get('totalpris'))}</td>"
            f"<td>{_fmt_int(car.get('seter'))}</td>"
            f"<td>{_fmt_int(car.get('kilometerstand_km'))}</td>"
            f"<td>{_fmt_int(car.get('modellår'))}</td>"
            f"<td>{_esc(car.get('status', '—'))}</td>"
            "</tr>"
        )
    return (
        header + "<table><thead><tr>"
        "<th>Score</th><th>Title</th><th>Price</th><th>Seats</th>"
        "<th>Mileage (km)</th><th>Model year</th><th>Status</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _fig_to_div(fig: go.Figure, include_js: bool) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=("cdn" if include_js else False))


def _build_charts(model_df: pd.DataFrame) -> str:
    """Return the HTML for the price charts, in order. The first emitted figure
    carries the plotly.js CDN tag; later ones reuse it. Degrades to a note when
    there is not enough data."""

    sections: list[str] = []
    js_pending = True

    def emit(heading: str, fig: go.Figure, caption: str = "") -> None:
        nonlocal js_pending
        cap = f'<div class="caption">{caption}</div>' if caption else ""
        sections.append(f'<div class="chart"><h2>{html.escape(heading)}</h2>{_fig_to_div(fig, js_pending)}{cap}</div>')
        js_pending = False

    def note(heading: str, message: str) -> None:
        sections.append(
            f'<div class="chart"><h2>{html.escape(heading)}</h2><p class="note">{html.escape(message)}</p></div>'
        )

    # 1) Price vs. usedness (OLS-derived), with the regression line.
    _model, analysis_data, metrics, _pred = perform_ols_analysis(model_df)
    if metrics is not None:
        fig = make_price_scatter(
            analysis_data, x="usedness", opts=PLOT_OPTS, extra_hover=["kilometerstand_km", "age_years"]
        )
        usedness = analysis_data.sort_values("usedness")["usedness"].values
        fig.add_trace(_regression_trace(usedness, metrics["c0"] + usedness, name="OLS (Price = c₀ + usedness)"))
        caption = (
            f"R² = {metrics['r2']:.3f} · mileage {metrics['c1']:.2f} NOK/km · "
            f"age {metrics['c2']:,.0f} NOK/year".replace(",", " ")
        )
        emit("Price vs. usedness", fig, caption)
    else:
        note("Price vs. usedness", "Not enough data to fit the price model (need at least 10 complete rows).")

    # 2) Price vs. mileage, with a linear fit.
    mileage_data = model_df.dropna(subset=["kilometerstand_km", "totalpris", "age_years"])
    if not mileage_data.empty:
        fig = make_price_scatter(
            mileage_data, x="kilometerstand_km", opts=PLOT_OPTS, extra_hover=["førstegangsregistrert"]
        )
        if len(mileage_data) > 1:
            x_sorted, y_pred = _linear_fit(mileage_data["kilometerstand_km"].values, mileage_data["totalpris"].values)
            fig.add_trace(_regression_trace(x_sorted, y_pred))
        emit("Price vs. mileage", fig)
    else:
        note("Price vs. mileage", "No cars with both price and mileage.")

    # 3) Price vs. registration date, with a linear fit (fit on days since earliest).
    reg_data = model_df.dropna(subset=["førstegangsregistrert", "totalpris"])
    if not reg_data.empty:
        fig = make_price_scatter(
            reg_data, x="førstegangsregistrert", opts=PLOT_OPTS, extra_hover=[], continuous_scale="plasma"
        )
        if len(reg_data) > 1:
            reg_dates = pd.to_datetime(reg_data["førstegangsregistrert"])
            min_date = reg_dates.min()
            days = (reg_dates - min_date).dt.days.values
            days_sorted, y_pred = _linear_fit(days, reg_data["totalpris"].values)
            dates_sorted = min_date + pd.to_timedelta(days_sorted, unit="D")
            fig.add_trace(_regression_trace(dates_sorted, y_pred))
        emit("Price vs. registration date", fig)
    else:
        note("Price vs. registration date", "No cars with both price and registration date.")

    return "".join(sections)


def _render_page(title: str, summary: SummaryResult, charts_html: str) -> str:
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(title)}</title>{STYLE}</head><body>"
        f"<h1>{_esc(title)}</h1>"
        f'<p class="generated">Generated at {generated}</p>'
        f"{_render_headline(summary)}"
        f"{_render_constraint_table(summary.constraint_stats, summary.model_count)}"
        f"{charts_html}"
        f"{_render_car_table('Best fits (all time)', summary.feasible_sorted)}"
        f"{_render_car_table('Best fits (currently available)', summary.available_sorted)}"
        "</body></html>\n"
    )


def generate_report(config: ReportConfig) -> Path:
    """Build the report page for ``config`` and write it to ``output_dir/index.html``.
    Returns the written path."""

    df = load_ads_dataframe()
    summary = summarize_cars(config.constraints, df)

    model_df = filter_model(df, config.constraints.merke, config.constraints.modell)
    model_df = add_derived_columns(model_df)
    charts_html = _build_charts(model_df)

    title = config.title or f"{config.constraints.merke} {config.constraints.modell} report"
    page = _render_page(title, summary, charts_html)

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "index.html"
    output_path.write_text(page, encoding="utf-8")
    logger.info("Wrote report to %s", output_path)
    return output_path


# --- CLI wiring ----------------------------------------------------------------


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "report",
        help="Generate a static HTML report for GitHub Pages",
        description="Render the summarize results plus Plotly charts to a static index.html.",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Path to a JSON config file (ReportConfig).",
    )
    parser.set_defaults(func=run)
    return parser


def run(args: argparse.Namespace) -> int:
    config = load_config(args.config, ReportConfig)
    generate_report(config)
    return 0
