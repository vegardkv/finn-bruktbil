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
            price_nok INTEGER,
            location TEXT,
            brand TEXT,
            model TEXT,
            model_year INTEGER,
            mileage_km INTEGER,
            raw_spec_json TEXT NOT NULL,
            FOREIGN KEY (ad_id) REFERENCES ad_ids (ad_id) ON DELETE CASCADE
        );
        """
    )

    _ensure_column(conn, "ad_ids", "fetched_by", "TEXT NOT NULL DEFAULT 'unknown'")


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
    title: Optional[str]
    price_nok: Optional[int]
    location: Optional[str]
    brand: Optional[str]
    model: Optional[str]
    model_year: Optional[int]
    mileage_km: Optional[int]
    specs: Dict[str, str]


def save_ad_detail(conn: sqlite3.Connection, record: AdRecord) -> None:
    conn.execute(
        """
        INSERT INTO ad_details (
            ad_id, fetched_at, title, price_nok, location,
            brand, model, model_year, mileage_km, raw_spec_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ad_id) DO UPDATE SET
            fetched_at = excluded.fetched_at,
            title = excluded.title,
            price_nok = excluded.price_nok,
            location = excluded.location,
            brand = excluded.brand,
            model = excluded.model,
            model_year = excluded.model_year,
            mileage_km = excluded.mileage_km,
            raw_spec_json = excluded.raw_spec_json
        """,
        (
            record.ad_id,
            record.fetched_at.isoformat(timespec="seconds"),
            record.title,
            record.price_nok,
            record.location,
            record.brand,
            record.model,
            record.model_year,
            record.mileage_km,
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
