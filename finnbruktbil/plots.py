"""Streamlit-free plotting and analysis helpers.

These are shared by the interactive dashboard (``analysis_app.py``) and the static
HTML report (``cli/report.py``). Keeping them here means the report generator and
CI never import ``streamlit`` just to build a figure.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

try:
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


# Sentinel year used when the data contains no model years at all.
MODEL_YEAR_SENTINEL = 1900
# Minimum rows with price/mileage/age required to fit the OLS model.
MIN_OLS_SAMPLES = 10

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


# Categorize each row: the aux-parsed trim_level column (see aux_data_parser.py)
# is authoritative when present; subtitle parsing is the fallback for ads scraped
# without parse_aux_data.
def categorize_trim(row):
    source = row.get("trim_level")
    if pd.isna(source) or source == "":
        source = row.get("subtitle")
    if pd.isna(source) or source == "":
        return "undetermined"
    text = str(source).lower()
    if "gt-line" in text or "gt line" in text:
        return "gt-line"
    elif "exclusive" in text:
        return "exclusive"
    else:
        return "undetermined"


def categorize_import_status(value):
    if value is True:
        return "imported"
    elif value is False:
        return "norwegian"
    else:
        return "unknown"


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


def _linear_fit(x, y):
    """Fit a straight line to (x, y) and return (x_sorted, y_predicted) for
    drawing a regression trace. Uses sklearn when available, manual OLS otherwise."""
    x = np.asarray(x, dtype=float).reshape(-1, 1)
    y = np.asarray(y, dtype=float)
    x_sorted = np.sort(x, axis=0)
    if SKLEARN_AVAILABLE:
        lr = LinearRegression()
        lr.fit(x, y)
        return x_sorted.flatten(), lr.predict(x_sorted)
    x_flat = x.flatten()
    x_mean = x_flat.mean()
    y_mean = y.mean()
    slope = np.sum((x_flat - x_mean) * (y - y_mean)) / np.sum((x_flat - x_mean) ** 2)
    intercept = y_mean - slope * x_mean
    return x_sorted.flatten(), slope * x_sorted.flatten() + intercept


def _regression_trace(x, y, name="Regression Line"):
    return go.Scatter(
        x=x,
        y=y,
        mode="lines",
        name=name,
        line={"color": "red", "width": 2},
        showlegend=True,
    )


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


def add_derived_columns(subset) -> pd.DataFrame:
    """Add the derived columns the plots rely on: age and the categorical/numeric
    tire-set, import-status, and availability-status encodings."""
    subset = subset.copy()

    # ``import_category`` is normally computed by the dashboard's sidebar filter;
    # compute it here when absent so this function is self-contained (the report
    # generator does not go through the sidebar).
    if "import_category" not in subset.columns:
        subset["import_category"] = (
            subset["imported"].apply(categorize_import_status) if "imported" in subset.columns else "unknown"
        )

    subset["fetched_at_dt"] = pd.to_datetime(subset["fetched_at"], errors="coerce", utc=True)
    subset["førstegangsregistrert_dt"] = pd.to_datetime(subset["førstegangsregistrert"], errors="coerce", utc=True)
    subset["age_years"] = (subset["fetched_at_dt"] - subset["førstegangsregistrert_dt"]).dt.days / 365.25

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

    return subset
