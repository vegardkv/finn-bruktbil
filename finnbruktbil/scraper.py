from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

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


def _extract_key_info(root: WebElement) -> Dict[str, str]:
    key_info: Dict[str, str] = {}
    for dl in root.find_elements(By.TAG_NAME, "dl"):
        keys = dl.find_elements(By.TAG_NAME, "dt")
        values = dl.find_elements(By.TAG_NAME, "dd")
        if len(keys) != len(values):
            continue
        for key_el, value_el in zip(keys, values):
            # Use textContent which gets all text (even hidden)
            raw_key = (key_el.get_attribute("textContent") or "").strip()
            raw_value = (value_el.get_attribute("textContent") or "").strip()
            if not raw_key or not raw_value:
                continue

            key_line = raw_key.splitlines()[0].strip()
            key = key_line.rstrip(":")

            value = raw_value.replace("\xa0", " ").replace("\u202f", " ")
            value = " ".join(part for part in value.split())

            if key and value and key not in key_info:
                key_info[key] = value
    return key_info


def _parse_date_string(date_str: Optional[str]) -> Optional[str]:
    """Parse Norwegian date format (DD.MM.YYYY) to ISO format (YYYY-MM-DD)."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
        return dt.date().isoformat()
    except (ValueError, AttributeError):
        return None


# Mapping from expected field names to key_info keys
FIELD_MAPPING = {
    "omregistrering": "Omregistrering",
    "pris_eks_omreg": "Pris eksl. omreg.",
    "årsavgift_info": "Årsavgift",
    "merke": "Merke",
    "modell": "Modell",
    "modellår": "Modellår",
    "karosseri": "Karosseri",
    "drivstoff": "Drivstoff",
    "effekt_hk": "Effekt",
    "kilometerstand_km": "Kilometerstand",
    "batterikapasitet_kWh": "Batterikapasitet",
    "rekkevidde_km": "Rekkevidde (WLTP)",
    "girkasse": "Girkasse",
    "maksimal_tilhengervekt_kg": "Maksimal tilhengervekt",
    "hjuldrift": "Hjuldrift",
    "vekt_kg": "Vekt",
    "seter": "Seter",
    "dører": "Dører",
    "bagasjerom_volum_l": "Størrelse på bagasjerom",
    "farge": "Farge",
    "fargebeskrivelse": "Fargebeskrivelse",
    "interiørfarge": "Interiørfarge",
    "bilen_står_i": "Bilen står i",
    "neste_eu_kontroll": "Neste frist for EU-kontroll",
    "avgiftsklasse": "Avgiftsklasse",
    "registreringsnummer": "Registreringsnummer",
    "chassisnummer": "Chassis nr. (VIN)",
    "førstegangsregistrert": "1. gang registrert",
    "eiere": "Eiere",
    "garanti": "Garanti",
    "salgsform": "Salgsform",
}


def scrape_ad(driver, ad_id: str) -> Optional[AdRecord]:
    driver.get(f"{AD_BASE_URL}{ad_id}")
    if not wait_for_elements(driver, "h1", timeout=15):
        return None

    title = _text_or_none(driver, "h1")
    
    try:
        key_info_section = driver.find_element(By.CSS_SELECTOR, ".key-info-section")
        key_info = _extract_key_info(key_info_section)
    except NoSuchElementException:
        print(f"Warning: No key-info-section found for ad {ad_id}")
        key_info = {}

    # Track which keys were used and which were not
    expected_keys = set(FIELD_MAPPING.values())
    found_keys = set(key_info.keys())
    
    missing_keys = expected_keys - found_keys
    redundant_keys = found_keys - expected_keys
    
    if missing_keys:
        print(f"Missing keys for ad {ad_id}: {sorted(missing_keys)}")
    if redundant_keys:
        print(f"Redundant keys for ad {ad_id}: {sorted(redundant_keys)}")

    # Map key_info to AdRecord fields
    return AdRecord(
        ad_id=ad_id,
        fetched_at=datetime.now(),
        title=title,
        omregistrering=_parse_int(key_info.get(FIELD_MAPPING["omregistrering"])),
        pris_eks_omreg=_parse_int(key_info.get(FIELD_MAPPING["pris_eks_omreg"])),
        årsavgift_info=key_info.get(FIELD_MAPPING["årsavgift_info"]),
        merke=key_info.get(FIELD_MAPPING["merke"]),
        modell=key_info.get(FIELD_MAPPING["modell"]),
        modellår=_parse_int(key_info.get(FIELD_MAPPING["modellår"])),
        karosseri=key_info.get(FIELD_MAPPING["karosseri"]),
        drivstoff=key_info.get(FIELD_MAPPING["drivstoff"]),
        effekt_hk=_parse_int(key_info.get(FIELD_MAPPING["effekt_hk"])),
        kilometerstand_km=_parse_int(key_info.get(FIELD_MAPPING["kilometerstand_km"])),
        batterikapasitet_kWh=_parse_int(key_info.get(FIELD_MAPPING["batterikapasitet_kWh"])),
        rekkevidde_km=_parse_int(key_info.get(FIELD_MAPPING["rekkevidde_km"])),
        girkasse=key_info.get(FIELD_MAPPING["girkasse"]),
        maksimal_tilhengervekt_kg=_parse_int(key_info.get(FIELD_MAPPING["maksimal_tilhengervekt_kg"])),
        hjuldrift=key_info.get(FIELD_MAPPING["hjuldrift"]),
        vekt_kg=_parse_int(key_info.get(FIELD_MAPPING["vekt_kg"])),
        seter=_parse_int(key_info.get(FIELD_MAPPING["seter"])),
        dører=_parse_int(key_info.get(FIELD_MAPPING["dører"])),
        bagasjerom_volum_l=_parse_int(key_info.get(FIELD_MAPPING["bagasjerom_volum_l"])),
        farge=key_info.get(FIELD_MAPPING["farge"]),
        fargebeskrivelse=key_info.get(FIELD_MAPPING["fargebeskrivelse"]),
        interiørfarge=key_info.get(FIELD_MAPPING["interiørfarge"]),
        bilen_står_i=key_info.get(FIELD_MAPPING["bilen_står_i"]),
        neste_eu_kontroll=_parse_date_string(key_info.get(FIELD_MAPPING["neste_eu_kontroll"])),
        avgiftsklasse=key_info.get(FIELD_MAPPING["avgiftsklasse"]),
        registreringsnummer=key_info.get(FIELD_MAPPING["registreringsnummer"]),
        chassisnummer=key_info.get(FIELD_MAPPING["chassisnummer"]),
        førstegangsregistrert=_parse_date_string(key_info.get(FIELD_MAPPING["førstegangsregistrert"])),
        eiere=_parse_int(key_info.get(FIELD_MAPPING["eiere"])),
        garanti=key_info.get(FIELD_MAPPING["garanti"]),
        salgsform=key_info.get(FIELD_MAPPING["salgsform"]),
        specs=key_info,  # Store all raw specs
    )
