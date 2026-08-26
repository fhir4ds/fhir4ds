# Running CQL Measures

This guide explains how to run CQL measures using the duckdb-fhirpath project.

## Quick Start

```python
import duckdb
from duckdb_fhirpath_py.extension import register_fhirpath
from duckdb_cql_py.extension import register

# 1. Create DuckDB connection
con = duckdb.connect(':memory:')

# 2. Register FHIRPath UDFs (fhirpath_text, fhirpath_date, etc.)
register_fhirpath(con)

# 3. Register CQL UDFs (in_valueset, intervalOverlaps, AgeInYearsAt, etc.)
register(con, include_fhirpath=False)  # Already registered above

# 4. Set measurement period (required for most measures)
from duckdb_cql_py.udf.variable import setvariable
setvariable('measurement_period', '[2024-01-01, 2024-12-31]')

# 5. Load FHIR data into resources table
# ... (see Data Loading section)

# 6. Generate and execute SQL
from cql_py import evaluate_measure
result = evaluate_measure(
    library_path="./cql-measures/CMS165/CMS165FHIRControllingHighBP.cql",
    conn=con,
    output_columns={
        "initial_population": "Initial Population",
        "denominator": "Denominator",
        "numerator": "Numerator",
    },
)
print(result.df())
```

## UDF Registration

### Two Packages Required

The project has two UDF packages that must be registered:

| Package | Purpose | Key Functions |
|---------|---------|---------------|
| `duckdb-fhirpath-py` | FHIRPath navigation | `fhirpath_text`, `fhirpath_date`, `fhirpath_quantity` |
| `duckdb-cql-py` | CQL operations | `in_valueset`, `AgeInYearsAt`, `intervalOverlaps`, `parse_quantity` |

### Registration Order

```python
from duckdb_fhirpath_py.extension import register_fhirpath
from duckdb_cql_py.extension import register

# Register FHIRPath first
register_fhirpath(con)

# Then register CQL UDFs (skip FHIRPath since already registered)
register(con, include_fhirpath=False)
```

### All CQL UDFs

The `register(con)` function registers these UDFs:

**Interval Operations** (`duckdb_cql_py.udf.interval`):
- `intervalStart(interval)`, `intervalEnd(interval)`
- `intervalFromBounds(low, high, lowClosed, highClosed)`
- `intervalOverlaps(i1, i2)`, `intervalContains(i, point)`
- `intervalBefore(i1, i2)`, `intervalAfter(i1, i2)`

**Quantity Operations** (`duckdb_cql_py.udf.quantity`):
- `parse_quantity(json)` / `parseQuantity(json)`
- `quantityValue(json)`, `quantityUnit(json)`
- `quantityCompare(q1, q2, op)`

**Age Calculations** (`duckdb_cql_py.udf.age`):
- `AgeInYears(resource, date)`
- `AgeInMonths(resource, date)`, `AgeInDays(resource, date)`

**List Operations** (`duckdb_cql_py.udf.list`):
- `SingletonFrom(list)`, `ElementAt(list, index)`
- `jsonConcat(left, right)`

**Variable/Parameter Access** (`duckdb_cql_py.udf.variable`):
- `getvariable(name)`, `setvariable(name, value)`

**Valueset Membership** (`duckdb_cql_py.udf.valueset`):
- `in_valueset(resource, path, valueset_url)`

## Data Loading

### Using FHIRDataLoader

```python
from cql_py import FHIRDataLoader

loader = FHIRDataLoader(con, table_name="resources", create_table=True)

# Load from NDJSON
loader.load_ndjson("./fhir-data/patients.ndjson")

# Load from directory (JSON, NDJSON, bundles)
loader.load_directory("./fhir-data/", recursive=True)
```

### Manual Table Creation

```python
import json

con.execute('''
    CREATE TABLE resources (
        resourceType VARCHAR,
        patient_ref VARCHAR,
        resource JSON
    )
''')

# Insert FHIR resources
for resource in fhir_resources:
    con.execute(
        'INSERT INTO resources VALUES (?, ?, ?)',
        [resource['resourceType'], resource['subject']['reference'], json.dumps(resource)]
    )
```

## Setting Parameters

### Measurement Period

Most CQL measures require a measurement period:

