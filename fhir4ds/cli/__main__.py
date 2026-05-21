"""Allow `python -m fhir4ds.cli`."""

from fhir4ds.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
