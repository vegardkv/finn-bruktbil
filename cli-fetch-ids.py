from finnbruktbil.cli.config import FetchIdsConfig, load_config
from finnbruktbil.cli.fetch_ids import fetch_ids_into_db


fetch_cfg = load_config("configs/fetch.json", FetchIdsConfig)
fetch_ids_into_db(fetch_cfg)