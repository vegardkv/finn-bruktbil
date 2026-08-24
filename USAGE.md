# finnbruktbil Usage

This package provides a unified command-line tool and reusable Python helpers for scraping and analysing used-car ads from finn.no.

## Installation

```shell
pip install -e .
```

The editable install exposes a console script named `finnbruktbil` and keeps the workspace in sync with local changes.

## Supabase Setup

This project uses [Supabase](https://supabase.com) as a cloud database. Follow these steps to set it up:

### 1. Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) and create a free account
2. Create a new project (takes ~2 minutes to provision)
3. Note your project URL and API keys from **Project Settings → API**

### 2. Create Database Tables

Open the **SQL Editor** in your Supabase dashboard and run:

```sql
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
    raw_description TEXT
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_ad_ids_scrape_status ON ad_ids(scrape_status);
CREATE INDEX IF NOT EXISTS idx_ad_ids_last_scraped ON ad_ids(last_scraped);
```

### 3. Configure Environment Variables

Copy the example environment file and add your credentials:

```shell
cp .env.example .env
```

Edit `.env` with your Supabase credentials:

```dotenv
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-or-service-role-key
```

You can find these in your Supabase dashboard under **Project Settings → API**.

## Command-Line Workflow

1. Fetch ad identifiers for a pre-filtered FINN search page:
   ```shell
   finnbruktbil fetch-ids configs/fetch.json
   ```

2. Download ad details for stored identifiers:
   ```shell
   finnbruktbil download configs/download.json
   ```

3. Launch the Streamlit dashboard to explore results:
   ```shell
   finnbruktbil analyze configs/analyze.json
   ```

4. Generate a static HTML report (for GitHub Pages) to `site/index.html`:
   ```shell
   finnbruktbil report configs/report.json
   ```

Each sub-command consumes a JSON configuration file that is validated with Pydantic. Example documents:

Example `configs/fetch.json`:

```json
{
   "base_url": "https://www.finn.no/mobility/search/car?model=1.777.2000638&registration_class=1",
   "limit": 150,
   "max_pages": 10,
   "fetched_by": "daily-job",
   "headless": true
}
```

Example `configs/download.json`:

```json
{
   "limit": 50,
   "stale_hours": 24,
   "random_order": false,
   "headless": true,
   "parse_aux_data": false,
   "skip_sold": true
}
```

**Skipping sold ads**: with `"skip_sold": true` the downloader leaves out every ad a previous scrape
found sold or inactive/removed (the `solgt` flag covers both), so the `limit` is spent on ads that
can still change and no request is made for the rest. On a queue that is mostly sold this cuts the
number of page loads dramatically. The default is `false`, which re-visits everything as before; with
the flag on, flip it back to `false` for a run when you deliberately want to refresh the sold ads.
Ads that have never been scraped are of course never skipped.

**Auxiliary Data Parsing**: Set `"parse_aux_data": true` to enable parsing of additional information from ad descriptions using OpenAI's API. This extracts:
- **Tire sets**: Whether the car comes with one or two sets of tires (including winter tires)
- **Trim level**: The equipment/trim level (e.g., "GT-Line", "Premium", "Elegance")

To use this feature:
1. Install the required dependencies: `pip install -e .` (includes `openai` and `python-dotenv`)
2. Set your OpenAI API key either by:
   - Creating a `.env` file: `cp .env.example .env` and add your key, **OR**
   - Setting an environment variable: `export OPENAI_API_KEY=your-key-here`
3. Set `"parse_aux_data": true` in your download config

The implementation works seamlessly with both `.env` files (local development) and environment variables (GitHub Codespaces, Docker, CI/CD).

Note: This feature requires an OpenAI API key and will incur API costs.

To try the parser on its own (makes one billable API call):

```python
from finnbruktbil.aux_data_parser import parse_aux_data_with_openai

description = """
Kia EV9 GT-Line AWD 7 seter med vinterhjul og hengerfeste!
Ekstra sett med vinterhjul på felg. Kun 21.500 km kjørt!
"""

aux_data = parse_aux_data_with_openai(description)
print(f"Tire sets: {aux_data.tire_sets.value}")
print(f"Trim level: {aux_data.trim_level}")
```

Example `configs/analyze.json`:

```json
{
   "streamlit_args": ["--server.port", "8502"]
}
```

Example `configs/report.json` (embeds the same constraint block as `configs/summarize.json`):

```json
{
   "title": "Kia EV9 — FINN bruktbil report",
   "output_dir": "site",
   "constraints": {
      "merke": "Kia",
      "modell": "EV9",
      "imported": [false, "hard"],
      "number_of_seats": [7, "hard"],
      "max_price": [800000, "soft"],
      "trim_level": ["GT-Line", "soft"],
      "max_mileage": [30000, "soft"],
      "color": ["grey", "soft"]
   }
}
```

Omit values to fall back to defaults. The download and fetch jobs also honour the `headless` flag for the Selenium driver.

## Report / GitHub Pages

`finnbruktbil report configs/report.json` renders the summarize tables plus three interactive
Plotly charts (price vs. usedness / mileage / registration date, colored by availability) into a
single self-contained `site/index.html`. The page loads Plotly from a CDN, so viewing it needs an
internet connection.

The report is published to GitHub Pages by `.github/workflows/report.yml` on a daily schedule (and
on-demand via **Actions → Publish report → Run workflow**). The workflow only reads the database —
no scraping runs in CI. One-time repository setup:

1. **Settings → Pages → Source: GitHub Actions**.
2. **Settings → Secrets and variables → Actions** — add `SUPABASE_URL` and `SUPABASE_KEY` (use a
   read-capable key, not the service-role key).

Note the resulting page is public, so anything on it (prices, ad links, your constraints) is
world-readable at the Pages URL.

## Python API

Consume the same JSON configs in Python by loading the Pydantic models and invoking the helpers directly:

```python
from finnbruktbil.cli.config import (
   AnalyzeConfig,
   DownloadConfig,
   FetchIdsConfig,
   ReportConfig,
   load_config,
)
from finnbruktbil.cli.fetch_ids import fetch_ids_into_db
from finnbruktbil.cli.download_data import download_ads
from finnbruktbil.cli.analyze import launch_streamlit
from finnbruktbil.cli.report import generate_report

fetch_cfg = load_config("configs/fetch.json", FetchIdsConfig)
fetch_ids_into_db(fetch_cfg)

download_cfg = load_config("configs/download.json", DownloadConfig)
download_ads(download_cfg)

analyze_cfg = load_config("configs/analyze.json", AnalyzeConfig)
launch_streamlit(analyze_cfg)

report_cfg = load_config("configs/report.json", ReportConfig)
generate_report(report_cfg)  # writes site/index.html
```

Refer to the modules under `finnbruktbil/` for additional helpers and extension points.
