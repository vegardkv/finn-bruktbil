from finnbruktbil.cli import setup_logging
from finnbruktbil.cli.config import DownloadConfig, load_config
from finnbruktbil.cli.download_data import download_ads

setup_logging()
download_cfg = load_config("configs/download.json", DownloadConfig)
download_ads(download_cfg)
