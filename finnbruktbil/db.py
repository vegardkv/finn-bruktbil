from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Iterator, List, Optional

from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from .env file
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


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


def upsert_ad_ids(
    client: Client,
    source_url: str,
    ad_ids: Iterable[str],
    *,
    fetched_by: str = "unknown",
) -> None:
    """Insert or update ad IDs in the database."""
    now = datetime.now(timezone.utc).isoformat()
    
    records = [
        {
            "ad_id": ad_id,
            "source_url": source_url,
            "fetched_by": fetched_by,
            "first_seen": now,
            "last_seen": now,
            "scrape_status": "pending",
        }
        for ad_id in ad_ids
    ]
    
    if not records:
        return
    
    # Supabase upsert: on conflict, update last_seen and conditionally scrape_status
    # We need to handle this in batches and with custom logic
    for record in records:
        # Check if exists
        existing = client.table("ad_ids").select("ad_id, scrape_status").eq("ad_id", record["ad_id"]).execute()
        
        if existing.data:
            # Update existing record
            update_data = {
                "source_url": record["source_url"],
                "fetched_by": record["fetched_by"],
                "last_seen": record["last_seen"],
            }
            # Reset status from 'missing' to 'pending'
            if existing.data[0]["scrape_status"] == "missing":
                update_data["scrape_status"] = "pending"
            
            client.table("ad_ids").update(update_data).eq("ad_id", record["ad_id"]).execute()
        else:
            # Insert new record
            client.table("ad_ids").insert(record).execute()


@dataclass
class AdRecord:
    ad_id: str
    fetched_at: datetime
    # Basic info
    title: Optional[str]
    subtitle: Optional[str]
    # Pricing
    totalpris: Optional[int]
    omregistrering: Optional[int]
    pris_eks_omreg: Optional[int]
    årsavgift_info: Optional[str]
    # Car details
    merke: Optional[str]
    modell: Optional[str]
    modellår: Optional[int]
    karosseri: Optional[str]
    drivstoff: Optional[str]
    effekt_hk: Optional[int]
    kilometerstand_km: Optional[int]
    batterikapasitet_kWh: Optional[int]
    rekkevidde_km: Optional[int]
    girkasse: Optional[str]
    maksimal_tilhengervekt_kg: Optional[int]
    hjuldrift: Optional[str]
    vekt_kg: Optional[int]
    seter: Optional[int]
    dører: Optional[int]
    bagasjerom_volum_l: Optional[int]
    farge: Optional[str]
    fargebeskrivelse: Optional[str]
    interiørfarge: Optional[str]
    bilen_står_i: Optional[str]
    neste_eu_kontroll: Optional[str]
    avgiftsklasse: Optional[str]
    registreringsnummer: Optional[str]
    chassisnummer: Optional[str]
    førstegangsregistrert: Optional[str]
    eiere: Optional[int]
    garanti: Optional[str]
    salgsform: Optional[str]
    # Raw specs
    specs: Dict[str, str]
    # Auxiliary data
    tire_sets: Optional[str]
    trim_level: Optional[str]
    raw_description: Optional[str]
    # Ad metadata
    sist_oppdatert: Optional[str] = None
    solgt: Optional[bool] = None
    # Import status (from Vegvesen API or description analysis)
    imported: Optional[bool] = None
    import_country: Optional[str] = None
    # How the import status was determined (see ImportDeterminationMethod)
    import_determination_method: Optional[str] = None


def save_ad_detail(client: Client, record: AdRecord) -> None:
    """Save or update an ad detail record."""
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
    client.table("ad_ids").update({
        "last_scraped": record.fetched_at.isoformat(),
        "scrape_status": "scraped",
    }).eq("ad_id", record.ad_id).execute()


def mark_missing(client: Client, ad_id: str) -> None:
    """Mark an ad as missing (no longer available)."""
    now = datetime.now(timezone.utc).isoformat()
    client.table("ad_ids").update({
        "scrape_status": "missing",
        "last_scraped": now,
    }).eq("ad_id", ad_id).execute()


def fetch_ids_for_scraping(
    client: Client,
    limit: int,
    stale_hours: Optional[int] = None,
    random_order: bool = False,
) -> List[str]:
    """Fetch ad IDs that need to be scraped."""
    query = client.table("ad_ids").select("ad_id, last_scraped").in_("scrape_status", ["pending", "scraped"])
    
    if stale_hours is None:
        query = query.is_("last_scraped", "null")
    else:
        threshold = (datetime.now(timezone.utc) - timedelta(hours=stale_hours)).isoformat()
        # Get records where last_scraped is null OR older than threshold
        # Supabase doesn't support OR easily, so we'll fetch and filter
        pass  # We'll handle this differently
    
    query = query.limit(limit)
    
    # Note: Supabase doesn't have native RANDOM() ordering via the client
    # For random order, we'd need to use a database function or fetch more and shuffle
    if not random_order:
        query = query.order("last_scraped", nullsfirst=True)
    
    result = query.execute()
    
    ids = [row["ad_id"] for row in result.data]
    
    # If stale_hours is set, we need additional logic to include stale records
    if stale_hours is not None:
        threshold = datetime.now(timezone.utc) - timedelta(hours=stale_hours)
        # Filter to include null or stale
        filtered_ids = []
        for row in result.data:
            last_scraped = row.get("last_scraped")
            if last_scraped is None:
                filtered_ids.append(row["ad_id"])
            else:
                # Parse the timestamp and compare
                try:
                    scraped_dt = datetime.fromisoformat(last_scraped.replace("Z", "+00:00"))
                    if scraped_dt <= threshold:
                        filtered_ids.append(row["ad_id"])
                except (ValueError, AttributeError):
                    filtered_ids.append(row["ad_id"])
        ids = filtered_ids[:limit]
    
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


def load_ads_dataframe():
    """Load all ad details into a pandas DataFrame."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required to build the analysis dataframe") from exc
    
    client = _get_client()
    
    # Fetch all ad details
    result = client.table("ad_details").select("*").execute()
    
    if not result.data:
        return pd.DataFrame()
    
    ads = pd.DataFrame(result.data)
    
    if ads.empty:
        return ads
    
    # Rename columns back to Norwegian for compatibility with existing code
    column_mapping = {
        "aarsavgift_info": "årsavgift_info",
        "modellaar": "modellår",
        "batterikapasitet_kwh": "batterikapasitet_kWh",
        "doerer": "dører",
        "interioerfarge": "interiørfarge",
        "bilen_staar_i": "bilen_står_i",
        "foerstegangsregistrert": "førstegangsregistrert",
    }
    ads = ads.rename(columns=column_mapping)

    # Derive a single availability status from the solgt flag (which the scraper
    # sets for both SOLGT-badged and inactive ads).
    solgt_series = ads["solgt"] if "solgt" in ads.columns else pd.Series([None] * len(ads))
    ads["status"] = [_derive_status(solgt) for solgt in solgt_series]

    # Handle raw_spec_json - it's already a dict from Supabase JSONB
    if "raw_spec_json" in ads.columns:
        spec_dicts = ads["raw_spec_json"].apply(
            lambda x: x if isinstance(x, dict) else {}
        )
        specs_df = pd.json_normalize(spec_dicts)
        specs_df.columns = [f"spec.{c}" for c in specs_df.columns]
        ads = pd.concat([ads.drop(columns=["raw_spec_json"]), specs_df], axis=1)
    
    return ads
