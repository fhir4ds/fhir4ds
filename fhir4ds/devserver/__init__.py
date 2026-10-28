"""fhir4ds.devserver — the `fhir4ds dev` cleanroom dev server."""

from .config import DevConfigError, DevServerConfig, load_config

__all__ = [
    "DevConfigError",
    "DevServerConfig",
    "load_config",
    "run_dev_server",
]


def __getattr__(name: str):  # lazy: avoid importing http machinery at pkg import
    if name == "run_dev_server":
        from .api import run_dev_server

        return run_dev_server
    raise AttributeError(name)
