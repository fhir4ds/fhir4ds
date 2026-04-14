from pathlib import Path
import os

def get_package_root() -> Path:
    """Get the root directory of the cql_py package."""
    # Using os.path.dirname(__file__) is often more robust in WASM/Pyodide
    # than Path(__file__).resolve() which can fail or behave weirdly in virtual FS
    return Path(os.path.dirname(__file__))

def get_resource_path(*parts: str) -> Path:
    """Get a path to a resource within the package."""
    return get_package_root() / "resources" / Path(*parts)
