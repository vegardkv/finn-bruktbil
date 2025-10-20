# finnbruktbil Usage

This package provides a unified command-line tool and reusable Python helpers for scraping and analysing used-car ads from finn.no.

## Installation

```shell
pip install -e .
```

The editable install exposes a console script named `finnbruktbil` and keeps the workspace in sync with local changes.

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
   "headless": true
}
```

Example `configs/analyze.json`:

```json
{
   "streamlit_args": ["--server.port", "8502"]
}
```

Omit values to fall back to defaults. Set `db` in any document to point at a non-default SQLite file. The download and fetch jobs also honour the `headless` flag for the Selenium driver.

## Python API

Consume the same JSON configs in Python by loading the Pydantic models and invoking the helpers directly:

```python
from finnbruktbil.cli.config import (
   AnalyzeConfig,
   DownloadConfig,
   FetchIdsConfig,
   load_config,
)
from finnbruktbil.cli.fetch_ids import fetch_ids_into_db
from finnbruktbil.cli.download_data import download_ads
from finnbruktbil.cli.analyze import launch_streamlit

fetch_cfg = load_config("configs/fetch.json", FetchIdsConfig)
fetch_ids_into_db(fetch_cfg)

download_cfg = load_config("configs/download.json", DownloadConfig)
download_ads(download_cfg)

analyze_cfg = load_config("configs/analyze.json", AnalyzeConfig)
launch_streamlit(analyze_cfg)
```

Refer to the modules under `finnbruktbil/` for additional helpers and extension points.
