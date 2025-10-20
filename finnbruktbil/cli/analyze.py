from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from ..db import DEFAULT_DB_PATH
from .config import AnalyzeConfig, load_config

ENV_DB_PATH = "FINNBRUKTBIL_DB_PATH"


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "analyze",
        help="Launch the Streamlit analysis app",
        description="Start the interactive Streamlit dashboard for exploring scraped data.",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Path to a JSON config file describing analysis parameters.",
    )
    parser.set_defaults(func=run)
    return parser


def launch_streamlit(config: AnalyzeConfig) -> int:
    script_path = Path(__file__).resolve().parent.parent / "analysis_app.py"
    command = [sys.executable, "-m", "streamlit", "run", str(script_path)]

    if config.streamlit_args:
        command.extend(config.streamlit_args)

    env = os.environ.copy()
    resolved_db = config.resolved_db_path
    if resolved_db is not None:
        env[ENV_DB_PATH] = str(resolved_db)
    else:
        env.setdefault(ENV_DB_PATH, str(DEFAULT_DB_PATH))

    result = subprocess.run(command, env=env, check=False)
    return result.returncode


def run(args: argparse.Namespace) -> int:
    config = load_config(args.config, AnalyzeConfig)
    return launch_streamlit(config)
