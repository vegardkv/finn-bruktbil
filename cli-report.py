from finnbruktbil.cli import setup_logging
from finnbruktbil.cli.config import ReportConfig, load_config
from finnbruktbil.cli.report import generate_report

setup_logging()
config = load_config("configs/report.json", ReportConfig)
generate_report(config)
