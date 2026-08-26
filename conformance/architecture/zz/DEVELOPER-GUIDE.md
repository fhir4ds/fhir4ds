# Developer Guide: Extending the CQL-to-SQL Translator

## Overview

This guide explains how to extend the context-aware CQL-to-SQL translator. The translator converts Clinical Quality Language (CQL) directly to DuckDB SQL, using FHIRPath UDFs for FHIR-specific operations while leveraging native SQL for complex constructs.

## Architecture

### Core Components

1. **SQLTranslationContext** (`cql-py/src/cql_py/translator/context.py`)
   - Tracks symbol tables, scope, and translation state
   - Contains `definition_meta` for shape tracking
   - Contains `warnings` for diagnostic messages
   - Manages CTE definitions and column registry

2. **ExpressionTranslator** (`cql-py/src/cql_py/translator/expressions.py`)
   - Translates CQL expressions to SQL
   - Uses `ExprUsage` to determine translation strategy
   - Delegates to specialized handlers for each expression type
   - Handles property access through FHIRPath UDFs

3. **SQLQueryBuilder** (`cql-py/src/cql_py/translator/queries.py`)
   - Builds JOIN clauses from CTE references
   - Tracks multi-usage with `CTEReference`
   - Validates for Cartesian fanout
   - Constructs CTEs and final SELECT statements

4. **CQLToSQLTranslator** (`cql-py/src/cql_py/translator/translator.py`)
   - Main entry point for translation
   - Sorts definitions topologically
   - Infers row shapes and types
   - Orchestrates the entire translation process

### Population-First Approach

All translations follow a population-first pattern where queries return one row per patient. This is optimized for quality measure evaluation where you need to evaluate many patients simultaneously.

The generated SQL structure:
1. `patients` CTE - distinct patient IDs from resources table
2. Definition CTEs - one per CQL definition, filtered per patient
3. Final SELECT - LEFT JOINs to produce one row per patient

## Adding a New Expression Type

To add support for a new CQL expression type:

1. **Add the AST node in `cql-py/src/cql_py/parser/ast_nodes.py`**:

   ```python
   @dataclass
   class NewExpression(Expression):
       """A new CQL expression type."""
       operand: Expression
       operator: str
       # Add other fields as needed
   ```

2. **Add a handler method in `expressions.py`**:

   ```python
   def _translate_new_expression(self, expr, usage=ExprUsage.LIST):
       """Translate NewExpression to SQL."""
       if usage == ExprUsage.LIST:
           # Generate SQL that returns a collection
           operand_sql = self.translate(expr.operand, ExprUsage.LIST)
           return SQLFunctionCall(
               name="new_function",
               args=[operand_sql],
               precedence=PRECEDENCE["FUNCTION"]
           )
       elif usage == ExprUsage.SCALAR:
           # Generate SQL that returns a single value
           operand_sql = self.translate(expr.operand, ExprUsage.SCALAR)
           return SQLFunctionCall(
               name="new_function_scalar",
               args=[operand_sql],
               precedence=PRECEDENCE["FUNCTION"]
           )
       # Add other usage cases as needed
   ```

3. **Add shape inference in `translator.py`**:

   ```python
   def _infer_row_shape(self, ast_node):
       if isinstance(ast_node, NewExpression):
           # Determine what shape this expression produces
           if expr.operator in ["equals", "greater", "less"]:
               return RowShape.PATIENT_SCALAR  # Boolean result
           elif expr.operator in ["count", "sum"]:
               return RowShape.PATIENT_SCALAR  # Numeric result
           else:
               return RowShape.PATIENT_LIST   # Collection result
   ```

4. **Add tests in `cql-py/tests/unit/test_v2_expressions.py`**:

   ```python
   def test_new_expression(self):
       # Test with LIST usage
       cql = "NewExpression(Condition, 'count')"
       ast = self.parse_cql(cql)
       sql = self.translate(ast)

       # Verify the generated SQL
       expected = "SELECT new_function(fhirpath_text(resource->'condition')) FROM..."
       self.assertIn(expected, sql)

       # Test with SCALAR usage
       cql = "NewExpression(Condition, 'count') > 0"
       ast = self.parse_cql(cql)
       sql = self.translate(ast)

       # Verify boolean context
       self.assertIn("IS NOT NULL", sql)
   ```

## Adding a New FHIR Resource Type

To add support for a new FHIR resource type:

1. **Add DEFAULT_SORT_COLUMNS entry in `types.py`**:

   ```python
   DEFAULT_SORT_COLUMNS["NewResource"] = [
       "date_element DESC NULLS LAST",
       "id ASC NULLS LAST"
   ]
   ```

2. **Add precomputed columns in `SQLRetrieveCTE` if needed**:

   ```python
   class SQLRetrieveCTE:
       def _get_precomputed_columns(self, resource_type):
           if resource_type == "NewResource":
               return [
                   "fhirpath_text(resource->'dateElement') AS date_element",
                   "fhirpath_text(resource->'id') AS id_element"
               ]
           return []
   ```

3. **Add FHIRPath UDFs for the resource**:

   Ensure the FHIRPath UDFs support the new resource type. Check the implementation in `duckdb-fhirpath-py`.

