"""Parse auxiliary data from car ad descriptions using OpenAI API.

This module extracts additional information from car ad descriptions that isn't
available in the structured fields, such as tire sets and trim levels.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

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


class TireSet(str, Enum):
    """Enum for tire set options."""
    ONE_SET = "one_set"
    TWO_SETS = "two_sets"
    UNKNOWN = "unknown"


@dataclass
class AuxData:
    """Auxiliary data extracted from car ad description.
    
    This dataclass holds additional information parsed from the free-text
    description that isn't available in structured fields.
    
    Attributes:
        tire_sets: Whether the car comes with one or two sets of tires
        trim_level: The trim/equipment level (e.g., "GT-Line", "Premium", "Elegance")
        raw_description: The original description text that was parsed
    """
    tire_sets: TireSet
    trim_level: Optional[str]
    raw_description: str

    def __repr__(self) -> str:
        return (
            f"AuxData(tire_sets={self.tire_sets.value}, "
            f"trim_level={self.trim_level!r}, "
            f"raw_description={self.raw_description[:50]!r}...)"
        )


def extract_description_from_ad(driver: WebDriver, ad_id: str) -> Optional[str]:
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
    
    print(f"Warning: No description found for ad {ad_id}")
    return None


def parse_aux_data_with_openai(description: str, api_key: Optional[str] = None) -> AuxData:
    """Parse auxiliary data from ad description using OpenAI API.
    
    Args:
        description: The ad description text to parse
        api_key: OpenAI API key. If None, reads from OPENAI_API_KEY environment variable
    
    Returns:
        AuxData object with parsed information
        
    Raises:
        ValueError: If API key is not provided and not found in environment
        ImportError: If openai package is not installed
    """
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "The 'openai' package is required for this functionality. "
            "Install it with: pip install openai"
        ) from exc
    
    # Get API key
    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenAI API key must be provided either as argument or "
            "via OPENAI_API_KEY environment variable"
        )
    
    # Initialize OpenAI client
    client = openai.OpenAI(api_key=api_key)
    
    # Construct the prompt
    system_prompt = """You are a helpful assistant that extracts structured information from Norwegian car advertisements.
Your task is to analyze the ad description and extract:

1. Tire sets: Determine if the car comes with one set or two sets of tires (including winter tires/wheels)
   - Return "two_sets" if the ad mentions: vinterhjul, vinterdekk, ekstra dekk, 2 sett dekk, or similar
   - Return "one_set" if only summer tires or no mention of extra tires
   - Return "unknown" if it's unclear

2. Trim level: Extract the trim/equipment level name if mentioned
   - Examples: "GT-Line", "Premium", "Elegance", "Executive", "Teknikk", "Comfort", "Sport"
   - Return null if no trim level is mentioned or if it's unclear
   - Sometimes this is part of the model specification

Respond ONLY with valid JSON in this exact format:
{
    "tire_sets": "one_set" | "two_sets" | "unknown",
    "trim_level": "string" | null
}"""

    user_prompt = f"""Analyze this Norwegian car ad description and extract tire sets and trim level:

{description}"""

    try:
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Using cheaper, faster model for structured extraction
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,  # Deterministic output
            response_format={"type": "json_object"}
        )
        
        # Parse response
        import json
        result = json.loads(response.choices[0].message.content)
        
        # Validate and construct AuxData
        tire_sets_str = result.get("tire_sets", "unknown")
        try:
            tire_sets = TireSet(tire_sets_str)
        except ValueError:
            print(f"Warning: Invalid tire_sets value '{tire_sets_str}', defaulting to UNKNOWN")
            tire_sets = TireSet.UNKNOWN
        
        trim_level = result.get("trim_level")
        
        return AuxData(
            tire_sets=tire_sets,
            trim_level=trim_level,
            raw_description=description
        )
        
    except Exception as exc:
        print(f"Error calling OpenAI API: {exc}")
        # Return conservative defaults on error
        return AuxData(
            tire_sets=TireSet.UNKNOWN,
            trim_level=None,
            raw_description=description
        )


def parse_aux_data_from_ad(
    driver: WebDriver,
    ad_id: str,
    api_key: Optional[str] = None
) -> Optional[AuxData]:
    """Extract and parse auxiliary data from a car ad.
    
    This is a convenience function that combines description extraction
    and OpenAI parsing in one step.
    
    Args:
        driver: Selenium WebDriver with the ad page loaded
        ad_id: The FINN ad ID
        api_key: OpenAI API key (optional, reads from env if not provided)
    
    Returns:
        AuxData object if description was found and parsed, None otherwise
    """
    description = extract_description_from_ad(driver, ad_id)
    if description is None:
        return None
    
    return parse_aux_data_with_openai(description, api_key)


# Example usage
if __name__ == "__main__":
    # Example Norwegian car ad description
    example_description = """
    Velkommen til Bilsenteret R2 AS hvor fornøyde bileiere står i fokus!
    
    Kia EV9 GT-Line AWD 7 seter med vinterhjul og hengerfeste!
    
    Denne flotte bilen er utstyrt med:
    - Panoramatak
    - Skinninteriør
    - Adaptiv cruise control
    - 360 graders kamera
    - Elektrisk bakluke
    - Ekstra sett med vinterhjul på felg
    
    Bilen er som ny og har full servicehistorikk.
    Kun 21.500 km kjørt!
    
    Ta kontakt for visning og prøvekjøring.
    """
    
    try:
        aux_data = parse_aux_data_with_openai(example_description)
        print(f"Parsed data: {aux_data}")
        print(f"Tire sets: {aux_data.tire_sets.value}")
        print(f"Trim level: {aux_data.trim_level}")
    except (ValueError, ImportError) as e:
        print(f"Cannot run example: {e}")
