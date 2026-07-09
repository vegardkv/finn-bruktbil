"""Command-line interface for the ``finnbruktbil`` tool."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable, Sequence

from . import analyze, download_data, fetch_ids, report, summarize


def setup_logging(level: int = logging.INFO) -> None:
    """Configure a console handler for the pipeline's ``logging`` diagnostics.

    Called by the CLI and the root-level ``cli-*.py`` wrappers; a no-op if the
    root logger already has handlers.
    """
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finnbruktbil",
        description="Tools for fetching, downloading, and analysing FINN used-car ads.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_ids.add_parser(subparsers)
    download_data.add_parser(subparsers)
    analyze.add_parser(subparsers)
    summarize.add_parser(subparsers)
    report.add_parser(subparsers)

    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 0

    result = handler(args)
    if isinstance(result, int):
        return result
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry-point compatible with ``python -m finnbruktbil`` and console scripts."""

    exit_code = run_cli(argv)
    return exit_code


def dispatch(argv: Iterable[str]) -> int:
    """Convenience helper mirroring :func:`main` for external callers."""

    return main(list(argv))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
