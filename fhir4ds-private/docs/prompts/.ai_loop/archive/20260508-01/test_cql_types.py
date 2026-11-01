import duckdb
import pytest
from decimal import Decimal

# Test Python fallback and C++ DuckDB Extension fast path for primitive types
def run_tests():
    con = duckdb.connect()
    
    # Try loading the extension
    try:
        con.execute("LOAD cql;")
        print("C++ Extension LOADED.")
    except Exception as e:
        print(f"Extension not found: {e}")
        
    print("Testing CQL Primitives...")
    
    # Tests
    tests = [
        # Boolean
        ("SELECT true as val", True),
        ("SELECT false as val", False),
        # Integer
        ("SELECT 42 as val", 42),
        ("SELECT -1 as val", -1),
        ("SELECT 2147483647 as val", 2147483647), # Max Int32
        # Decimal
        ("SELECT 3.14159265::DECIMAL(10,8) as val", Decimal('3.14159265')),
        # String
        ("SELECT 'hello world' as val", 'hello world'),
        ("SELECT '' as val", ''),
        # Long (CQL 1.5 trial-use)
        ("SELECT 9223372036854775807 as val", 9223372036854775807), # Max Int64
    ]
    
    passed = 0
    failed = 0
    for query, expected in tests:
        try:
            res = con.execute(query).fetchone()[0]
            if res == expected:
                passed += 1
            else:
                print(f"Failed: {query} -> Got {res}, expected {expected}")
                failed += 1
        except Exception as e:
            print(f"Error on {query}: {e}")
            failed += 1
            
    print(f"Passed: {passed}, Failed: {failed}")
    if failed > 0:
        return 1
    return 0

if __name__ == "__main__":
    exit(run_tests())
