from __future__ import annotations

import os
import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

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

if subset.empty:
    st.warning("No data matches the selected filters.")
    st.stop()

price_min, price_max = _series_bounds(subset["pris_eks_omreg"], 0, 0)
if price_min < price_max:
    price_range = st.sidebar.slider(
        "Price (NOK)",
        price_min,
        price_max,
        value=(price_min, price_max),
    )
    subset = subset[(subset["pris_eks_omreg"].fillna(0) >= price_range[0]) & (subset["pris_eks_omreg"].fillna(0) <= price_range[1])]
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
subset = subset.copy()
subset["fetched_at_dt"] = pd.to_datetime(subset["fetched_at"], errors="coerce")
subset["førstegangsregistrert_dt"] = pd.to_datetime(subset["førstegangsregistrert"], errors="coerce")
subset["age_years"] = (subset["fetched_at_dt"] - subset["førstegangsregistrert_dt"]).dt.days / 365.25

scatter_cols = st.columns(2)
with scatter_cols[0]:
    st.subheader("Price vs. Mileage")
    fig_mileage = px.scatter(
        subset.dropna(subset=["kilometerstand_km", "pris_eks_omreg", "age_years"]),
        x="kilometerstand_km",
        y="pris_eks_omreg",
        color="age_years",
        hover_data=["title", "merke", "modell", "førstegangsregistrert"],
        labels={
            "kilometerstand_km": "Mileage (km)",
            "pris_eks_omreg": "Price (NOK)",
            "age_years": "Age (years)"
        },
        color_continuous_scale="viridis"
    )
    fig_mileage.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    fig_mileage.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    st.plotly_chart(fig_mileage, use_container_width=True)

with scatter_cols[1]:
    st.subheader("Price vs. Registration Date")
    fig_registration = px.scatter(
        subset.dropna(subset=["førstegangsregistrert", "pris_eks_omreg"]),
        x="førstegangsregistrert",
        y="pris_eks_omreg",
        color="kilometerstand_km",
        hover_data=["title", "merke", "modell"],
        labels={
            "førstegangsregistrert": "First Registration",
            "pris_eks_omreg": "Price (NOK)",
            "kilometerstand_km": "Mileage (km)"
        },
        color_continuous_scale="plasma"
    )
    fig_registration.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    fig_registration.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    st.plotly_chart(fig_registration, use_container_width=True)

st.subheader("Matching ads")
st.dataframe(
    subset[[
        "ad_id",
        "title",
        "pris_eks_omreg",
        "kilometerstand_km",
        "age_years",
        "modellår",
        "førstegangsregistrert",
        "bilen_står_i",
        "fetched_at",
    ]].sort_values(by="pris_eks_omreg", ascending=False),
    use_container_width=True,
)
