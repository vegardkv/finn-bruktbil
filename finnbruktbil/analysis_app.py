from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
    from scipy import stats
    SKLEARN_AVAILABLE = True
    SCIPY_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    SCIPY_AVAILABLE = False

# Add parent directory to path to support both direct execution and module import
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from finnbruktbil.db import DEFAULT_DB_PATH, load_ads_dataframe
else:
    from .db import DEFAULT_DB_PATH, load_ads_dataframe


def _series_bounds(series, fallback_min: int = 0, fallback_max: int = 0) -> tuple[int, int]:
    values = series.dropna()
    if values.empty:
        return fallback_min, fallback_max
    lower = int(values.min())
    upper = int(values.max())
    if lower > upper:
        lower, upper = upper, lower
    return lower, upper


st.set_page_config(page_title="FINN Used Car Explorer", layout="wide")

st.title("FINN Used Car Explorer")
st.caption("Filter and visualize scraped data from finn.no ads.")

default_db = os.environ.get("FINNBRUKTBIL_DB_PATH", str(DEFAULT_DB_PATH))
selected_db = st.sidebar.text_input("Database path", value=default_db)

try:
    data = load_ads_dataframe(Path(selected_db))
except FileNotFoundError:
    st.warning("No database file found yet. Run the fetch and download scripts first.")
    st.stop()
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

if data.empty:
    st.info("The database does not contain any ad details yet. Run the downloader script first.")
    st.stop()

brand_options = sorted({b for b in data["merke"].dropna().unique() if b})
selected_brand = st.sidebar.selectbox("Brand", options=["(All)"] + brand_options)

subset = data.copy()
if selected_brand != "(All)":
    subset = subset[subset["merke"] == selected_brand]

model_options = sorted({m for m in subset["modell"].dropna().unique() if m})
selected_model = st.sidebar.selectbox("Model", options=["(All)"] + model_options)
if selected_model != "(All)":
    subset = subset[subset["modell"] == selected_model]

seats_options = sorted({int(s) for s in subset["seter"].dropna().unique() if s})
selected_seats = st.sidebar.selectbox("Number of seats", options=["(All)"] + seats_options)
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

if subset.empty:
    st.warning("No data matches the selected filters.")
    st.stop()

price_min, price_max = _series_bounds(subset["totalpris"], 0, 0)
if price_min < price_max:
    price_range = st.sidebar.slider(
        "Price (NOK)",
        price_min,
        price_max,
        value=(price_min, price_max),
    )
    subset = subset[(subset["totalpris"].fillna(0) >= price_range[0]) & (subset["totalpris"].fillna(0) <= price_range[1])]
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
        (subset["kilometerstand_km"].fillna(0) >= mileage_range[0]) & (subset["kilometerstand_km"].fillna(0) <= mileage_range[1])
    ]
else:
    st.sidebar.text(f"Mileage: {mileage_min:,} km")

year_min, year_max = _series_bounds(subset["modellår"], 1900, 1900)
if year_min < year_max:
    year_selection = st.sidebar.slider("Model year", year_min, year_max, (year_min, year_max))
    subset = subset[
        (subset["modellår"].fillna(year_min) >= year_selection[0])
        & (subset["modellår"].fillna(year_max) <= year_selection[1])
    ]
else:
    st.sidebar.text(f"Model year: {year_min if year_min > 1900 else 'N/A'}")

st.metric("Matches", len(subset))

# Preprocess: Calculate age in years
import pandas as pd
import numpy as np
try:
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

subset = subset.copy()
subset["fetched_at_dt"] = pd.to_datetime(subset["fetched_at"], errors="coerce")
subset["førstegangsregistrert_dt"] = pd.to_datetime(subset["førstegangsregistrert"], errors="coerce")
subset["age_years"] = (subset["fetched_at_dt"] - subset["førstegangsregistrert_dt"]).dt.days / 365.25