```python
from duckdb_cql_py.udf.variable import setvariable

# Set as interval string
setvariable('measurement_period', '[2024-01-01, 2024-12-31]')
```

### Via evaluate_measure()

```python
from datetime import datetime

result = evaluate_measure(
    library_path="./measure.cql",
    conn=con,
    parameters={
        "Measurement Period": (datetime(2024, 1, 1), datetime(2024, 12, 31))
    },
)
```

## Valueset Loading

The `in_valueset` UDF requires a valueset cache:

```python
from duckdb_cql_py.udf.valueset import createValuesetMembershipUdf

# Load valueset codes (typically from FHIR ValueSet resources)
valueset_cache = {
    "http://cts.nlm.nih.gov/fhir/ValueSet/Diabetes": {"44054006", "73211009"},
    # ... more valuesets
}

# Create and register UDF with cache
in_valueset_udf = createValuesetMembershipUdf(valueset_cache)
con.create_function("in_valueset", in_valueset_udf)
```

For development/testing, the default `register(con)` creates an empty cache that always returns `True`.

## Complete Example

```python
import duckdb
import json
from pathlib import Path

# Import UDF registration
from duckdb_fhirpath_py.extension import register_fhirpath
from duckdb_cql_py.extension import register
from duckdb_cql_py.udf.variable import setvariable

# Import CQL evaluation
from cql_py import evaluate_measure

# 1. Setup connection and UDFs
con = duckdb.connect(':memory:')
register_fhirpath(con)
register(con, include_fhirpath=False)

# 2. Set measurement period
setvariable('measurement_period', '[2024-01-01, 2024-12-31]')

# 3. Load test data
con.execute('''
    CREATE TABLE resources (
        resourceType VARCHAR,
        patient_ref VARCHAR,
        resource JSON
    )
''')

# Load from NDJSON file
with open('./test-data/patients.ndjson', 'r') as f:
    for line in f:
        resource = json.loads(line)
        patient_ref = resource.get('id')
        if resource['resourceType'] == 'Patient':
            patient_ref = resource['id']
        elif 'subject' in resource:
            patient_ref = resource['subject']['reference'].replace('Patient/', '')
        con.execute(
            'INSERT INTO resources VALUES (?, ?, ?)',
            [resource['resourceType'], patient_ref, json.dumps(resource)]
        )

# 4. Run CQL measure
result = evaluate_measure(
    library_path="./cql-measures/CMS165/CMS165FHIRControllingHighBP.cql",
    conn=con,
    include_paths=["./cql-measures/CMS165"],  # For included libraries
    output_columns={
        "initial_population": "Initial Population",
        "denominator": "Denominator",
        "numerator": "Numerator",
    },
    verbose=True,  # Print generated SQL
)

# 5. Get results
df = result.df()
print(f"Total patients: {len(df)}")
print(f"In initial population: {df['initial_population'].sum()}")
```

## Troubleshooting

### "Scalar Function with name X does not exist"

You need to register the UDFs:
```python
from duckdb_fhirpath_py.extension import register_fhirpath
from duckdb_cql_py.extension import register
register_fhirpath(con)
register(con, include_fhirpath=False)
```

### "Table with name resource does not exist"

This is a SQL generation bug where a column reference (`jN.resource`) is used in a FROM clause. This is a known issue in complex nested queries.

### Empty Results

1. Check that resources table has data: `con.execute("SELECT COUNT(*) FROM resources").fetchone()`
2. Verify patient_ref is populated for all resources
3. Check measurement period is set correctly

### Valueset Issues

If `in_valueset` always returns False, you need to load actual valueset codes:
```python
from duckdb_cql_py.udf.valueset import createValuesetMembershipUdf
# Create cache with actual codes, then re-register
```

## Package Dependencies

```
duckdb
duckdb-fhirpath-py  # FHIRPath UDFs
duckdb-cql-py       # CQL UDFs
cql-py              # CQL parser and translator
pyarrow             # For vectorized UDFs
pint                # For quantity unit conversion
orjson              # Fast JSON parsing
```

## See Also

- [FHIRPath UDF Reference](../duckdb-fhirpath-py/README.md)
- [CQL UDF Reference](../duckdb-cql-py/README.md)
- [CQL Translator Documentation](./PLAN-FULL-AST-MIGRATION.md)
