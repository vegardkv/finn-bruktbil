from __future__ import annotations

import logging
from datetime import datetime

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from .browser import wait_for_elements
from .db import AdRecord

logger = logging.getLogger(__name__)

AD_BASE_URL = "https://www.finn.no/mobility/item/"


def _text_or_none(driver, selector: str) -> str | None:
    try:
        element = driver.find_element(By.CSS_SELECTOR, selector)
    except NoSuchElementException:
        return None
    text = (element.get_attribute("textContent") or "").strip()
    return text or None


def _get_text_content(element: WebElement) -> str:
    """Extract text content from an element using textContent attribute.

    This is more reliable than .text as it gets all text including hidden elements.
    """
    raw_text = (element.get_attribute("textContent") or "").strip()
    # Normalize whitespace
    normalized = raw_text.replace("\xa0", " ").replace("\u202f", " ")
    return " ".join(part for part in normalized.split())


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


# Selectors that have held the specification <dl>, newest markup first. FINN
# renames these wrappers now and then, so try each in turn before giving up.
KEY_INFO_SELECTORS = (".key-info", ".key-info-section", ".specifications-area")


def _key_text(key_el: WebElement) -> str:
    """Text of a <dt>, minus any tooltip help text rendered inside it.

    FINN wraps the little "?" help popovers in a <w-attention> custom element
    whose message lives in the light DOM, so a plain textContent read glues the
    whole tooltip onto the label (e.g. "Rekkevidde (WLTP)WLTP er et maltall...").
    """
    text = _get_text_content(key_el)
    for tooltip in key_el.find_elements(By.CSS_SELECTOR, "w-attention, [slot='message']"):
        tooltip_text = _get_text_content(tooltip)
        if tooltip_text:
            text = text.replace(tooltip_text, " ")
    return " ".join(text.split())


def _extract_key_info(root: WebElement) -> dict[str, str]:
    key_info: dict[str, str] = {}
    for dl in root.find_elements(By.TAG_NAME, "dl"):
        keys = dl.find_elements(By.TAG_NAME, "dt")
        values = dl.find_elements(By.TAG_NAME, "dd")
        if len(keys) != len(values):
            continue
        for key_el, value_el in zip(keys, values, strict=True):
            raw_key = _key_text(key_el)
            raw_value = _get_text_content(value_el)
            if not raw_key or not raw_value:
                continue

            key_line = raw_key.splitlines()[0].strip()
            key = key_line.rstrip(":")

            if key and raw_value and key not in key_info:
                key_info[key] = raw_value
    return key_info


