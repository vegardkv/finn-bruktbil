from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# Add parent directory to path to support both direct execution and module import
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from finnbruktbil.db import load_ads_dataframe
else:
    from .db import load_ads_dataframe


# Sentinel year used when the data contains no model years at all.
MODEL_YEAR_SENTINEL = 1900
# Minimum rows with price/mileage/age required to fit the OLS model.
MIN_OLS_SAMPLES = 10


def _series_bounds(series, fallback_min: int = 0, fallback_max: int = 0) -> tuple[int, int]:
    values = series.dropna()
    if values.empty:
        return fallback_min, fallback_max
    lower = int(values.min())
    upper = int(values.max())
    if lower > upper:
        lower, upper = upper, lower
    return lower, upper


# Shared axis/hover labels for all plots; plotly only applies the entries whose
# columns are actually in use.
AXIS_LABELS = {
    "usedness": "Usedness Score (0=New, 1=Most Used)",
    "totalpris": "Price (NOK)",
    "age_years": "Age (years)",
    "kilometerstand_km": "Mileage (km)",
    "modellår": "Model Year",
    "seter": "Seats",
    "førstegangsregistrert": "First Registration",
    "tire_sets_numeric": "Tire Sets",
    "tire_sets_cat": "Tire Sets",
    "import_status_cat": "Import Status",
    "import_country": "Import Country",
    "status": "Status",
}

# Discrete color modes keyed by the sidebar's "Color by" option: which categorical
# column to color by, its extra hover columns, category order, and color map.
# Any other option colors by that column directly on a continuous scale.
DISCRETE_COLOR_MODES = {
    "tire_sets_numeric": {
        "column": "tire_sets_cat",
        "hover": ["tire_sets_cat"],
        "category_order": ["unknown", "one_set", "two_sets"],
        "color_map": {"unknown": "gray", "one_set": "orange", "two_sets": "green"},
    },
    "imported_numeric": {
        "column": "import_status_cat",
        "hover": ["import_status_cat", "import_country"],
        "category_order": ["unknown", "norwegian", "imported"],
        "color_map": {"unknown": "gray", "norwegian": "steelblue", "imported": "crimson"},
    },
    "status_numeric": {
        "column": "status",
        "hover": ["status"],
        "category_order": ["unknown", "available", "sold"],
        "color_map": {"unknown": "gray", "available": "seagreen", "sold": "firebrick"},
    },
}


class PlotOptions(NamedTuple):
    """The sidebar's plot-customization selections, passed to each plot builder."""

    color_column: str
    size_column: str


def make_price_scatter(df, x, opts: PlotOptions, extra_hover, continuous_scale="viridis"):
    """Build a price scatter plot, encapsulating the discrete/continuous
    color-mode branching shared by the three plot sections."""
    kwargs = {}
    mode = DISCRETE_COLOR_MODES.get(opts.color_column)
    if mode is not None:
        color = mode["column"]
        mode_hover = mode["hover"]
        kwargs["category_orders"] = {mode["column"]: mode["category_order"]}
        kwargs["color_discrete_map"] = mode["color_map"]
    else:
        color = opts.color_column
        mode_hover = ["tire_sets_cat"]
        kwargs["color_continuous_scale"] = continuous_scale

    fig = px.scatter(
        df,
        x=x,
        y="totalpris",
        color=color,
        size=opts.size_column if opts.size_column != "None" else None,
        hover_data=["title", "merke", "modell", *extra_hover, *mode_hover],
        labels=AXIS_LABELS,
        **kwargs,
    )
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="LightGray")
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="LightGray")
    return fig


st.set_page_config(page_title="FINN Used Car Explorer", layout="wide")

st.title("FINN Used Car Explorer")
st.caption("Filter and visualize scraped data from finn.no ads.")

try:
    data = load_ads_dataframe()
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

if data.empty:
    st.info("The database does not contain any ad details yet. Run the downloader script first.")
    st.stop()

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

# Trim level filter based on subtitle
st.sidebar.markdown("**Trim Level**")
trim_gt_line = st.sidebar.checkbox("GT-Line", value=True)
trim_exclusive = st.sidebar.checkbox("Exclusive", value=True)
trim_undetermined = st.sidebar.checkbox("Undetermined", value=True)


# Categorize each row based on subtitle
def categorize_trim(subtitle):
    if pd.isna(subtitle) or subtitle == "":
        return "undetermined"
    subtitle_lower = str(subtitle).lower()
    if "gt-line" in subtitle_lower or "gt line" in subtitle_lower:
        return "gt-line"
    elif "exclusive" in subtitle_lower:
        return "exclusive"
    else:
        return "undetermined"


