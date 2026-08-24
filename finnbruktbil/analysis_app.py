from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Streamlit executes this file as a top-level script, so it has no parent package and
# the relative imports below cannot resolve on their own. Put the repo root on the path
# and name the package (PEP 366) before any of them run. Must stay above the imports.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "finnbruktbil"

# Chart/analysis helpers live in plots.py so the report generator and CI can build
# figures without importing streamlit. Re-exported here for backwards compatibility.
from .plots import (  # noqa: E402, F401
    AXIS_LABELS,
    DISCRETE_COLOR_MODES,
    MIN_OLS_SAMPLES,
    MODEL_YEAR_SENTINEL,
    SKLEARN_AVAILABLE,
    PlotOptions,
    _linear_fit,
    _regression_trace,
    add_derived_columns,
    categorize_import_status,
    categorize_trim,
    make_price_scatter,
    map_tire_sets,
    perform_ols_analysis,
)

from .db import load_ads_dataframe  # noqa: E402


def _series_bounds(series, fallback_min: int = 0, fallback_max: int = 0) -> tuple[int, int]:
    values = series.dropna()
    if values.empty:
        return fallback_min, fallback_max
    lower = int(values.min())
    upper = int(values.max())
    if lower > upper:
        lower, upper = upper, lower
    return lower, upper


def load_data():
    """Load the ads dataframe, stopping the app with a message when unavailable."""
    try:
        data = load_ads_dataframe()
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    if data.empty:
        st.info("The database does not contain any ad details yet. Run the downloader script first.")
        st.stop()

    return data


def apply_sidebar_filters(data) -> tuple[pd.DataFrame, PlotOptions]:
    """Render the sidebar (category filters, plot customization, range sliders)
    and return the filtered subset plus the selected plot options.

    Stops the app when no rows match the filters.
    """
    brand_options = sorted({b for b in data["merke"].dropna().unique() if b})
    selected_brand = st.sidebar.selectbox("Brand", options=["(All)", *brand_options])

    subset = data.copy()
    if selected_brand != "(All)":
        subset = subset[subset["merke"] == selected_brand]

    model_options = sorted({m for m in subset["modell"].dropna().unique() if m})
    selected_model = st.sidebar.selectbox("Model", options=["(All)", *model_options])
    if selected_model != "(All)":
        subset = subset[subset["modell"] == selected_model]

    seats_options = sorted({int(s) for s in subset["seter"].dropna().unique() if s})
    selected_seats = st.sidebar.selectbox("Number of seats", options=["(All)", *seats_options])
    if selected_seats != "(All)":
        subset = subset[subset["seter"] == selected_seats]

    # Trim level filter
    st.sidebar.markdown("**Trim Level**")
    trim_gt_line = st.sidebar.checkbox("GT-Line", value=True)
    trim_exclusive = st.sidebar.checkbox("Exclusive", value=True)
    trim_undetermined = st.sidebar.checkbox("Undetermined", value=True)

    subset["trim_category"] = subset.apply(categorize_trim, axis=1)

    selected_trims = []
    if trim_gt_line:
        selected_trims.append("gt-line")
    if trim_exclusive:
        selected_trims.append("exclusive")
    if trim_undetermined:
        selected_trims.append("undetermined")

    if selected_trims:
        subset = subset[subset["trim_category"].isin(selected_trims)]

    # Import status filter
    st.sidebar.markdown("**Import Status**")
    import_show_imported = st.sidebar.checkbox("Imported", value=True)
    import_show_norwegian = st.sidebar.checkbox("Norwegian", value=True)
    import_show_unknown = st.sidebar.checkbox("Unknown", value=True)

    if "imported" in subset.columns:
        subset["import_category"] = subset["imported"].apply(categorize_import_status)
    else:
        subset["import_category"] = "unknown"

    selected_import_cats = []
    if import_show_imported:
        selected_import_cats.append("imported")
    if import_show_norwegian:
        selected_import_cats.append("norwegian")
    if import_show_unknown:
        selected_import_cats.append("unknown")

    if selected_import_cats:
        subset = subset[subset["import_category"].isin(selected_import_cats)]

    if subset.empty:
        st.warning("No data matches the selected filters.")
        st.stop()

    # Plot customization options
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Plot Customization**")

    available_color_options = [
        "age_years",
        "kilometerstand_km",
        "totalpris",
        "modellår",
        "seter",
        "tire_sets_numeric",
        "imported_numeric",
        "status_numeric",
    ]
    available_size_options = ["None", "kilometerstand_km", "totalpris", "age_years", "modellår"]

    color_column = st.sidebar.selectbox(
        "Color by",
        options=available_color_options,
        index=0,  # Default to age_years
        help="Select which column to use for coloring the data points",
        format_func=lambda x: {
            "age_years": "Age (years)",
            "kilometerstand_km": "Mileage (km)",
            "totalpris": "Price (NOK)",
            "modellår": "Model Year",
            "seter": "Seats",
            "tire_sets_numeric": "Tire Sets",
            "imported_numeric": "Import Status",
            "status_numeric": "Status",
        }.get(x, x),
    )

    size_column = st.sidebar.selectbox(
        "Size by",
        options=available_size_options,
        index=1,  # Default to kilometerstand_km
        help="Select which column to use for sizing the data points",
        format_func=lambda x: {
            "None": "None",
            "kilometerstand_km": "Mileage (km)",
            "totalpris": "Price (NOK)",
            "age_years": "Age (years)",
            "modellår": "Model Year",
        }.get(x, x),
    )

    price_min, price_max = _series_bounds(subset["totalpris"], 0, 0)
    if price_min < price_max:
        price_range = st.sidebar.slider(
            "Price (NOK)",
            price_min,
            price_max,
            value=(price_min, price_max),
        )
        subset = subset[
            (subset["totalpris"].fillna(0) >= price_range[0]) & (subset["totalpris"].fillna(0) <= price_range[1])
        ]
    else:
        st.sidebar.text(f"Price: {price_min:,} NOK")

    mileage_min, mileage_max = _series_bounds(subset["kilometerstand_km"], 0, 0)
    if mileage_min < mileage_max:
        mileage_range = st.sidebar.slider(
            "Mileage (km)",
            mileage_min,
            mileage_max,
            value=(mileage_min, mileage_max),
        )
        subset = subset[
            (subset["kilometerstand_km"].fillna(0) >= mileage_range[0])
            & (subset["kilometerstand_km"].fillna(0) <= mileage_range[1])
        ]
    else:
        st.sidebar.text(f"Mileage: {mileage_min:,} km")

    year_min, year_max = _series_bounds(subset["modellår"], MODEL_YEAR_SENTINEL, MODEL_YEAR_SENTINEL)
    if year_min < year_max:
        year_selection = st.sidebar.slider("Model year", year_min, year_max, (year_min, year_max))
        subset = subset[
            (subset["modellår"].fillna(year_min) >= year_selection[0])
            & (subset["modellår"].fillna(year_max) <= year_selection[1])
        ]
    else:
        st.sidebar.text(f"Model year: {year_min if year_min > MODEL_YEAR_SENTINEL else 'N/A'}")

    return subset, PlotOptions(color_column=color_column, size_column=size_column)


