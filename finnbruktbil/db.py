from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

DEFAULT_DB_PATH = Path("data") / "finn.db"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    _ensure_parent(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_session(db_path: Path | str = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ad_ids (
            ad_id TEXT PRIMARY KEY,
            source_url TEXT NOT NULL,
            fetched_by TEXT NOT NULL DEFAULT 'unknown',
            first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_scraped TIMESTAMP,
            scrape_status TEXT NOT NULL DEFAULT 'pending'
        );

        CREATE TABLE IF NOT EXISTS ad_details (
            ad_id TEXT PRIMARY KEY,
            fetched_at TIMESTAMP NOT NULL,
            title TEXT,
            subtitle TEXT,
            totalpris INTEGER,
            omregistrering INTEGER,
            pris_eks_omreg INTEGER,
            årsavgift_info TEXT,
            merke TEXT,
            modell TEXT,
            modellår INTEGER,
            karosseri TEXT,
            drivstoff TEXT,
            effekt_hk INTEGER,
            kilometerstand_km INTEGER,
            batterikapasitet_kWh INTEGER,
            rekkevidde_km INTEGER,
            girkasse TEXT,
            maksimal_tilhengervekt_kg INTEGER,
            hjuldrift TEXT,
            vekt_kg INTEGER,
            seter INTEGER,
            dører INTEGER,
            bagasjerom_volum_l INTEGER,
            farge TEXT,
            fargebeskrivelse TEXT,
            interiørfarge TEXT,
            bilen_står_i TEXT,
            neste_eu_kontroll TEXT,
            avgiftsklasse TEXT,
            registreringsnummer TEXT,
            chassisnummer TEXT,
            førstegangsregistrert TEXT,
            eiere INTEGER,
            garanti TEXT,
            salgsform TEXT,
            raw_spec_json TEXT NOT NULL,
            FOREIGN KEY (ad_id) REFERENCES ad_ids (ad_id) ON DELETE CASCADE
        );
        """
    )

    _ensure_column(conn, "ad_ids", "fetched_by", "TEXT NOT NULL DEFAULT 'unknown'")
    _ensure_column(conn, "ad_details", "subtitle", "TEXT")
    _ensure_column(conn, "ad_details", "totalpris", "INTEGER")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def upsert_ad_ids(
    conn: sqlite3.Connection,
    source_url: str,
    ad_ids: Iterable[str],
    *,
    fetched_by: str = "unknown",
) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn.executemany(
        """
        INSERT INTO ad_ids (ad_id, source_url, fetched_by, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(ad_id) DO UPDATE SET
            source_url = excluded.source_url,
            fetched_by = excluded.fetched_by,
            last_seen = excluded.last_seen,
            scrape_status = CASE
                WHEN ad_ids.scrape_status = 'missing' THEN 'pending'
                ELSE ad_ids.scrape_status
            END
        """,
        ((ad_id, source_url, fetched_by, now, now) for ad_id in ad_ids),
    )


@dataclass
class AdRecord:
    ad_id: str
    fetched_at: datetime
    # Basic info
    title: Optional[str]
    subtitle: Optional[str]  # Additional car description/variant
    # Pricing
    totalpris: Optional[int]  # NOK - Total price from the ad page
    omregistrering: Optional[int]  # NOK
    pris_eks_omreg: Optional[int]  # NOK
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
    neste_eu_kontroll: Optional[str]  # Store as ISO date string
    avgiftsklasse: Optional[str]
    registreringsnummer: Optional[str]
    chassisnummer: Optional[str]
    førstegangsregistrert: Optional[str]  # Store as ISO date string
    eiere: Optional[int]
    garanti: Optional[str]
    salgsform: Optional[str]
    # Raw specs for additional data
    specs: Dict[str, str]


def save_ad_detail(conn: sqlite3.Connection, record: AdRecord) -> None:
    conn.execute(
        """
        INSERT INTO ad_details (
            ad_id, fetched_at, title, subtitle, totalpris,
            omregistrering, pris_eks_omreg, årsavgift_info,
            merke, modell, modellår, karosseri, drivstoff,
            effekt_hk, kilometerstand_km, batterikapasitet_kWh,
            rekkevidde_km, girkasse, maksimal_tilhengervekt_kg,
            hjuldrift, vekt_kg, seter, dører, bagasjerom_volum_l,
            farge, fargebeskrivelse, interiørfarge, bilen_står_i,
            neste_eu_kontroll, avgiftsklasse, registreringsnummer,
            chassisnummer, førstegangsregistrert, eiere, garanti,
            salgsform, raw_spec_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ad_id) DO UPDATE SET
            fetched_at = excluded.fetched_at,
            title = excluded.title,
            subtitle = excluded.subtitle,
            totalpris = excluded.totalpris,
            omregistrering = excluded.omregistrering,
            pris_eks_omreg = excluded.pris_eks_omreg,
            årsavgift_info = excluded.årsavgift_info,
            merke = excluded.merke,
            modell = excluded.modell,
            modellår = excluded.modellår,
            karosseri = excluded.karosseri,
            drivstoff = excluded.drivstoff,
            effekt_hk = excluded.effekt_hk,
            kilometerstand_km = excluded.kilometerstand_km,
            batterikapasitet_kWh = excluded.batterikapasitet_kWh,
            rekkevidde_km = excluded.rekkevidde_km,
            girkasse = excluded.girkasse,
            maksimal_tilhengervekt_kg = excluded.maksimal_tilhengervekt_kg,
            hjuldrift = excluded.hjuldrift,
            vekt_kg = excluded.vekt_kg,
            seter = excluded.seter,
            dører = excluded.dører,
            bagasjerom_volum_l = excluded.bagasjerom_volum_l,
            farge = excluded.farge,
            fargebeskrivelse = excluded.fargebeskrivelse,
            interiørfarge = excluded.interiørfarge,
            bilen_står_i = excluded.bilen_står_i,
            neste_eu_kontroll = excluded.neste_eu_kontroll,
            avgiftsklasse = excluded.avgiftsklasse,
            registreringsnummer = excluded.registreringsnummer,
            chassisnummer = excluded.chassisnummer,
            førstegangsregistrert = excluded.førstegangsregistrert,
            eiere = excluded.eiere,
            garanti = excluded.garanti,
            salgsform = excluded.salgsform,
            raw_spec_json = excluded.raw_spec_json
        """,
        (
            record.ad_id,
            record.fetched_at.isoformat(timespec="seconds"),
            record.title,
            record.subtitle,
            record.totalpris,
            record.omregistrering,
            record.pris_eks_omreg,
            record.årsavgift_info,
            record.merke,
            record.modell,
            record.modellår,
            record.karosseri,
            record.drivstoff,
            record.effekt_hk,
            record.kilometerstand_km,
            record.batterikapasitet_kWh,
            record.rekkevidde_km,
            record.girkasse,
            record.maksimal_tilhengervekt_kg,
            record.hjuldrift,
            record.vekt_kg,
            record.seter,
            record.dører,
            record.bagasjerom_volum_l,
            record.farge,
            record.fargebeskrivelse,
            record.interiørfarge,
            record.bilen_står_i,
            record.neste_eu_kontroll,
            record.avgiftsklasse,
            record.registreringsnummer,
            record.chassisnummer,
            record.førstegangsregistrert,
            record.eiere,
            record.garanti,
            record.salgsform,
            json.dumps(record.specs, ensure_ascii=True),
        ),
    )
    conn.execute(
        """
        UPDATE ad_ids
        SET last_scraped = ?, scrape_status = 'scraped'
        WHERE ad_id = ?
        """,
        (record.fetched_at.isoformat(timespec="seconds"), record.ad_id),
    )


def mark_missing(conn: sqlite3.Connection, ad_id: str) -> None:
    conn.execute(
        """
        UPDATE ad_ids
        SET scrape_status = 'missing', last_scraped = ?
        WHERE ad_id = ?
        """,
        (datetime.utcnow().isoformat(timespec="seconds"), ad_id),
    )


def fetch_ids_for_scraping(
    conn: sqlite3.Connection,
    limit: int,
    stale_hours: Optional[int] = None,
    random_order: bool = False,
) -> List[str]:
    where_clauses = ["scrape_status IN ('pending', 'scraped')"]
    params: List[object] = []

    if stale_hours is None:
        where_clauses.append("last_scraped IS NULL")
    else:
        threshold = datetime.utcnow() - timedelta(hours=stale_hours)
        where_clauses.append("(last_scraped IS NULL OR last_scraped <= ?)")
        params.append(threshold.isoformat(timespec="seconds"))

    order_by = "ORDER BY RANDOM()" if random_order else "ORDER BY COALESCE(last_scraped, '1970-01-01T00:00:00') ASC"

    query = f"""
        SELECT ad_id
        FROM ad_ids
        WHERE {' AND '.join(where_clauses)}
        {order_by}
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [row["ad_id"] for row in rows]


def load_ads_dataframe(db_path: Path | str = DEFAULT_DB_PATH):
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pandas is required to build the analysis dataframe") from exc

    with db_session(db_path) as conn:
        initialize_schema(conn)
        ads = pd.read_sql_query("SELECT * FROM ad_details", conn)
        if ads.empty:
            return ads
        spec_dicts = ads["raw_spec_json"].apply(json.loads)
        specs_df = pd.json_normalize(spec_dicts)
        specs_df.columns = [f"spec.{c}" for c in specs_df.columns]
        return pd.concat([ads.drop(columns=["raw_spec_json"]), specs_df], axis=1)
