from finnbruktbil.cli import setup_logging
from finnbruktbil.cli.config import CarConstraints, load_config
from finnbruktbil.cli.summarize import print_summary, summarize_cars

setup_logging()
config = load_config("configs/summarize-ioniq9.json", CarConstraints)
print_summary(summarize_cars(config))
