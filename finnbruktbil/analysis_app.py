from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

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

brand_options = sorted({b for b in data["brand"].dropna().unique() if b})
selected_brand = st.sidebar.selectbox("Brand", options=["(All)"] + brand_options)

subset = data.copy()
if selected_brand != "(All)":
    subset = subset[subset["brand"] == selected_brand]

model_options = sorted({m for m in subset["model"].dropna().unique() if m})
selected_model = st.sidebar.selectbox("Model", options=["(All)"] + model_options)
if selected_model != "(All)":
    subset = subset[subset["model"] == selected_model]

if subset.empty:
    st.warning("No data matches the selected filters.")
    st.stop()

price_min, price_max = _series_bounds(subset["price_nok"], 0, 0)
price_range = st.sidebar.slider(
    "Price (NOK)",
    price_min,
    max(price_max, price_min),
    value=(price_min, max(price_max, price_min)),
)
subset = subset[(subset["price_nok"].fillna(0) >= price_range[0]) & (subset["price_nok"].fillna(0) <= price_range[1])]

mileage_min, mileage_max = _series_bounds(subset["mileage_km"], 0, 0)
mileage_range = st.sidebar.slider(
    "Mileage (km)",
    mileage_min,
    max(mileage_max, mileage_min),
    value=(mileage_min, max(mileage_max, mileage_min)),
)
subset = subset[
    (subset["mileage_km"].fillna(0) >= mileage_range[0]) & (subset["mileage_km"].fillna(0) <= mileage_range[1])
]

year_min, year_max = _series_bounds(subset["model_year"], 1900, 1900)
year_selection = st.sidebar.slider("Model year", year_min, year_max, (year_min, year_max))
subset = subset[
    (subset["model_year"].fillna(year_min) >= year_selection[0])
    & (subset["model_year"].fillna(year_max) <= year_selection[1])
]

st.metric("Matches", len(subset))

scatter_cols = st.columns(2)
with scatter_cols[0]:
    st.subheader("Price vs. Mileage")
    st.scatter_chart(subset, x="mileage_km", y="price_nok", color="model_year")

with scatter_cols[1]:
    st.subheader("Price vs. Model Year")
    st.scatter_chart(subset, x="model_year", y="price_nok", color="mileage_km")

st.subheader("Matching ads")
st.dataframe(
    subset[[
        "ad_id",
        "title",
        "price_nok",
        "mileage_km",
        "model_year",
        "location",
        "fetched_at",
    ]].sort_values(by="price_nok", ascending=False),
    use_container_width=True,
)
