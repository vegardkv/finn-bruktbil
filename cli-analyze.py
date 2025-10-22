from finnbruktbil.cli.analyze import launch_streamlit
from finnbruktbil.cli.config import AnalyzeConfig, load_config

analyze_cfg = load_config("configs/analyze.json", AnalyzeConfig)
launch_streamlit(analyze_cfg)