4. **Add tests for the new resource type**:

   ```python
   def test_new_resource_retrieve(self):
       cql = "[NewResource]"
       ast = self.parse_cql(cql)
       sql = self.translate(ast)

       # Verify resource type filter
       self.assertIn("WHERE resource_type = 'NewResource'", sql)

       # Verify precomputed columns
       self.assertIn("date_element", sql)
       self.assertIn("id_element", sql)
   ```

## Debugging Translation Issues

### Enable Warnings

The translator collects warnings during translation that can help identify issues:

```python
from cql_py.translator.translator import CQLToSQLTranslator

translator = CQLToSQLTranslator()
sql = translator.translate_library(ast)
if translator._context.warnings.has_warnings():
    print("Translation Warnings:")
    print(translator._context.warnings.report())
```

### Check Definition Metadata

Inspect the metadata for each definition to understand shape and type information:

```python
for name, meta in translator._context.definition_meta.items():
    print(f"{name}:")
    print(f"  Shape: {meta.shape}")
    print(f"  Type: {meta.cql_type}")
    print(f"  Dependencies: {meta.dependencies}")
```

### Check CTE References

Examine CTE references to understand how definitions are joined:

```python
for key, ref in translator.query_builder.cte_references.items():
    print(f"{key}:")
    print(f"  Usages: {ref.usages}")
    print(f"  Shape: {ref.shape}")
    print(f"  Multi-usage: {ref.multi_usage}")
```

### Debug Expression Translation

Set breakpoints or add logging to expression handlers:

```python
def _translate_binary_expression(self, expr, usage=ExprUsage.LIST):
    print(f"Translating binary expression: {expr.operator} with usage {usage}")
    left_sql = self.translate(expr.left, self._determine_usage(expr.left, usage))
    right_sql = self.translate(expr.right, self._determine_usage(expr.right, usage))
    # ... rest of implementation
```

### Use Test Mode

Enable test mode to see intermediate representations:

```python
translator = CQLToSQLTranslator()
translator.enable_test_mode = True
sql = translator.translate_library(ast)
print("CTEs generated:")
for cte_name, cte_def in translator.ctes.items():
    print(f"\n{cte_name}:")
    print(cte_def.sql)
```

## Testing

### Unit Tests

Run unit tests to verify individual components:

```bash
# Test expressions
pytest cql-py/tests/unit/test_v2_expressions.py -v

# Test queries
pytest cql-py/tests/unit/test_v2_queries.py -v

# Test translation
pytest cql-py/tests/unit/test_translator.py -v

# Test all unit tests
pytest cql-py/tests/unit/ -v
```

### Integration Tests

Run integration tests to verify end-to-end functionality:

```bash
# Test with CMS165 measure
pytest cql-py/tests/integration/test_cms165_v2.py -v

# Test with other measures
pytest cql-py/tests/integration/ -v

# Test all integration tests
pytest cql-py/tests/integration/ -v
```

### Structure Tests

Verify SQL structure and optimization:

```bash
# Test SQL optimization
pytest cql-py/tests/unit/test_sql_optimization.py -v

# Test CTE generation
pytest cql-py/tests/unit/test_sql_retrieve_cte.py -v

# Test join conversion
pytest cql-py/tests/unit/test_join_conversion.py -v

# Test all structure tests
pytest cql-py/tests/unit/test_sql_structure.py -v
```

### Test Data

Use the provided test fixtures:

```python
from cql_py.tests.fixtures.test_data import (
    sample_patient,
    sample_condition,
    sample_observation
)

# Create test database with sample data
def create_test_db():
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE resources (id VARCHAR, resource_type VARCHAR, resource JSON, patient_ref VARCHAR)")

    # Insert sample data
    conn.execute("INSERT INTO VALUES (?, ?, ?, ?)",
                [sample_patient['id'], 'Patient', sample_patient, sample_patient['id']])
    # ... insert other resources

    return conn
```

## Performance Optimization

### Query Optimization

The translator includes several optimizations:

1. **CTE Extraction**: Complex expressions are extracted into CTEs
2. **Join Conversion**: List-valued expressions are converted to JOINs
3. **Column Precomputation**: FHIRPath expressions are precomputed as columns
4. **Filter Pushdown**: WHERE clauses are applied early in CTEs

### Monitoring Performance

Use query profiling to identify bottlenecks:

```python
import duckdb

conn = duckdb.connect()
conn.execute("PRAGMA enable_profiling")

# Execute translated query
conn.execute(sql)

# Get profile results
profile = conn.execute("PRAGMA profile").fetchall()
print(profile)
```

## Contributing

When extending the translator:

1. Follow the existing code style and patterns
2. Add comprehensive tests for new features
3. Update documentation with new features
4. Test with real-world measures (CMS165, QICore)
5. Consider performance implications of changes

## Troubleshooting Common Issues

### "Forward reference not found"

This occurs when a definition references another definition that hasn't been processed yet. Ensure definitions are properly ordered or add forward reference handling.

### "Cartesian fanout detected"

The translator prevents excessive JOIN operations that could cause performance issues. Consider breaking complex queries into smaller definitions.

### "Shape mismatch"

When expressions produce different shapes than expected, check the shape inference logic and ensure proper handling of different usage contexts.

### "Missing FHIRPath UDF"

Ensure the required FHIRPath UDFs are installed and available in the DuckDB instance.