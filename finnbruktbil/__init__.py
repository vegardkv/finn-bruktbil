"""Utility package for scraping and analyzing FINN used-car listings."""

from .browser import create_driver, polite_delay, wait_for_elements
from .cli import main as cli_main
from .db import (
    DEFAULT_DB_PATH,
    AdRecord,
    db_session,
    fetch_ids_for_scraping,
    initialize_schema,
    load_ads_dataframe,
    mark_missing,
    save_ad_detail,
    upsert_ad_ids,
)
from .scraper import scrape_ad

__all__ = [
    "DEFAULT_DB_PATH",
    "AdRecord",
    "cli_main",
    "create_driver",
    "db_session",
    "fetch_ids_for_scraping",
    "initialize_schema",
    "load_ads_dataframe",
    "mark_missing",
    "save_ad_detail",
    "upsert_ad_ids",
    "polite_delay",
    "wait_for_elements",
    "scrape_ad",
]
