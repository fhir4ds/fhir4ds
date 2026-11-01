"""``python -m fhir4ds.serve`` — start the surface without the whole CLI.

The installed ``fhir4ds`` console script builds every subcommand at import time,
including ``dqm``, which imports pandas (the optional ``[measures]`` extra). A
slim deployment that installs only ``[serve]`` therefore cannot start the
surface through that script::

    $ fhir4ds serve --port 7860
    ModuleNotFoundError: No module named 'pandas'

This module runs exactly the ``serve`` command — same parser, same ``run()`` as
``fhir4ds serve`` — without importing the rest of the CLI. The container image
uses it; so can any ``[serve]``-only install.
"""

from __future__ import annotations

import argparse
import sys

from fhir4ds.cli.serve import configure_parser, run


def main(argv: list[str] | None = None) -> int:
    """Parse ``serve`` arguments and run the server. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m fhir4ds.serve",
        description="FHIR R4 / SQL-on-FHIR HTTP surface (see `fhir4ds serve --help`).",
    )
    configure_parser(parser)
    return run(parser.parse_args(argv))


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