subset["trim_category"] = subset["subtitle"].apply(categorize_trim)

# TODO: it would be better to rather post-process the database for auxiliary fields
# This post-processing should be able to run while downloading/scraping the data
# if requested. Relevant aspects:
# - Identify trim level more generally, so that the analysis script references trim
#   level column instead of a model-specific subtitle parsing.
# - Determine if two sets of tires are included (summer/winter). This could be
#   inferred from subtitle or other fields. May want to use chatgpt or similar
#   to help with natural language parsing of subtitles and descriptions.

# Filter based on selected trim levels
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


def categorize_import_status(value):
    if value is True:
        return "imported"
    elif value is False:
        return "norwegian"
    else:
        return "unknown"


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

# Get numeric columns for color and size options
numeric_columns = subset.select_dtypes(include=[np.number]).columns.tolist()
# Add calculated fields that will be available
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

plot_opts = PlotOptions(color_column=color_column, size_column=size_column)

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

# Preprocess: Calculate age in years
subset = subset.copy()
subset["fetched_at_dt"] = pd.to_datetime(subset["fetched_at"], errors="coerce", utc=True)
subset["førstegangsregistrert_dt"] = pd.to_datetime(subset["førstegangsregistrert"], errors="coerce", utc=True)
subset["age_years"] = (subset["fetched_at_dt"] - subset["førstegangsregistrert_dt"]).dt.days / 365.25


# Map tire_sets to categorical values for better display
def map_tire_sets(value):
    if pd.isna(value) or value == "" or value == "unknown":
        return "unknown"
    elif value == "one_set":
        return "one_set"
    elif value == "two_sets":
        return "two_sets"
    else:
        return "unknown"


subset["tire_sets_cat"] = subset["tire_sets"].apply(map_tire_sets)
# Create numeric mapping for color scale: unknown=0, one_set=1, two_sets=2
tire_sets_numeric_map = {"unknown": 0, "one_set": 1, "two_sets": 2}
subset["tire_sets_numeric"] = subset["tire_sets_cat"].map(tire_sets_numeric_map)


# Categorical import status for display; same categorization as the filter column.
subset["import_status_cat"] = subset["import_category"]
# Numeric mapping: unknown=0, norwegian=1, imported=2
import_status_numeric_map = {"unknown": 0, "norwegian": 1, "imported": 2}
subset["imported_numeric"] = subset["import_status_cat"].map(import_status_numeric_map)

# Availability status (available / sold / unknown). "sold" already folds in
# inactive/removed ads (see db._derive_status).
if "status" not in subset.columns:
    subset["status"] = "unknown"
# Numeric mapping: unknown=0, available=1, sold=2
status_numeric_map = {"unknown": 0, "available": 1, "sold": 2}
subset["status_numeric"] = subset["status"].map(status_numeric_map).fillna(0).astype(int)


# OLS Regression Model: Price = c0 + c1*mileage + c2*age
def perform_ols_analysis(data):
    """Perform OLS regression analysis on car price data."""
    # Filter out rows with missing values for the analysis
    analysis_data = data.dropna(subset=["totalpris", "kilometerstand_km", "age_years"]).copy()

    if len(analysis_data) < MIN_OLS_SAMPLES:
        return None, None, None, None

    # Prepare features and target
    X = analysis_data[["kilometerstand_km", "age_years"]].values
    y = analysis_data["totalpris"].values

    if SKLEARN_AVAILABLE:
        # Fit OLS model using sklearn
        model = LinearRegression()
        model.fit(X, y)

        # Make predictions
        y_pred = model.predict(X)

        # Calculate metrics
        r2 = r2_score(y, y_pred)
        mae = mean_absolute_error(y, y_pred)
        rmse = np.sqrt(mean_squared_error(y, y_pred))

        # Calculate usedness score: weighted combination of mileage and age
        # Normalize coefficients to create usedness metric
        c1, c2 = model.coef_
        c0 = model.intercept_

        # Create usedness as a linear combination: usedness = c1 * mileage + c2 * age
        # This makes the relationship: Price = c0 + usedness
        # So the regression line in Price vs Usedness will be perfectly straight
        analysis_data["usedness"] = c1 * analysis_data["kilometerstand_km"] + c2 * analysis_data["age_years"]

        return model, analysis_data, {"r2": r2, "mae": mae, "rmse": rmse, "c0": c0, "c1": c1, "c2": c2}, y_pred
    else:
        # Simple manual OLS implementation if sklearn not available
        # Add intercept term
        X_with_intercept = np.column_stack([np.ones(len(X)), X])

        # Calculate coefficients: (X'X)^-1 X'y
        try:
            coefficients = np.linalg.solve(X_with_intercept.T @ X_with_intercept, X_with_intercept.T @ y)
            c0, c1, c2 = coefficients

            # Make predictions
            y_pred = X_with_intercept @ coefficients

            # Calculate metrics
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = 1 - (ss_res / ss_tot)
            mae = np.mean(np.abs(y - y_pred))
            rmse = np.sqrt(np.mean((y - y_pred) ** 2))

            # Calculate usedness score: usedness = c1 * mileage + c2 * age
            # This makes Price = c0 + usedness (perfectly linear relationship)
            analysis_data["usedness"] = c1 * analysis_data["kilometerstand_km"] + c2 * analysis_data["age_years"]

            return None, analysis_data, {"r2": r2, "mae": mae, "rmse": rmse, "c0": c0, "c1": c1, "c2": c2}, y_pred
        except np.linalg.LinAlgError:
            return None, None, None, None


