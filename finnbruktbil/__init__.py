"""Utility package for scraping and analyzing FINN used-car listings."""

from .browser import create_driver, polite_delay, wait_for_elements
from .cli import main as cli_main
from .db import (
    AdRecord,
    db_session,
    deduplicate_by_vin,
    fetch_ids_for_scraping,
    initialize_schema,
    load_ads_dataframe,
    mark_missing,
    save_ad_detail,
    upsert_ad_ids,
)
from .scraper import scrape_ad

__all__ = [
    "AdRecord",
    "cli_main",
    "create_driver",
    "db_session",
    "deduplicate_by_vin",
    "fetch_ids_for_scraping",
    "initialize_schema",
    "load_ads_dataframe",
    "mark_missing",
    "polite_delay",
    "save_ad_detail",
    "scrape_ad",
    "upsert_ad_ids",
    "wait_for_elements",
]
