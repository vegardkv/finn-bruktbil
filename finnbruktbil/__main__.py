from __future__ import annotations

import sys

from .cli import main


def run() -> int:
    return main()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