# Perform OLS analysis
model, analysis_subset, metrics, predictions = perform_ols_analysis(subset)

# Display OLS Regression Results
if metrics is not None:
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
    if analysis_subset is not None:
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
        sorted_data = analysis_subset.sort_values("usedness")
        usedness_range = sorted_data["usedness"].values
        predicted_price = metrics["c0"] + usedness_range

        fig_usedness.add_trace(
            go.Scatter(
                x=usedness_range,
                y=predicted_price,
                mode="lines",
                name="OLS Regression (Price = c₀ + usedness)",
                line={"color": "red", "width": 2},
                showlegend=True,
            )
        )

        st.plotly_chart(fig_usedness, use_container_width=True)

        # Add correlation info
        if len(analysis_subset) > 1:
            corr = analysis_subset["usedness"].corr(analysis_subset["totalpris"])
            st.markdown(f"**Correlation between Usedness and Price**: {corr:.3f}")

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

    # Add regression line
    if len(mileage_data) > 1:
        X_mileage = mileage_data["kilometerstand_km"].values.reshape(-1, 1)
        y_mileage = mileage_data["totalpris"].values

        if SKLEARN_AVAILABLE:
            lr_mileage = LinearRegression()
            lr_mileage.fit(X_mileage, y_mileage)
            X_mileage_sorted = np.sort(X_mileage, axis=0)
            y_mileage_pred = lr_mileage.predict(X_mileage_sorted)
        else:
            # Manual linear regression
            X_mean = X_mileage.mean()
            y_mean = y_mileage.mean()
            slope = np.sum((X_mileage.flatten() - X_mean) * (y_mileage - y_mean)) / np.sum(
                (X_mileage.flatten() - X_mean) ** 2
            )
            intercept = y_mean - slope * X_mean
            X_mileage_sorted = np.sort(X_mileage, axis=0)
            y_mileage_pred = slope * X_mileage_sorted.flatten() + intercept

        fig_mileage.add_trace(
            go.Scatter(
                x=X_mileage_sorted.flatten(),
                y=y_mileage_pred,
                mode="lines",
                name="Regression Line",
                line={"color": "red", "width": 2},
                showlegend=True,
            )
        )

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

    # Add regression line
    if len(reg_data) > 1:
        # Convert dates to numeric (days since earliest date)
        reg_dates = pd.to_datetime(reg_data["førstegangsregistrert"])
        min_date = reg_dates.min()
        X_reg = (reg_dates - min_date).dt.days.values.reshape(-1, 1)
        y_reg = reg_data["totalpris"].values

        if SKLEARN_AVAILABLE:
            lr_reg = LinearRegression()
            lr_reg.fit(X_reg, y_reg)
            X_reg_sorted = np.sort(X_reg, axis=0)
            y_reg_pred = lr_reg.predict(X_reg_sorted)
        else:
            # Manual linear regression
            X_mean = X_reg.mean()
            y_mean = y_reg.mean()
            slope = np.sum((X_reg.flatten() - X_mean) * (y_reg - y_mean)) / np.sum((X_reg.flatten() - X_mean) ** 2)
            intercept = y_mean - slope * X_mean
            X_reg_sorted = np.sort(X_reg, axis=0)
            y_reg_pred = slope * X_reg_sorted.flatten() + intercept

        # Convert X back to dates for plotting
        dates_sorted = min_date + pd.to_timedelta(X_reg_sorted.flatten(), unit="D")

        fig_registration.add_trace(
            go.Scatter(
                x=dates_sorted,
                y=y_reg_pred,
                mode="lines",
                name="Regression Line",
                line={"color": "red", "width": 2},
                showlegend=True,
            )
        )

    st.plotly_chart(fig_registration, use_container_width=True)

st.subheader("Matching ads")

# Prepare columns for dataframe display
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

# Add usedness column if analysis was performed successfully
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
