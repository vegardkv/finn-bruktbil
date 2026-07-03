# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`finnbruktbil` is a personal tool for scraping and analysing used-car ads from finn.no. It has three modes that form a pipeline: **fetch ad ids → download ad details → analyze**. IDs and scraped details are stored in a Supabase (Postgres) cloud database; analysis is an interactive Streamlit dashboard.

## Commands

`uv` is the primary tool for this project. Setup (installs the package and exposes the `finnbruktbil` console script):
```shell
uv sync
```

The typical workflow runs the three pipeline stages with `uv run`. The four root-level `cli-*.py` wrapper scripts are the canonical entry points — they call the stage functions with hardcoded config paths, and **keeping them working is the priority**:
```shell
uv run cli-fetch-ids.py            # collect ad ids from a FINN search (configs/fetch.json)
uv run cli-fetch-ids-favorites.py  # collect ad ids from a saved favorites HTML file (configs/fetch-favorites.json)
uv run cli-download-data.py        # scrape ad details for stored ids (configs/download.json)
uv run cli-analyze.py              # launch the Streamlit dashboard (configs/analyze.json)
uv run cli-summarize.py            # summarize cars matching soft/hard constraints (configs/summarize.json)
```

Equivalent CLI subcommands (same functions, explicit config path argument):
```shell
uv run finnbruktbil fetch-ids configs/fetch.json
uv run finnbruktbil download configs/download.json
uv run finnbruktbil analyze configs/analyze.json
uv run finnbruktbil summarize configs/summarize.json
```

Run the Streamlit app directly (bypassing the CLI):
```shell
uv run streamlit run finnbruktbil/analysis_app.py
```

There is no test runner configured.

## Architecture

The package lives under `finnbruktbil/`. The CLI (`finnbruktbil/cli/__init__.py`) wires three subcommands via argparse; each subcommand module exposes both an `add_parser` (CLI) and a plain function (Python API), so every stage is callable programmatically — see USAGE.md.

**Data flow / key modules:**
- `cli/config.py` — Pydantic models (`FetchIdsConfig`, `DownloadConfig`, `AnalyzeConfig`, `CarConstraints`) and `load_config`. All runtime parameters come from JSON configs, not CLI flags.
- `cli/summarize.py` — filters `load_ads_dataframe()` to a single `merke`/`modell`, drops cars failing any **hard** constraint, scores survivors by number of **soft** constraints met, and prints all-time feasible / currently-available (`solgt is False`) counts plus a score-sorted list. Each constraint has an explicit `_eval_*` evaluator registered in `CONSTRAINT_EVALUATORS`; missing data fails the constraint. Add a constraint = new `CarConstraints` field + `_eval_*` fn + one registry line.
- `browser.py` — Selenium Chrome driver factory (`create_driver`) and helpers (`wait_for_elements`, `polite_delay`). Tries a system `chromedriver` first, then falls back to `webdriver-manager`, and uses a system `chromium` binary when present (important for the devcontainer / CI).
- `cli/fetch_ids.py` — two id-collection modes: scrape a FINN search URL page-by-page (`base_url`), or regex-extract 9-digit ids from a locally saved favorites HTML file (`favorites_file`). Persists via `upsert_ad_ids`.
- `scraper.py` — `scrape_ad` loads an ad page and extracts the `key-info-section` `<dl>` pairs, mapping Norwegian labels to `AdRecord` fields via `FIELD_MAPPING`. Returns `None` when the ad is gone (downloader then marks it `missing`). Logs missing/redundant keys to help keep `FIELD_MAPPING` in sync with FINN's markup.
- `aux_data_parser.py` — optional OpenAI (`gpt-4o-mini`) extraction from free-text ad descriptions, returning structured `tire_sets`, `trim_level`, and `imported`. Only runs when `parse_aux_data: true`. The `imported` prompt is deliberately conservative (explicit evidence only, else `None`).
- `vegvesen.py` — looks up import status via Statens Vegvesen's open API, either by chassis number/VIN (`lookup_import_status_by_vin`, `understellsnummer`) or by registration number (`lookup_import_status`, `kjennemerke`); both share the private `_lookup` request/retry loop and identical response shape. This is the **primary** source for `imported`/`import_country`. The scraper tries the VIN first (almost always present in the ad), then the reg number, then the OpenAI description signal only as a fallback when the API lookups are inconclusive or no key is set. Requires `SVV_API_KEY`.
- `db.py` — all Supabase access. Two tables: `ad_ids` (id queue with `scrape_status`: pending/scraped/missing) and `ad_details` (one row per scraped ad). `AdRecord` is the in-memory dataclass; `load_ads_dataframe` reads everything back into a pandas DataFrame for analysis.
- `analysis_app.py` — the Streamlit dashboard: sidebar filters, plotly charts, and an OLS regression (`Price = c₀ + c₁·mileage + c₂·age`) producing the interpretable cost-per-km / cost-per-year coefficients and a 0–1 "usedness" score (see PRICE_MODEL.md).

**Norwegian ↔ ASCII column naming:** `AdRecord` and analysis code use Norwegian field names with diacritics (`modellår`, `dører`, `interiørfarge`, `batterikapasitet_kWh`). Supabase columns use ASCII equivalents (`modellaar`, `doerer`, `aarsavgift_info`, etc.). `db.save_ad_detail` maps Norwegian→ASCII on write and `db.load_ads_dataframe` maps ASCII→Norwegian on read. Keep both sides of this mapping in sync when adding fields. `raw_spec_json` (JSONB) stores all scraped key-info; on read it is flattened into `spec.*` columns.

## Database schema

Tables are **not** created by the code — `db.initialize_schema` is a no-op. The authoritative `CREATE TABLE` SQL lives in the `initialize_schema` docstring in `db.py` (also in USAGE.md) and must be run manually in the Supabase SQL Editor. When adding a column to `AdRecord`, also add it to: the schema SQL, `save_ad_detail`, and (if Norwegian-named) the rename map in `load_ads_dataframe`.

## Configuration / secrets

Credentials are read from environment variables, with `.env` auto-loaded via `python-dotenv` (works in both local dev and Codespaces/Docker). See `.env.example`:
- `SUPABASE_URL`, `SUPABASE_KEY` — required for all DB operations.
- `OPENAI_API_KEY` — required only when `parse_aux_data: true`; incurs API cost.
- `SVV_API_KEY` — optional; enables Vegvesen import-status lookups.

## Environment notes

- Primary development is local on Windows with `uv` managing the `.venv`; Selenium uses `webdriver-manager` to obtain a chromedriver automatically.
- A devcontainer (`.devcontainer/`) is intended to install `chromium`/`chromium-driver` via apt and a `uv`-managed `.venv` (Python 3.12), but it is **not fully working yet** — don't assume it runs cleanly.
- The scraper is intentionally polite (randomised `polite_delay` between requests, realistic user-agent). Preserve this when modifying scraping loops.
