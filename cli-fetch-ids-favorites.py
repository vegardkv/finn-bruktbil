from finnbruktbil.cli import setup_logging
from finnbruktbil.cli.config import FetchIdsConfig, load_config
from finnbruktbil.cli.fetch_ids import fetch_ids_into_db

setup_logging()
fetch_cfg = load_config("configs/fetch-favorites.json", FetchIdsConfig)
fetch_ids_into_db(fetch_cfg)