# OLS Regression Model: Price = c0 + c1*mileage + c2*age
def perform_ols_analysis(data):
    """Perform OLS regression analysis on car price data."""
    # Filter out rows with missing values for the analysis
    analysis_data = data.dropna(subset=["totalpris", "kilometerstand_km", "age_years"]).copy()
    
    if len(analysis_data) < 10:  # Need sufficient data points
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
    - **Base Price**: {metrics['c0']:,.0f} NOK (when mileage and age are zero)
    - **Mileage Impact**: Each additional kilometer reduces value by {abs(metrics['c1']):.2f} NOK
    - **Age Impact**: Each additional year reduces value by {abs(metrics['c2']):,.0f} NOK
    - **Model Fit**: R² = {metrics['r2']:.3f} (explains {metrics['r2']*100:.1f}% of price variation)
    """)
    
    # Usedness vs Price plot
    if analysis_subset is not None:
        st.subheader("Price vs. Usedness Score")
        fig_usedness = px.scatter(
            analysis_subset,
            x="usedness",
            y="totalpris",
            color="age_years",
            size="kilometerstand_km",
            hover_data=["title", "merke", "modell", "kilometerstand_km", "age_years"],
            labels={
                "usedness": "Usedness Score (0=New, 1=Most Used)",
                "totalpris": "Price (NOK)",
                "age_years": "Age (years)",
                "kilometerstand_km": "Mileage (km)"
            },
            color_continuous_scale="viridis",
            title="Car Price vs. Combined Usedness Score"
        )
        
        # Add regression line: Price = c0 + usedness (perfectly straight line)
        # Since usedness = c1 * mileage + c2 * age, this is the OLS prediction
        sorted_data = analysis_subset.sort_values('usedness')
        usedness_range = sorted_data["usedness"].values
        predicted_price = metrics['c0'] + usedness_range
        
        fig_usedness.add_trace(
            go.Scatter(
                x=usedness_range,
                y=predicted_price,
                mode='lines',
                name='OLS Regression (Price = c₀ + usedness)',
                line=dict(color='red', width=2),
                showlegend=True
            )
        )
        
        fig_usedness.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
        fig_usedness.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
        st.plotly_chart(fig_usedness, use_container_width=True)
        
        # Add correlation info
        if len(analysis_subset) > 1:
            corr = analysis_subset["usedness"].corr(analysis_subset["totalpris"])
            st.markdown(f"**Correlation between Usedness and Price**: {corr:.3f}")
    
else:
    st.warning("⚠️ Cannot perform OLS analysis: insufficient data or missing required libraries (scikit-learn recommended)")

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
    fig_mileage = px.scatter(
        mileage_data,
        x="kilometerstand_km",
        y="totalpris",
        color="age_years",
        hover_data=["title", "merke", "modell", "førstegangsregistrert"],
        labels={
            "kilometerstand_km": "Mileage (km)",
            "totalpris": "Price (NOK)",
            "age_years": "Age (years)"
        },
        color_continuous_scale="viridis"
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
            slope = np.sum((X_mileage.flatten() - X_mean) * (y_mileage - y_mean)) / np.sum((X_mileage.flatten() - X_mean) ** 2)
            intercept = y_mean - slope * X_mean
            X_mileage_sorted = np.sort(X_mileage, axis=0)
            y_mileage_pred = slope * X_mileage_sorted.flatten() + intercept
        
        fig_mileage.add_trace(
            go.Scatter(
                x=X_mileage_sorted.flatten(),
                y=y_mileage_pred,
                mode='lines',
                name='Regression Line',
                line=dict(color='red', width=2),
                showlegend=True
            )
        )
    
    fig_mileage.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    fig_mileage.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    st.plotly_chart(fig_mileage, use_container_width=True)

with scatter_cols[1]:
    st.subheader("Price vs. Registration Date")
    reg_data = subset.dropna(subset=["førstegangsregistrert", "totalpris"])
    fig_registration = px.scatter(
        reg_data,
        x="førstegangsregistrert",
        y="totalpris",
        color="kilometerstand_km",
        hover_data=["title", "merke", "modell"],
        labels={
            "førstegangsregistrert": "First Registration",
            "totalpris": "Price (NOK)",
            "kilometerstand_km": "Mileage (km)"
        },
        color_continuous_scale="plasma"
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
        dates_sorted = min_date + pd.to_timedelta(X_reg_sorted.flatten(), unit='D')
        
        fig_registration.add_trace(
            go.Scatter(
                x=dates_sorted,
                y=y_reg_pred,
                mode='lines',
                name='Regression Line',
                line=dict(color='red', width=2),
                showlegend=True
            )
        )
    
    fig_registration.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    fig_registration.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
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
]

# Add usedness column if analysis was performed successfully
display_subset = subset.copy()
if analysis_subset is not None and "usedness" in analysis_subset.columns:
    # Check if ad_id exists in both dataframes for merging
    if "ad_id" in analysis_subset.columns and "ad_id" in display_subset.columns:
        # Merge usedness scores back to the main subset
        display_subset = display_subset.merge(
            analysis_subset[["ad_id", "usedness"]], 
            on="ad_id", 
            how="left"
        )
        display_columns.insert(5, "usedness")  # Insert after age_years
    else:
        # If no ad_id for merging, add usedness to all rows that have complete data
        complete_data_mask = (
            display_subset["totalpris"].notna() & 
            display_subset["kilometerstand_km"].notna() & 
            display_subset["age_years"].notna()
        )
        display_subset.loc[complete_data_mask, "usedness"] = analysis_subset["usedness"].values[:len(display_subset[complete_data_mask])]
        display_columns.insert(5, "usedness")

st.dataframe(
    display_subset[display_columns].sort_values(by="totalpris", ascending=False),
    use_container_width=True,
)
