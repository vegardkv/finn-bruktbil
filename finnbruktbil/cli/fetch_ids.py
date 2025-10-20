from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import List
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from selenium.webdriver.common.by import By

from ..browser import create_driver, polite_delay, wait_for_elements
from ..db import db_session, initialize_schema, upsert_ad_ids
from .config import FetchIdsConfig, load_config

RESULT_SELECTOR = "a.sf-search-ad-link"
DEFAULT_FETCHED_BY = "finn_search"


def build_page_url(base_url: str, page: int) -> str:
    if page == 1:
        return base_url
    parts = list(urlsplit(base_url))
    query_params = dict(parse_qsl(parts[3], keep_blank_values=True))
    query_params["page"] = str(page)
    parts[3] = urlencode(query_params, doseq=True)
    return urlunsplit(parts)


def extract_ids_from_page(driver) -> List[str]:
    elements = driver.find_elements(By.CSS_SELECTOR, RESULT_SELECTOR)
    ids: List[str] = []

    for element in elements:
        candidate = element.get_attribute("id") or ""
        if not candidate:
            href = element.get_attribute("href") or ""
            candidate = href.rstrip("/").split("/")[-1]
        candidate = candidate.strip()
        if candidate and candidate not in ids:
            ids.append(candidate)
    return ids


def collect_ad_ids(driver, base_url: str, max_pages: int, limit: int) -> List[str]:
    collected: List[str] = []
    for page in range(1, max_pages + 1):
        page_url = build_page_url(base_url, page)
        driver.get(page_url)
        if not wait_for_elements(driver, RESULT_SELECTOR, timeout=15):
            break
        page_ids = extract_ids_from_page(driver)
        if not page_ids:
            break
        for ad_id in page_ids:
            if ad_id not in collected:
                collected.append(ad_id)
        if len(collected) >= limit:
            return collected[:limit]
        polite_delay()
    return collected


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "fetch-ids",
        help="Fetch ad identifiers from a FINN search page",
        description="Fetch FINN ad ids and store them in the local database.",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Path to a JSON config file describing fetch parameters.",
    )
    parser.set_defaults(func=run)
    return parser


def fetch_ids_into_db(config: FetchIdsConfig) -> List[str]:
    """Fetch ad identifiers from a FINN search URL and persist them."""

    db_path = str(config.resolved_db_path)

    with db_session(db_path) as conn:
        initialize_schema(conn)

    driver = create_driver(headless=config.headless)
    try:
        ad_ids = collect_ad_ids(
            driver,
            config.base_url,
            config.max_pages,
            config.limit,
        )
    finally:
        driver.quit()

    if not ad_ids:
        return []

    with db_session(db_path) as conn:
        upsert_ad_ids(conn, config.base_url, ad_ids, fetched_by=config.fetched_by)

    return ad_ids


def run(args: argparse.Namespace) -> int:
    config = load_config(args.config, FetchIdsConfig)
    ad_ids = fetch_ids_into_db(config)
    if not ad_ids:
        print("No ad ids were discovered. Nothing stored.")
        return 0

    print(f"Stored {len(ad_ids)} unique ad ids at {datetime.now().isoformat(timespec='seconds')}")
    return 0