def render_summary_metrics(subset) -> None:
    """Show the matches / available / sold / unknown metric row."""
    if "status" in subset.columns:
        available_count = int(subset["status"].eq("available").sum())
        sold_count = int(subset["status"].eq("sold").sum())
        unknown_count = len(subset) - available_count - sold_count
    else:
        available_count = sold_count = 0
        unknown_count = len(subset)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Matches", len(subset))
    metric_cols[1].metric("Available", available_count)
    metric_cols[2].metric("Sold", sold_count)
    metric_cols[3].metric("Unknown", unknown_count)


def render_ols_section(analysis_subset, metrics, plot_opts: PlotOptions) -> None:
    """Show the OLS model metrics, coefficients, interpretation, and the
    price-vs-usedness plot (see PRICE_MODEL.md)."""
    st.header("📊 Car Price Model Analysis")
    st.markdown("**Model**: Price = c₀ + c₁ × Mileage + c₂ × Age")

    # Display model coefficients and metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("R² Score", f"{metrics['r2']:.3f}")
    with col2:
        st.metric("Mean Absolute Error", f"{metrics['mae']:,.0f} NOK")
    with col3:
        st.metric("RMSE", f"{metrics['rmse']:,.0f} NOK")
    with col4:
        st.metric("Sample Size", len(analysis_subset) if analysis_subset is not None else 0)

    # Display coefficients
    st.subheader("Model Coefficients")
    coeff_col1, coeff_col2, coeff_col3 = st.columns(3)
    with coeff_col1:
        st.metric("Intercept (c₀)", f"{metrics['c0']:,.0f} NOK")
    with coeff_col2:
        st.metric("Mileage Coeff (c₁)", f"{metrics['c1']:.2f} NOK/km")
    with coeff_col3:
        st.metric("Age Coeff (c₂)", f"{metrics['c2']:,.0f} NOK/year")

    # Interpretation
    st.markdown(f"""
    **Model Interpretation:**
    - **Base Price**: {metrics["c0"]:,.0f} NOK (when mileage and age are zero)
    - **Mileage Impact**: Each additional kilometer reduces value by {abs(metrics["c1"]):.2f} NOK
    - **Age Impact**: Each additional year reduces value by {abs(metrics["c2"]):,.0f} NOK
    - **Model Fit**: R² = {metrics["r2"]:.3f} (explains {metrics["r2"] * 100:.1f}% of price variation)
    """)

    # Usedness vs Price plot
    if analysis_subset is None:
        return

    st.subheader("Price vs. Usedness Score")

    fig_usedness = make_price_scatter(
        analysis_subset,
        x="usedness",
        opts=plot_opts,
        extra_hover=["kilometerstand_km", "age_years"],
    )
    fig_usedness.update_layout(title="Car Price vs. Combined Usedness Score")

    # Add regression line: Price = c0 + usedness (perfectly straight line)
    # Since usedness = c1 * mileage + c2 * age, this is the OLS prediction
    usedness_range = analysis_subset.sort_values("usedness")["usedness"].values
    predicted_price = metrics["c0"] + usedness_range
    fig_usedness.add_trace(
        _regression_trace(usedness_range, predicted_price, name="OLS Regression (Price = c₀ + usedness)")
    )

    st.plotly_chart(fig_usedness, use_container_width=True)

    # Add correlation info
    if len(analysis_subset) > 1:
        corr = analysis_subset["usedness"].corr(analysis_subset["totalpris"])
        st.markdown(f"**Correlation between Usedness and Price**: {corr:.3f}")


