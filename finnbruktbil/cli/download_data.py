from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from selenium.common.exceptions import WebDriverException

from ..browser import create_driver, polite_delay
from ..db import (
    db_session,
    fetch_ids_for_scraping,
    initialize_schema,
    mark_missing,
    save_ad_detail,
)
from ..scraper import scrape_ad
from .config import DownloadConfig, load_config


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "download",
        help="Download details for stored ad ids",
        description="Download FINN ad details for stored ad ids.",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Path to a JSON config file describing download parameters.",
    )
    parser.set_defaults(func=run)
    return parser


def download_ads(config: DownloadConfig) -> tuple[int, int]:
    """Download ad details for stored identifiers.

    Returns a tuple ``(scraped, missing)`` describing the number of records
    successfully scraped and the number marked missing.
    """

    db_path = str(config.resolved_db_path)

    with db_session(db_path) as conn:
        initialize_schema(conn)
        target_ids: List[str] = fetch_ids_for_scraping(
            conn,
            limit=config.limit,
            stale_hours=config.stale_hours,
            random_order=config.random_order,
        )

    if not target_ids:
        return (0, 0)

    driver = create_driver(headless=config.headless)
    scraped = 0
    missing = 0
    try:
        for ad_id in target_ids:
            try:
                record = scrape_ad(driver, ad_id, parse_aux_data=config.parse_aux_data)
            except WebDriverException as exc:
                print(f"Encountered webdriver issue for ad {ad_id}: {exc}")
                break

            if record is None:
                with db_session(db_path) as conn:
                    mark_missing(conn, ad_id)
                missing += 1
                continue

            with db_session(db_path) as conn:
                save_ad_detail(conn, record)
            scraped += 1
            polite_delay()
    finally:
        driver.quit()

    return scraped, missing


def run(args: argparse.Namespace) -> int:
    config = load_config(args.config, DownloadConfig)
    scraped, missing = download_ads(config)

    if scraped == 0 and missing == 0:
        print("No ad ids matched the requested filters.")
        return 0

    print(f"Scraped {scraped} ads; marked {missing} as missing")
    return 0
