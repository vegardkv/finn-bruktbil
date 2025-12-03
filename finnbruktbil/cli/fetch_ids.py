from __future__ import annotations

import argparse
import re
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
FAVORITES_FETCHED_BY = "favorites_file"


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


def extract_ids_from_favorites_file(file_path: Path) -> List[str]:
    """Extract ad IDs from a local favorites HTML file.
    
    The favorites HTML contains embedded JSON with items that have "itemId" fields.
    """
    html_content = file_path.read_text(encoding="utf-8")
    
    # Look for itemId values in the embedded JSON data
    # Pattern matches "itemId":123456789 where the number is the ad ID
    pattern = r'"itemId"\s*:\s*(\d+)'
    matches = re.findall(pattern, html_content)
    
    # Deduplicate while preserving order
    seen = set()
    unique_ids: List[str] = []
    for match in matches:
        if match not in seen:
            seen.add(match)
            unique_ids.append(match)
    
    return unique_ids


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
    """Fetch ad identifiers from a FINN search URL or favorites file and persist them."""

    with db_session() as client:
        initialize_schema(client)

    # Mode 1: Parse local favorites HTML file
    if config.favorites_file:
        favorites_path = Path(config.favorites_file)
        if not favorites_path.exists():
            raise FileNotFoundError(f"Favorites file not found: {favorites_path}")
        
        ad_ids = extract_ids_from_favorites_file(favorites_path)
        if config.limit:
            ad_ids = ad_ids[:config.limit]
        
        if not ad_ids:
            return []
        
        fetched_by = config.fetched_by if config.fetched_by != "finn_search" else FAVORITES_FETCHED_BY
        source = str(favorites_path)
        
        with db_session() as client:
            upsert_ad_ids(client, source, ad_ids, fetched_by=fetched_by)
        
        return ad_ids

    # Mode 2: Scrape from FINN search URL
    if not config.base_url:
        raise ValueError("Either base_url or favorites_file must be provided")

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

    with db_session() as client:
        upsert_ad_ids(client, config.base_url, ad_ids, fetched_by=config.fetched_by)

    return ad_ids


def run(args: argparse.Namespace) -> int:
    config = load_config(args.config, FetchIdsConfig)
    ad_ids = fetch_ids_into_db(config)
    if not ad_ids:
        print("No ad ids were discovered. Nothing stored.")
        return 0

    print(f"Stored {len(ad_ids)} unique ad ids at {datetime.now().isoformat(timespec='seconds')}")
    return 0
