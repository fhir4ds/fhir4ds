"""CQL specification-version policy for version-dependent operator semantics.

CQL 2.0 changed the step used by ``successor of`` / ``predecessor of`` for
Decimal and Quantity values. The engine therefore has to know WHICH CQL
version a library is being translated for.

CQL source text carries no specification-version marker:

* ``library X version '1.0.0'`` is the library's OWN semantic version (the
  cql-tests harness emits ``library Conformance version '1.0'``, which is not
  a claim about the CQL release).
* ``using FHIR version '4.0.1'`` is the model version.
* The cql-tests-runner's ``Build.CqlVersion`` configuration value only
  selects which test cases apply (``versionSkipReason`` in
  ``src/shared/run-test-core.ts``); it is never sent to the engine.

So the version is translator/server configuration (``cql_version`` on
:class:`~fhir4ds.cql.translator.translator.CQLToSQLTranslator`,
:class:`~fhir4ds.cql.fhir_server.types.CQLServerConfig`, and the public
``translate_cql``/``translate_library`` helpers), defaulting to
:data:`DEFAULT_CQL_VERSION`.

Ground truth (fetched 2026-11-24):

* CQL 1.5.3, §6.14 Predecessor / §6.18 Successor
  (https://cql.hl7.org/2019May/09-b-cqlreference.html):

  - "For Decimal, successor is equivalent to adding the minimum precision
    value for the Decimal type, or 10^-08."
  - "For Quantity values, the successor is equivalent to adding 1 if the
    quantity is an integer, and the minimum precision value for the Decimal
    type if the quantity is a decimal. The units are unchanged."
  - Examples: ``successor of 1.0 // 1.00000001``,
    ``predecessor of 1.0 // 0.99999999``.

* CQL 2.0.0 (§Successor / §Predecessor,
  https://cql.hl7.org/09-b-cqlreference.html#successor):

  - "For Decimal, successor is equivalent to adding 1 * the precision of the
    argument."
  - "For Quantity values, the successor is equivalent to adding 1 * the
    precision of the quantity value."
  - Examples: ``successor of 1.0 // 1.1``,
    ``successor of 1.00000000 // 1.00000001``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Tuple

__all__ = [
    "DEFAULT_CQL_VERSION",
    "parse_cql_version",
    "uses_minimum_precision_ordinals",
    "validate_cql_version",
]


#: CQL version assumed when none is configured.
#:
#: 2.0 (the current release) is the default so that existing translations do
#: not move: DQM measure results and the vendored cql-tests snapshot's
#: ``version="2.0"`` successor/predecessor fixtures are gated on the 2.0
#: semantics, and the 2029/2037 conformance baseline was established with
#: them. CQL 1.5.3 semantics are opt-in per translation.
DEFAULT_CQL_VERSION = "2.0"

#: First CQL version whose ``successor``/``predecessor`` step is the authored
#: precision instead of the fixed minimum Decimal precision (10^-8).
_FIRST_AUTHORED_PRECISION_VERSION = (2, 0)


def parse_cql_version(value: str) -> Tuple[int, ...]:
    """Parse a dotted CQL version (``"1.5.3"``, ``"2.0"``) into a tuple.

    Args:
        value: Dotted numeric version. Trailing components may be omitted.

    Returns:
        Numeric components, e.g. ``(1, 5, 3)``.

    Raises:
        ValueError: If *value* is not a dotted numeric version.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"cql_version must be a dotted numeric version, got {value!r}")
    text = value.strip()
    parts = text.split(".")
    if not all(part.isdigit() for part in parts):
        raise ValueError(f"cql_version must be a dotted numeric version, got {value!r}")
    return tuple(int(part) for part in parts)


def validate_cql_version(value: str) -> str:
    """Validate *value* as a CQL version and return its stripped text.

    Args:
        value: Dotted numeric version, e.g. ``"1.5.3"``.

    Returns:
        The stripped version text.

    Raises:
        ValueError: If *value* is not a dotted numeric version.
    """
    parse_cql_version(value)
    return value.strip()


@lru_cache(maxsize=32)
def uses_minimum_precision_ordinals(value: str) -> bool:
    """Return True when *value* uses the CQL <= 1.5.3 ordinal step rule.

    For those versions ``successor of``/``predecessor of`` use the minimum
    Decimal precision (10^-8) for Decimal and decimal-authored Quantity values,
    regardless of the authored precision. From CQL 2.0 the step follows the
    authored precision instead.

    Args:
        value: Dotted CQL version, e.g. ``"1.5.3"`` or ``"2.0"``.

    Returns:
        True for versions below 2.0, False otherwise.

    Raises:
        ValueError: If *value* is not a dotted numeric version.
    """
    parsed = parse_cql_version(value)
    width = max(len(parsed), len(_FIRST_AUTHORED_PRECISION_VERSION))
    padded = parsed + (0,) * (width - len(parsed))
    reference = _FIRST_AUTHORED_PRECISION_VERSION + (0,) * (width - len(_FIRST_AUTHORED_PRECISION_VERSION))
    return padded < reference