def render_scatter_sections(subset, plot_opts: PlotOptions) -> None:
    """Show the side-by-side price-vs-mileage and price-vs-registration plots."""
    scatter_cols = st.columns(2)
    with scatter_cols[0]:
        st.subheader("Price vs. Mileage")
        mileage_data = subset.dropna(subset=["kilometerstand_km", "totalpris", "age_years"])

        fig_mileage = make_price_scatter(
            mileage_data,
            x="kilometerstand_km",
            opts=plot_opts,
            extra_hover=["førstegangsregistrert"],
        )

        if len(mileage_data) > 1:
            x_sorted, y_pred = _linear_fit(mileage_data["kilometerstand_km"].values, mileage_data["totalpris"].values)
            fig_mileage.add_trace(_regression_trace(x_sorted, y_pred))

        st.plotly_chart(fig_mileage, use_container_width=True)

    with scatter_cols[1]:
        st.subheader("Price vs. Registration Date")
        reg_data = subset.dropna(subset=["førstegangsregistrert", "totalpris"])

        fig_registration = make_price_scatter(
            reg_data,
            x="førstegangsregistrert",
            opts=plot_opts,
            extra_hover=[],
            continuous_scale="plasma",
        )

        if len(reg_data) > 1:
            # Fit on days since the earliest registration, then convert back to
            # dates for plotting.
            reg_dates = pd.to_datetime(reg_data["førstegangsregistrert"])
            min_date = reg_dates.min()
            days = (reg_dates - min_date).dt.days.values
            days_sorted, y_pred = _linear_fit(days, reg_data["totalpris"].values)
            dates_sorted = min_date + pd.to_timedelta(days_sorted, unit="D")
            fig_registration.add_trace(_regression_trace(dates_sorted, y_pred))

        st.plotly_chart(fig_registration, use_container_width=True)


def render_ads_table(subset, analysis_subset) -> None:
    """Show the sortable table of matching ads, with usedness merged in when
    the OLS analysis produced it."""
    st.subheader("Matching ads")

    display_columns = [
        "ad_id",
        "title",
        "totalpris",
        "kilometerstand_km",
        "age_years",
        "modellår",
        "førstegangsregistrert",
        "bilen_står_i",
        "fetched_at",
        "imported",
        "import_country",
    ]

    display_subset = subset.copy()
    if analysis_subset is not None and "usedness" in analysis_subset.columns:
        # Check if ad_id exists in both dataframes for merging
        if "ad_id" in analysis_subset.columns and "ad_id" in display_subset.columns:
            # Merge usedness scores back to the main subset
            display_subset = display_subset.merge(analysis_subset[["ad_id", "usedness"]], on="ad_id", how="left")
            display_columns.insert(5, "usedness")  # Insert after age_years
        else:
            # If no ad_id for merging, add usedness to all rows that have complete data
            complete_data_mask = (
                display_subset["totalpris"].notna()
                & display_subset["kilometerstand_km"].notna()
                & display_subset["age_years"].notna()
            )
            display_subset.loc[complete_data_mask, "usedness"] = analysis_subset["usedness"].values[
                : len(display_subset[complete_data_mask])
            ]
            display_columns.insert(5, "usedness")

    available_display_columns = [c for c in display_columns if c in display_subset.columns]
    st.dataframe(
        display_subset[available_display_columns].sort_values(by="totalpris", ascending=False),
        use_container_width=True,
    )


def main() -> None:
    st.set_page_config(page_title="FINN Used Car Explorer", layout="wide")
    st.title("FINN Used Car Explorer")
    st.caption("Filter and visualize scraped data from finn.no ads.")

    data = load_data()
    subset, plot_opts = apply_sidebar_filters(data)
    render_summary_metrics(subset)
    subset = add_derived_columns(subset)

    _model, analysis_subset, metrics, _predictions = perform_ols_analysis(subset)
    if metrics is not None:
        render_ols_section(analysis_subset, metrics, plot_opts)
    else:
        st.warning(
            "⚠️ Cannot perform OLS analysis: insufficient data or missing required libraries (scikit-learn recommended)"
        )

    # TODO: Some ideas for further analysis:
    # - Discretize color scales. E.g., milage buckets.
    # - Easy access to ad URL: https://www.finn.no/mobility/item/{ad_id}
    # - The ideal car has: low mileage, recent registration date, low price.
    #   Maybe a combined score could be calculated and visualized? Or that
    #   mileage and age can be combined into a "usedness" score?
    render_scatter_sections(subset, plot_opts)
    render_ads_table(subset, analysis_subset)


if __name__ == "__main__":
    main()
