from finnbruktbil.cli.config import CarConstraints, load_config
from finnbruktbil.cli.summarize import print_summary, summarize_cars


config = load_config("configs/summarize.json", CarConstraints)
print_summary(summarize_cars(config))
