"""Parse auxiliary data from car ad descriptions using OpenAI API.

This module extracts additional information from car ad descriptions that isn't
available in the structured fields, such as tire sets and trim levels.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import StrEnum

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

# Try to load environment variables from .env file if dotenv is available
# Falls back to os.environ (useful for GitHub Codespaces, Docker, etc.)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # dotenv not available, will use system environment variables
    pass


logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", None)


class TireSet(StrEnum):
    """Enum for tire set options."""

    ONE_SET = "one_set"
    TWO_SETS = "two_sets"
    UNKNOWN = "unknown"


class ImportDeterminationMethod(StrEnum):
    """How a car's import status was determined."""

    CHASSIS_LOOKUP = "chassis_lookup"  # Vegvesen API via chassis nr (VIN)
    REGISTRATION_LOOKUP = "registration_lookup"  # Vegvesen API via reg nr
    DESCRIPTION_ANALYSIS = "description_analysis"  # OpenAI free-text analysis
    NOT_CHECKED = "not_checked"  # no method attempted
    INCONCLUSIVE = "inconclusive"  # checked but no evidence found
    CONDITION_REPORT = "condition_report"  # (future) tilstandsrapport PDF


@dataclass
class AuxData:
    """Auxiliary data extracted from car ad description.

    This dataclass holds additional information parsed from the free-text
    description that isn't available in structured fields.

    Attributes:
        tire_sets: Whether the car comes with one or two sets of tires
        trim_level: The trim/equipment level (e.g., "GT-Line", "Premium", "Elegance")
        raw_description: The original description text that was parsed
        imported: True if the description explicitly states the car was imported,
            False if it explicitly states it was sold new in Norway, or None when
            the description contains no clear evidence either way.
    """

    tire_sets: TireSet
    trim_level: str | None
    raw_description: str
    imported: bool | None = None

    def __repr__(self) -> str:
        return (
            f"AuxData(tire_sets={self.tire_sets.value}, "
            f"trim_level={self.trim_level!r}, "
            f"imported={self.imported!r}, "
            f"raw_description={self.raw_description[:50]!r}...)"
        )


def extract_description_from_ad(driver: WebDriver, ad_id: str) -> str | None:
    """Extract the description text from a FINN car ad page.

    Args:
        driver: Selenium WebDriver with the ad page already loaded
        ad_id: The FINN ad ID (for logging purposes)

    Returns:
        The description text if found, None otherwise
    """
    # Try multiple possible selectors for the description section
    selectors = [
        "div[data-testid='description-text']",
        "div.import-decoration",
        "div.import-description",
        "div.u-word-break",
        "section.panel p",
    ]

    for selector in selectors:
        try:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            text = element.get_attribute("textContent")
            if text and text.strip():
                return text.strip()
        except NoSuchElementException:
            continue

    logger.warning(f"No description found for ad {ad_id}")
    return None


def parse_aux_data_with_openai(description: str) -> AuxData:
    """Parse auxiliary data from ad description using OpenAI API.

    Args:
        description: The ad description text to parse

    Returns:
        AuxData object with parsed information

    Raises:
        ValueError: If OPENAI_API_KEY is not set in the environment
        ImportError: If openai package is not installed
    """
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "The 'openai' package is required for this functionality. Install it with: pip install openai"
        ) from exc

    # Get API key
    if not OPENAI_API_KEY:
        raise ValueError("OpenAI API key must be set via the OPENAI_API_KEY environment variable")

    # Initialize OpenAI client
    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    # Construct the prompt
    system_prompt = """\
You are a helpful assistant that extracts structured information from Norwegian car advertisements.
Your task is to analyze the ad description and extract:

1. Tire sets: Determine if the car comes with one set or two sets of tires (including winter tires/wheels)
   - Return "two_sets" if the ad mentions: vinterhjul, vinterdekk, ekstra dekk, 2 sett dekk, or similar
   - Return "one_set" if only summer tires or no mention of extra tires
   - Return "unknown" if it's unclear

2. Trim level: Extract the trim/equipment level name if mentioned
   - Examples: "GT-Line", "Premium", "Elegance", "Executive", "Teknikk", "Comfort", "Sport"
   - Return null if no trim level is mentioned or if it's unclear
   - Sometimes this is part of the model specification

3. Imported: Whether the car was imported from abroad or sold new in Norway.
   IMPORTANT — this field has strict rules to avoid false positives:
   - Return true ONLY if the description explicitly states the car was imported
     (e.g. "importert fra Tyskland", "bruktimportert", "bruktimport", "innført fra utlandet",
     "tidligere utenlandsk kjennemerke", "solgt brukt fra utlandet").
   - Return false ONLY if the description explicitly states the car was sold new in Norway
     (e.g. "norsklevert", "solgt ny i Norge", "levert ny hos norsk forhandler",
     "norsk bil fra ny").
   - Return null in ALL other cases — including when the description says nothing
     about import status. Most ads will not mention this at all.
   - Do NOT infer import status from indirect clues such as mileage, equipment level,
     model variant, price, or country of manufacture. Return null when in doubt.

Respond ONLY with valid JSON in this exact format:
{
    "tire_sets": "one_set" | "two_sets" | "unknown",
    "trim_level": "string" | null,
    "imported": true | false | null
}"""

    user_prompt = f"""Analyze this Norwegian car ad description and extract tire sets and trim level:

{description}"""

    try:
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Using cheaper, faster model for structured extraction
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0,  # Deterministic output
            response_format={"type": "json_object"},
        )

        # Parse response
        import json

        result = json.loads(response.choices[0].message.content)

        # Validate and construct AuxData
        tire_sets_str = result.get("tire_sets", "unknown")
        try:
            tire_sets = TireSet(tire_sets_str)
        except ValueError:
            logger.warning(f"Invalid tire_sets value '{tire_sets_str}', defaulting to UNKNOWN")
            tire_sets = TireSet.UNKNOWN

        trim_level = result.get("trim_level")

        # Extract imported: only accept explicit true/false; treat anything else as None
        raw_imported = result.get("imported")
        if raw_imported is True:
            imported = True
        elif raw_imported is False:
            imported = False
        else:
            imported = None

        return AuxData(
            tire_sets=tire_sets,
            trim_level=trim_level,
            raw_description=description,
            imported=imported,
        )

    except Exception as exc:
        logger.error(f"Error calling OpenAI API: {exc}")
        # Return conservative defaults on error
        return AuxData(
            tire_sets=TireSet.UNKNOWN,
            trim_level=None,
            raw_description=description,
            imported=None,
        )


def parse_aux_data_from_ad(
    driver: WebDriver,
    ad_id: str,
) -> AuxData | None:
    """Extract and parse auxiliary data from a car ad.

    This is a convenience function that combines description extraction
    and OpenAI parsing in one step.

    Args:
        driver: Selenium WebDriver with the ad page loaded
        ad_id: The FINN ad ID

    Returns:
        AuxData object if description was found and parsed, None otherwise
    """
    description = extract_description_from_ad(driver, ad_id)
    if description is None:
        return None

    return parse_aux_data_with_openai(description)
