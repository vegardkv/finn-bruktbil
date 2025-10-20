from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from .db import AdRecord
from .browser import wait_for_elements

AD_BASE_URL = "https://www.finn.no/mobility/item/"


def _text_or_none(driver, selector: str) -> Optional[str]:
    try:
        element = driver.find_element(By.CSS_SELECTOR, selector)
    except NoSuchElementException:
        return None
    text = element.text.strip()
    return text or None


def _parse_int(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _collect_specs(driver) -> Dict[str, str]:
    specs: Dict[str, str] = {}
    for dl in driver.find_elements(By.CSS_SELECTOR, "dl"):
        keys = dl.find_elements(By.TAG_NAME, "dt")
        values = dl.find_elements(By.TAG_NAME, "dd")
        if len(keys) != len(values):
            continue
        for key_el, value_el in zip(keys, values):
            key = key_el.text.strip()
            value = value_el.text.strip()
            if key and value and key not in specs:
                specs[key] = value
    return specs


def scrape_ad(driver, ad_id: str) -> Optional[AdRecord]:
    driver.get(f"{AD_BASE_URL}{ad_id}")
    if not wait_for_elements(driver, "h1", timeout=15):
        return None

    title = _text_or_none(driver, "h1")
    price_text = _text_or_none(driver, "[data-testid='price-amount']") or _text_or_none(driver, ".u-t3")
    location = _text_or_none(driver, "[data-testid='location']")

    specs = _collect_specs(driver)

    brand = specs.get("Merke") or specs.get("merke")
    model = specs.get("Modell") or specs.get("modell")
    model_year = _parse_int(specs.get("Modellår") or specs.get("modellår"))
    mileage = _parse_int(specs.get("Kilometerstand") or specs.get("kilometerstand"))
    price = _parse_int(price_text)

    return AdRecord(
        ad_id=ad_id,
        fetched_at=datetime.utcnow(),
        title=title,
        price_nok=price,
        location=location,
        brand=brand,
        model=model,
        model_year=model_year,
        mileage_km=mileage,
        specs=specs,
    )