def _parse_date_string(date_str: str | None) -> str | None:
    """Parse Norwegian date format (DD.MM.YYYY) to ISO format (YYYY-MM-DD)."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
        return dt.date().isoformat()
    except (ValueError, AttributeError):
        return None


_NORWEGIAN_MONTHS = {
    "januar": 1,
    "februar": 2,
    "mars": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}


def _parse_norwegian_datetime(date_str: str | None) -> str | None:
    """Parse Norwegian long-form datetime (e.g. '22. oktober 2025, 16:12') to ISO format."""
    if not date_str:
        return None
    try:
        # Expected formats: "22. oktober 2025, 16:12" or "22. oktober 2025"
        date_str = date_str.strip()
        if "," in date_str:
            date_part, time_part = date_str.split(",", 1)
            time_part = time_part.strip()
        else:
            date_part = date_str
            time_part = None

        parts = date_part.strip().split()
        # parts: ["22.", "oktober", "2025"]
        day = int(parts[0].rstrip("."))
        month = _NORWEGIAN_MONTHS.get(parts[1].lower())
        year = int(parts[2])
        if month is None:
            return None
        if time_part:
            return f"{year:04d}-{month:02d}-{day:02d}T{time_part}"
        return f"{year:04d}-{month:02d}-{day:02d}"
    except (ValueError, AttributeError, IndexError):
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


def scrape_ad(driver, ad_id: str, parse_aux_data: bool = False) -> AdRecord | None:
    driver.get(f"{AD_BASE_URL}{ad_id}")
    if not wait_for_elements(driver, "h1", timeout=15):
        return None

    title = _text_or_none(driver, "h1")

    # Extract subtitle - the paragraph right after the h1 title
    subtitle = None
    try:
        # Look for the subtitle that comes after h1
        h1_elem = driver.find_element(By.CSS_SELECTOR, "h1")
        parent = h1_elem.find_element(By.XPATH, "..")
        subtitle_elem = parent.find_element(By.CSS_SELECTOR, "p.s-text-subtle")
        subtitle_text = _get_text_content(subtitle_elem)
        subtitle = subtitle_text or None
    except NoSuchElementException:
        pass

    # Extract total price - look for "Totalpris" label
    totalpris = None
    try:
        # Find the element containing "Totalpris" text
        price_label = driver.find_element(By.XPATH, "//p[contains(text(), 'Totalpris')]")
        # Get the sibling h2 that contains the price
        price_section = price_label.find_element(By.XPATH, "..")
        price_elem = price_section.find_element(By.CSS_SELECTOR, "h2 span.t2")
        totalpris = _parse_int(_get_text_content(price_elem))
    except NoSuchElementException:
        pass

    key_info = {}
    for selector in KEY_INFO_SELECTORS:
        sections = driver.find_elements(By.CSS_SELECTOR, selector)
        if sections:
            key_info = _extract_key_info(sections[0])
            if key_info:
                break
    if not key_info:
        logger.warning(
            f"No key info found for ad {ad_id} using {list(KEY_INFO_SELECTORS)}; "
            "falling back to scanning every <dl> on the page"
        )
        key_info = _extract_key_info(driver.find_element(By.TAG_NAME, "body"))
        if not key_info:
            logger.warning(f"No key info at all for ad {ad_id} - FINN's markup has probably changed")

    # Track which keys were used and which were not
    expected_keys = set(FIELD_MAPPING.values())
    found_keys = set(key_info.keys())

    missing_keys = expected_keys - found_keys
    redundant_keys = found_keys - expected_keys

    if missing_keys:
        logger.info(f"Missing keys for ad {ad_id}: {sorted(missing_keys)}")
    if redundant_keys:
        logger.info(f"Redundant keys for ad {ad_id}: {sorted(redundant_keys)}")

    # Check for SOLGT (sold) badge
    solgt = False
    try:
        for el in driver.find_elements(By.XPATH, "//*[normalize-space(text())='SOLGT']"):
            if el.get_attribute("textContent").strip() == "SOLGT":
                solgt = True
                break
    except Exception:
        pass

    # An ad that has been made inactive (sold or taken off the market by the
    # seller) still renders its title, but shows a banner: "Denne annonsen er
    # ikke lenger tilgjengelig". FINN often flips ads straight to inactive
    # without ever showing the SOLGT badge, so treat inactive as sold.
    if not solgt:
        try:
            if driver.find_elements(By.XPATH, "//*[contains(text(), 'ikke lenger tilgjengelig')]"):
                solgt = True
        except Exception:
            pass

    # Extract "Sist oppdatert" (last modified) from the Annonseinformasjon section
    sist_oppdatert = None
    try:
        label = driver.find_element(By.XPATH, "//p[normalize-space(text())='Sist oppdatert']")
        value_el = label.find_element(By.XPATH, "following-sibling::p[1]")
        sist_oppdatert = _parse_norwegian_datetime(value_el.get_attribute("textContent").strip())
    except NoSuchElementException:
        pass

    # Determine import status, setting the determination method as each step runs:
    #   1. Primary: Vegvesen API lookup using the chassis number / VIN (needs SVV_API_KEY);
    #      the VIN is almost always present in the ad's key-info.
    #   2. Secondary: Vegvesen API lookup using the registration number, only when the
    #      VIN lookup was inconclusive.
    #   3. Fallback: OpenAI description analysis, only when it finds explicit evidence.
    from .aux_data_parser import ImportDeterminationMethod
    from .vegvesen import SVV_API_KEY, lookup_import_status, lookup_import_status_by_vin

    tire_sets_value = None
    trim_level_value = None
    raw_description_value = None
    imported_value: bool | None = None
    import_country_value: str | None = None
    import_method = ImportDeterminationMethod.NOT_CHECKED

    # Primary: Vegvesen chassis-number (VIN) lookup.
    chassis_nr = key_info.get(FIELD_MAPPING["chassisnummer"])
    if chassis_nr and SVV_API_KEY:
        try:
            imported_value, import_country_value = lookup_import_status_by_vin(chassis_nr)
        except Exception as exc:
            logger.warning(f"Vegvesen VIN lookup failed for ad {ad_id}: {exc}")
        import_method = (
            ImportDeterminationMethod.CHASSIS_LOOKUP  # incl. 404 -> not imported
            if imported_value is not None
            else ImportDeterminationMethod.INCONCLUSIVE
        )

    # Secondary: Vegvesen reg-nr lookup, only if the VIN lookup was inconclusive.
    reg_nr = key_info.get(FIELD_MAPPING["registreringsnummer"])
    if imported_value is None and reg_nr and SVV_API_KEY:
        try:
            imported_value, import_country_value = lookup_import_status(reg_nr)
        except Exception as exc:
            logger.warning(f"Vegvesen lookup failed for ad {ad_id}: {exc}")
        import_method = (
            ImportDeterminationMethod.REGISTRATION_LOOKUP  # incl. 404 -> not imported
            if imported_value is not None
            else ImportDeterminationMethod.INCONCLUSIVE
        )

    # Auxiliary data is always parsed when enabled (tire sets / trim level); it also
    # serves as the import fallback when the reg-nr lookup was inconclusive.
    if parse_aux_data:
        try:
            from .aux_data_parser import parse_aux_data_from_ad

            aux_data = parse_aux_data_from_ad(driver, ad_id)
            if aux_data:
                tire_sets_value = aux_data.tire_sets.value
                trim_level_value = aux_data.trim_level
                raw_description_value = aux_data.raw_description
                if imported_value is None:
                    if aux_data.imported is not None:
                        imported_value = aux_data.imported
                        import_method = ImportDeterminationMethod.DESCRIPTION_ANALYSIS
                    else:
                        import_method = ImportDeterminationMethod.INCONCLUSIVE
        except Exception as exc:
            logger.warning(f"Failed to parse auxiliary data for ad {ad_id}: {exc}")

    import_method_value = import_method.value

    # Map key_info to AdRecord fields
    return AdRecord(
        ad_id=ad_id,
        fetched_at=datetime.now(),
        title=title,
        subtitle=subtitle,
        totalpris=totalpris,
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
        tire_sets=tire_sets_value,
        trim_level=trim_level_value,
        raw_description=raw_description_value,
        sist_oppdatert=sist_oppdatert,
        solgt=solgt,
        imported=imported_value,
        import_country=import_country_value,
        import_determination_method=import_method_value,
    )
