"""Command-line interface for the ``finnbruktbil`` tool."""

from __future__ import annotations

import argparse
import sys
from typing import Iterable, Optional, Sequence

from . import analyze, download_data, fetch_ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finnbruktbil",
        description="Tools for fetching, downloading, and analysing FINN used-car ads.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_ids.add_parser(subparsers)
    download_data.add_parser(subparsers)
    analyze.add_parser(subparsers)

    return parser


def run_cli(argv: Optional[Sequence[str]] = None) -> int:
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry-point compatible with ``python -m finnbruktbil`` and console scripts."""

    exit_code = run_cli(argv)
    return exit_code


def dispatch(argv: Iterable[str]) -> int:
    """Convenience helper mirroring :func:`main` for external callers."""

    return main(list(argv))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
