"""
Load fluent functions from parsed CQL libraries and register with FunctionInliner.

This module replaces the hardcoded body_sql templates in _initialize_common_functions
by dynamically loading fluent function definitions from CQL library files and registering
them with the FunctionInliner for AST-based inlining.

Key improvements:
1. Eliminates all hardcoded SQL string templates
2. Uses FunctionInliner for proper AST-based inlining
3. Works with any CQL library (not just QICoreCommon/Status)
4. Maintains backward compatibility with existing translator code
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING

from ..paths import get_resource_path

from ..parser import parse_cql
from ..translator.function_inliner import FunctionDef, FunctionInliner
from ..parser.ast_nodes import FunctionDefinition

if TYPE_CHECKING:
    from ..translator.context import SQLTranslationContext

logger = logging.getLogger(__name__)


class FluentFunctionLoader:
    """Load fluent functions from CQL libraries and register for inlining."""

    def __init__(self):
        """Initialize the loader."""
        self._loaded_libraries: Dict[str, bool] = {}
        self._library_paths = self._find_library_paths()

    @staticmethod
    def _load_standard_library_names() -> list:
        """Load standard library names from configuration file."""
        config_path = get_resource_path("terminology", "standard_libraries.json")
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
                return data.get("standard_libraries", [])
        return []

    def _find_library_paths(self) -> Dict[str, str]:
        """
        Find common CQL library paths.

        Returns:
            Dict mapping library names to file paths.
        """
        paths = {}

        from ..paths import get_package_root
        package_root = get_package_root()
        # cql-py root is parent of src/cql_py
        cql_py_root = package_root.parent
        # workspace root is parent of cql-py
        root_dir = cql_py_root.parent

        search_dirs = [
            get_resource_path("cql"),
            root_dir / "benchmarking" / "ecqm-content-qicore-2025" / "input" / "cql",
            root_dir / "benchmarking" / "dqm-content-qicore-2026" / "input" / "cql",
            root_dir / "cql" / "libraries",
        ]

        # Load standard library names from configuration
        lib_names = self._load_standard_library_names()
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            # Search recursively for library files
            for lib_name in lib_names:
                for cql_file in search_dir.rglob(f"{lib_name}.cql"):
                    if lib_name not in paths:
                        paths[lib_name] = str(cql_file)
                        logger.debug(f"Found {lib_name}: {cql_file}")

        return paths

    def load_library(
        self,
        library_name: str,
        inliner: FunctionInliner,
        context: Optional[SQLTranslationContext] = None,
    ) -> bool:
        """
        Load a CQL library and register its fluent functions with the inliner.

        Args:
            library_name: The name of the library to load (e.g., "Status", "QICoreCommon").
            inliner: The FunctionInliner to register functions with.
            context: Optional translation context for symbol resolution.

        Returns:
            True if the library was loaded successfully, False otherwise.
        """
        if library_name in self._loaded_libraries:
            return self._loaded_libraries[library_name]

        # Find the library file; for namespaced paths try the last segment too
        lib_path = self._library_paths.get(library_name)
        if not lib_path and "." in library_name:
            lib_path = self._library_paths.get(library_name.rsplit(".", 1)[-1])
        if not lib_path or not Path(lib_path).exists():
            logger.warning(f"Library file not found: {library_name}")
            self._loaded_libraries[library_name] = False
            return False

        try:
            # Parse the library
            with open(lib_path, "r") as f:
                cql_source = f.read()

            library = parse_cql(cql_source)
            logger.info(f"Loaded library: {library_name} from {lib_path}")

            # Extract and register fluent functions
            fluent_count = self._register_fluent_functions(library, inliner, library_name)
            logger.info(f"Registered {fluent_count} fluent functions from {library_name}")

            self._loaded_libraries[library_name] = True
            return True

        except Exception as e:
            logger.error(f"Error loading library {library_name}: {e}", exc_info=True)
            self._loaded_libraries[library_name] = False
            return False

    def _register_fluent_functions(
        self,
        library,
        inliner: FunctionInliner,
        library_name: str,
    ) -> int:
        """
        Extract fluent functions from a library and register with inliner.

        Args:
            library: The parsed Library AST node.
            inliner: The FunctionInliner to register with.
            library_name: The name of the library being loaded.

        Returns:
            The number of functions registered.
        """
        count = 0

        # Extract fluent functions from library statements
        for statement in library.statements:
            if isinstance(statement, FunctionDefinition) and statement.fluent:
                try:
                    # Register the function with the inliner
                    inliner.register_function_from_ast(statement, library_name)
                    count += 1
                    logger.debug(
                        f"Registered fluent function: {statement.name} "
                        f"from {library_name}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Error registering function {statement.name} from {library_name}: {e}"
                    )

        return count

    def load_default_libraries(
        self,
        inliner: FunctionInliner,
        context: Optional[SQLTranslationContext] = None,
    ) -> None:
        """
        Load the default set of fluent function libraries.

        This loads standard CQL libraries (configured in standard_libraries.json) if available.

        Args:
            inliner: The FunctionInliner to register with.
            context: Optional translation context.
        """
        for lib_name in self._load_standard_library_names():
            self.load_library(lib_name, inliner, context)
