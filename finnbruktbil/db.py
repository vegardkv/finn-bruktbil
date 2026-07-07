from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv
from supabase import Client, create_client

# Load environment variables from .env file
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# DB (ASCII) column name -> in-memory Norwegian column name. Single source of truth
# for both the write path (save_ad_detail) and read path (load_ads_dataframe). Only
# columns whose Supabase (ASCII) name differs from the Norwegian AdRecord name are
# listed; all others map to themselves.
ASCII_TO_NORWEGIAN = {
    "aarsavgift_info": "årsavgift_info",
    "modellaar": "modellår",
    "batterikapasitet_kwh": "batterikapasitet_kWh",
    "doerer": "dører",
    "interioerfarge": "interiørfarge",
    "bilen_staar_i": "bilen_står_i",
    "foerstegangsregistrert": "førstegangsregistrert",
}
NORWEGIAN_TO_ASCII = {v: k for k, v in ASCII_TO_NORWEGIAN.items()}


def _get_client() -> Client:
    """Create and return a Supabase client."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "Supabase credentials not configured. "
            "Set SUPABASE_URL and SUPABASE_KEY environment variables or in .env file."
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


@contextmanager
def db_session() -> Iterator[Client]:
    """Context manager for Supabase client (for API compatibility)."""
    client = _get_client()
    yield client


def initialize_schema(client: Client) -> None:
    """No-op for Supabase - tables are created via the Supabase dashboard.

    Run this SQL in your Supabase SQL Editor to create the required tables:

    CREATE TABLE IF NOT EXISTS ad_ids (
        ad_id TEXT PRIMARY KEY,
        source_url TEXT NOT NULL,
        fetched_by TEXT NOT NULL DEFAULT 'unknown',
        first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_scraped TIMESTAMPTZ,
        scrape_status TEXT NOT NULL DEFAULT 'pending'
    );

    CREATE TABLE IF NOT EXISTS ad_details (
        ad_id TEXT PRIMARY KEY REFERENCES ad_ids(ad_id) ON DELETE CASCADE,
        fetched_at TIMESTAMPTZ NOT NULL,
        title TEXT,
        subtitle TEXT,
        totalpris INTEGER,
        omregistrering INTEGER,
        pris_eks_omreg INTEGER,
        aarsavgift_info TEXT,
        merke TEXT,
        modell TEXT,
        modellaar INTEGER,
        karosseri TEXT,
        drivstoff TEXT,
        effekt_hk INTEGER,
        kilometerstand_km INTEGER,
        batterikapasitet_kwh INTEGER,
        rekkevidde_km INTEGER,
        girkasse TEXT,
        maksimal_tilhengervekt_kg INTEGER,
        hjuldrift TEXT,
        vekt_kg INTEGER,
        seter INTEGER,
        doerer INTEGER,
        bagasjerom_volum_l INTEGER,
        farge TEXT,
        fargebeskrivelse TEXT,
        interioerfarge TEXT,
        bilen_staar_i TEXT,
        neste_eu_kontroll TEXT,
        avgiftsklasse TEXT,
        registreringsnummer TEXT,
        chassisnummer TEXT,
        foerstegangsregistrert TEXT,
        eiere INTEGER,
        garanti TEXT,
        salgsform TEXT,
        raw_spec_json JSONB NOT NULL,
        tire_sets TEXT,
        trim_level TEXT,
        raw_description TEXT,
        sist_oppdatert TEXT,
        solgt BOOLEAN,
        imported BOOLEAN,
        import_country TEXT,
        import_determination_method TEXT
    );

    -- To add these columns to an existing table:
    -- ALTER TABLE ad_details ADD COLUMN IF NOT EXISTS imported BOOLEAN;
    -- ALTER TABLE ad_details ADD COLUMN IF NOT EXISTS import_country TEXT;
    -- ALTER TABLE ad_details ADD COLUMN IF NOT EXISTS import_determination_method TEXT;

    -- Create indexes for common queries
    CREATE INDEX IF NOT EXISTS idx_ad_ids_scrape_status ON ad_ids(scrape_status);
    CREATE INDEX IF NOT EXISTS idx_ad_ids_last_scraped ON ad_ids(last_scraped);
    """
    pass


# Ids per batched query; keeps the in_() filter comfortably inside URL limits.
_ID_CHUNK_SIZE = 200


def upsert_ad_ids(
    client: Client,
    source_url: str,
    ad_ids: Iterable[str],
    *,
    fetched_by: str = "unknown",
) -> None:
    """Insert or update ad IDs in the database.

    New ids are inserted as ``pending``. Ids seen before get their
    ``source_url``/``fetched_by``/``last_seen`` refreshed (``first_seen`` is
    preserved) and previously ``missing`` ids are reset to ``pending``.
    Runs a handful of batched queries per chunk instead of two round trips
    per id.
    """
    now = datetime.now(UTC).isoformat()
    unique_ids = list(dict.fromkeys(ad_ids))

    for start in range(0, len(unique_ids), _ID_CHUNK_SIZE):
        chunk = unique_ids[start : start + _ID_CHUNK_SIZE]

        existing = client.table("ad_ids").select("ad_id, scrape_status").in_("ad_id", chunk).execute()
        existing_ids = {row["ad_id"] for row in existing.data}
        missing_ids = [row["ad_id"] for row in existing.data if row["scrape_status"] == "missing"]

        new_records = [
            {
                "ad_id": ad_id,
                "source_url": source_url,
                "fetched_by": fetched_by,
                "first_seen": now,
                "last_seen": now,
                "scrape_status": "pending",
            }
            for ad_id in chunk
            if ad_id not in existing_ids
        ]
        if new_records:
            client.table("ad_ids").insert(new_records).execute()

        if existing_ids:
            client.table("ad_ids").update({"source_url": source_url, "fetched_by": fetched_by, "last_seen": now}).in_(
                "ad_id", sorted(existing_ids)
            ).execute()

        if missing_ids:
            client.table("ad_ids").update({"scrape_status": "pending"}).in_("ad_id", missing_ids).execute()


@dataclass
class AdRecord:
    ad_id: str
    fetched_at: datetime
    # Basic info
    title: str | None
    subtitle: str | None
    # Pricing
    totalpris: int | None
    omregistrering: int | None
    pris_eks_omreg: int | None
    årsavgift_info: str | None
    # Car details
    merke: str | None
    modell: str | None
    modellår: int | None
    karosseri: str | None
    drivstoff: str | None
    effekt_hk: int | None
    kilometerstand_km: int | None
    batterikapasitet_kWh: int | None
    rekkevidde_km: int | None
    girkasse: str | None
    maksimal_tilhengervekt_kg: int | None
    hjuldrift: str | None
    vekt_kg: int | None
    seter: int | None
    dører: int | None
    bagasjerom_volum_l: int | None
    farge: str | None
    fargebeskrivelse: str | None
    interiørfarge: str | None
    bilen_står_i: str | None
    neste_eu_kontroll: str | None
    avgiftsklasse: str | None
    registreringsnummer: str | None
    chassisnummer: str | None
    førstegangsregistrert: str | None
    eiere: int | None
    garanti: str | None
    salgsform: str | None
    # Raw specs
    specs: dict[str, str]
    # Auxiliary data
    tire_sets: str | None
    trim_level: str | None
    raw_description: str | None
    # Ad metadata
    sist_oppdatert: str | None = None
    solgt: bool | None = None
    # Import status (from Vegvesen API or description analysis)
    imported: bool | None = None
    import_country: str | None = None
    # How the import status was determined (see ImportDeterminationMethod)
    import_determination_method: str | None = None


def save_ad_detail(client: Client, record: AdRecord) -> None:
    """Save or update an ad detail record.

    Maps Norwegian ``AdRecord`` attributes to ASCII Supabase columns. The canonical
    name map is ``ASCII_TO_NORWEGIAN`` (used in reverse on the read path); keep any
    diacritic-named column added here in sync with that mapping.
    """
    data = {
        "ad_id": record.ad_id,
        "fetched_at": record.fetched_at.isoformat(),
        "title": record.title,
        "subtitle": record.subtitle,
        "totalpris": record.totalpris,
        "omregistrering": record.omregistrering,
        "pris_eks_omreg": record.pris_eks_omreg,
        "aarsavgift_info": record.årsavgift_info,
        "merke": record.merke,
        "modell": record.modell,
        "modellaar": record.modellår,
        "karosseri": record.karosseri,
        "drivstoff": record.drivstoff,
        "effekt_hk": record.effekt_hk,
        "kilometerstand_km": record.kilometerstand_km,
        "batterikapasitet_kwh": record.batterikapasitet_kWh,
        "rekkevidde_km": record.rekkevidde_km,
        "girkasse": record.girkasse,
        "maksimal_tilhengervekt_kg": record.maksimal_tilhengervekt_kg,
        "hjuldrift": record.hjuldrift,
        "vekt_kg": record.vekt_kg,
        "seter": record.seter,
        "doerer": record.dører,
        "bagasjerom_volum_l": record.bagasjerom_volum_l,
        "farge": record.farge,
        "fargebeskrivelse": record.fargebeskrivelse,
        "interioerfarge": record.interiørfarge,
        "bilen_staar_i": record.bilen_står_i,
        "neste_eu_kontroll": record.neste_eu_kontroll,
        "avgiftsklasse": record.avgiftsklasse,
        "registreringsnummer": record.registreringsnummer,
        "chassisnummer": record.chassisnummer,
        "foerstegangsregistrert": record.førstegangsregistrert,
        "eiere": record.eiere,
        "garanti": record.garanti,
        "salgsform": record.salgsform,
        "raw_spec_json": record.specs,
        "tire_sets": record.tire_sets,
        "trim_level": record.trim_level,
        "raw_description": record.raw_description,
        "sist_oppdatert": record.sist_oppdatert,
        "solgt": record.solgt,
        "imported": record.imported,
        "import_country": record.import_country,
        "import_determination_method": record.import_determination_method,
    }

    # Upsert ad_details
    client.table("ad_details").upsert(data).execute()

    # Update ad_ids status
    client.table("ad_ids").update(
        {
            "last_scraped": record.fetched_at.isoformat(),
            "scrape_status": "scraped",
        }
    ).eq("ad_id", record.ad_id).execute()


def mark_missing(client: Client, ad_id: str) -> None:
    """Mark an ad as missing (no longer available)."""
    now = datetime.now(UTC).isoformat()
    client.table("ad_ids").update(
        {
            "scrape_status": "missing",
            "last_scraped": now,
        }
    ).eq("ad_id", ad_id).execute()


def fetch_ids_for_scraping(
    client: Client,
    limit: int,
    stale_hours: int | None = None,
    random_order: bool = False,
) -> list[str]:
    """Fetch ad IDs that need to be scraped.

    With ``stale_hours`` set, ids whose ``last_scraped`` is null or older than
    the threshold qualify; otherwise only never-scraped ids do.
    """
    query = client.table("ad_ids").select("ad_id").in_("scrape_status", ["pending", "scraped"])

    if stale_hours is None:
        query = query.is_("last_scraped", "null")
    else:
        threshold = (datetime.now(UTC) - timedelta(hours=stale_hours)).isoformat()
        query = query.or_(f"last_scraped.is.null,last_scraped.lte.{threshold}")

    # Never-scraped ids first, then oldest-scraped. Supabase has no native
    # RANDOM() ordering via the client, so random_order only shuffles within
    # the fetched page.
    result = query.order("last_scraped", nullsfirst=True).limit(limit).execute()

    ids = [row["ad_id"] for row in result.data]

    if random_order:
        import random

        random.shuffle(ids)

    return ids


def _derive_status(solgt) -> str:
    """Derive an availability status from the ``solgt`` flag.

    The scraper sets ``solgt`` for both SOLGT-badged and inactive/removed ads
    (see scraper.py), so this single flag captures both. ``solgt`` may be a
    Python/numpy bool, ``None``, or ``NaN`` (unknown).
    """
    if solgt is None or solgt != solgt:  # None or NaN
        return "unknown"
    return "sold" if solgt else "available"


def _rename_to_norwegian(ads):
    """Rename ASCII Supabase columns back to the Norwegian names the analysis code
    expects, using the shared ``ASCII_TO_NORWEGIAN`` mapping."""
    return ads.rename(columns=ASCII_TO_NORWEGIAN)


def _add_status(ads):
    """Add a derived ``status`` column (available/sold/unknown) from the ``solgt``
    flag, which the scraper sets for both SOLGT-badged and inactive ads."""
    import pandas as pd

    solgt_series = ads["solgt"] if "solgt" in ads.columns else pd.Series([None] * len(ads))
    ads["status"] = [_derive_status(solgt) for solgt in solgt_series]
    return ads


def _flatten_specs(ads):
    """Flatten the ``raw_spec_json`` JSONB column (a dict per row) into ``spec.*``
    columns and drop the original column."""
    import pandas as pd

    if "raw_spec_json" not in ads.columns:
        return ads

    spec_dicts = ads["raw_spec_json"].apply(lambda x: x if isinstance(x, dict) else {})
    specs_df = pd.json_normalize(spec_dicts)
    specs_df.columns = [f"spec.{c}" for c in specs_df.columns]
    return pd.concat([ads.drop(columns=["raw_spec_json"]), specs_df], axis=1)


def load_ads_dataframe():
    """Load all ad details into a pandas DataFrame.

    Reads the raw ``ad_details`` rows and applies the client-side transforms the
    analysis code relies on: rename ASCII columns to Norwegian, derive ``status``,
    and flatten ``raw_spec_json`` into ``spec.*`` columns.
    """
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required to build the analysis dataframe") from exc

    client = _get_client()

    # Fetch all ad details. PostgREST caps responses (1000 rows by default),
    # so page until a short page signals the end.
    page_size = 1000
    rows: list[dict] = []
    while True:
        offset = len(rows)
        result = client.table("ad_details").select("*").range(offset, offset + page_size - 1).execute()
        rows.extend(result.data)
        if len(result.data) < page_size:
            break

    if not rows:
        return pd.DataFrame()

    ads = pd.DataFrame(rows)

    if ads.empty:
        return ads

    ads = _rename_to_norwegian(ads)
    ads = _add_status(ads)
    ads = _flatten_specs(ads)

    return ads
