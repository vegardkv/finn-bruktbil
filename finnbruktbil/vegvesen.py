"""Look up vehicle import status using Statens Vegvesen's open API.

Uses the Enkeltoppslag (single-lookup) REST API at:
  https://akfell-datautlevering.atlas.vegvesen.no/enkeltoppslag/kjoretoydata

Requires a free API key applied for at:
  https://www.vegvesen.no/om+statens+vegvesen/om+organisasjonen/apne-data/api-for-tekniske-kjoretoyopplysninger

Set the key in the SVV_API_KEY environment variable (or .env file).
"""

from __future__ import annotations

import logging
import os
import time
from http import HTTPStatus

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

SVV_API_KEY = os.environ.get("SVV_API_KEY", None)

_ENDPOINT = "https://akfell-datautlevering.atlas.vegvesen.no/enkeltoppslag/kjoretoydata"
_MAX_RETRIES = 3
_RETRY_DELAY_S = 2.0


def lookup_import_status(
    registration_number: str,
) -> tuple[bool | None, str | None]:
    """Look up whether a car was imported using Statens Vegvesen's API.

    Args:
        registration_number: The Norwegian registration number / kjennemerke
            (e.g. "AB12345").  Whitespace is stripped before the request.

    Returns:
        A ``(imported, import_country)`` tuple where:
        - ``imported`` is ``True`` if the vehicle is a used import,
          ``False`` if it has no import record, or ``None`` if the lookup
          failed or was skipped (e.g. no API key configured).
        - ``import_country`` is the country name string (e.g. ``"Tyskland"``)
          when the vehicle is imported and the API provides the information,
          otherwise ``None``.
    """
    reg = registration_number.strip().replace(" ", "")
    if not reg:
        return None, None
    return _lookup({"kjennemerke": reg}, reg)


def lookup_import_status_by_vin(
    chassis_number: str,
) -> tuple[bool | None, str | None]:
    """Look up whether a car was imported using its chassis number (VIN).

    Uses the ``understellsnummer`` query parameter of the same Vegvesen
    Enkeltoppslag endpoint, which returns the identical payload shape as the
    registration-number lookup.

    Args:
        chassis_number: The vehicle's chassis number / VIN
            (``understellsnummer``).  Whitespace is stripped before the
            request; no length validation is performed.

    Returns:
        The same ``(imported, import_country)`` tuple as
        :func:`lookup_import_status`.
    """
    vin = chassis_number.strip().replace(" ", "")
    if not vin:
        return None, None
    return _lookup({"understellsnummer": vin}, vin)


def _lookup(
    params: dict,
    identifier: str,
) -> tuple[bool | None, str | None]:
    """Query the Vegvesen API with the given lookup params and parse the result.

    Args:
        params: Query parameters identifying the vehicle, e.g.
            ``{"kjennemerke": ...}`` or ``{"understellsnummer": ...}``.
        identifier: The lookup value, used only for log messages.
    """
    if not SVV_API_KEY:
        return None, None

    try:
        import requests
    except ImportError:
        logger.warning("'requests' package is not installed; skipping Vegvesen lookup")
        return None, None

    headers = {"SVV-Authorization": f"Apikey {SVV_API_KEY}"}

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = requests.get(
                _ENDPOINT,
                headers=headers,
                params=params,
                timeout=10,
            )
        except requests.RequestException as exc:
            logger.warning(f"Vegvesen API request failed for {identifier!r} (attempt {attempt}): {exc}")
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_S)
            continue

        if response.status_code == HTTPStatus.OK:
            return _parse_response(response.json())

        if response.status_code == HTTPStatus.NOT_FOUND:
            # Vehicle not found in the registry — treat as non-imported Norwegian car.
            return False, None

        if response.status_code in (429, 500, 502, 503, 504):
            logger.warning(
                f"Vegvesen API returned {response.status_code} for {identifier!r} (attempt {attempt}/{_MAX_RETRIES})"
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_S * attempt)
            continue

        # Other unexpected status codes — log and give up.
        logger.warning(f"Vegvesen API returned unexpected status {response.status_code} for {identifier!r}")
        return None, None

    # All retries exhausted.
    return None, None


def _parse_response(data: dict) -> tuple[bool | None, str | None]:
    """Extract import status and country from a Vegvesen API JSON response."""
    try:
        vehicles = data.get("kjoretoydataListe") or []
        if not vehicles:
            return False, None

        vehicle = vehicles[0]
        godkjenning = vehicle.get("godkjenning") or {}
        forstegangs = godkjenning.get("forstegangsGodkjenning") or {}
        bruktimport = forstegangs.get("bruktimport")

        if bruktimport is None:
            return False, None

        # bruktimport is non-null → the car was imported as a used vehicle.
        importland = bruktimport.get("importland") or {}
        country_name: str | None = importland.get("landNavn") or None

        return True, country_name

    except Exception as exc:
        logger.warning(f"Failed to parse Vegvesen API response: {exc}")
        return None, None
