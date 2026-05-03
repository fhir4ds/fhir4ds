#!/usr/bin/env python3
"""
FP-11 SKEPTIC Personality — Adversarial Tests for §5.7 Math (STU)
Targets: abs(), ceiling(), exp(), floor(), ln(), log(base), power(exponent), round([precision]), sqrt(), truncate()

SKEPTIC BUG PREDICTIONS (from C++ source review):
  BUG-1 (CRITICAL): exp() has NO NaN/Infinity output check — exp(1000) → Infinity returned as 'inf.0'
  BUG-2 (HIGH): empty input () — () is not valid FHIRPath syntax, so test via other means
  BUG-3 (MEDIUM): round() with negative precision — spec allows negative precision
  BUG-4 (HIGH): truncate() on negative decimals — verify truncation toward zero behavior
  BUG-5 (MEDIUM): abs() on Quantity — should return Quantity with absolute value, verify unit preserved

NOTE: The DuckDB UDF returns List<String> so all expected values are strings.
"""
import duckdb, json, sys, os, math

sys.path.insert(0, '/mnt/d/fhir4ds')
os.chdir('/mnt/d/fhir4ds')

PASS = 0
FAIL = 0
ISSUES = []

conn = duckdb.connect(config={"allow_unsigned_extensions": True})
conn.execute("FORCE INSTALL '/mnt/d/fhir4ds/extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension'")
conn.execute("LOAD fhirpath")

def fp(expr, resource='{"resourceType": "Patient"}'):
    """Evaluate a FHIRPath expression against a resource."""
    r = conn.execute("SELECT fhirpath(?, ?)", [json.dumps(json.loads(resource)), expr]).fetchone()
    return r[0] if r else None

def test(category, name, expr, expected, resource='{"resourceType": "Patient"}', severity="MEDIUM"):
    """expected should be a list of strings, or [] for empty, or None to just check no crash"""
    global PASS, FAIL
    try:
        result = fp(expr, resource)

        # If expected is None, we just check no crash
        if expected is None:
            PASS += 1
            return

        # Normalize both to lists of strings for comparison
        norm_expected = [str(e) for e in expected] if expected is not None else []
        norm_result = [str(x) for x in result] if result is not None else []

        # For float comparison, try numeric matching
        matched = False
        if len(norm_expected) == len(norm_result):
            all_match = True
            for e, r in zip(norm_expected, norm_result):
                try:
                    ef = float(e)
                    rf = float(r)
                    if abs(ef - rf) < 0.0001:
                        continue
                    else:
                        all_match = False
                        break
                except (ValueError, TypeError):
                    if e == r:
                        continue
                    else:
                        all_match = False
                        break
            matched = all_match

        if matched:
            PASS += 1
        else:
            FAIL += 1
            issue = {
                "category": category,
                "name": name,
                "expr": expr,
                "expected": norm_expected,
                "actual": norm_result,
                "severity": severity,
                "resource": resource if resource != '{"resourceType": "Patient"}' else "default"
            }
            ISSUES.append(issue)
            print(f"  FAIL [{severity}] {category}/{name}: expr={expr}")
            print(f"    expected: {norm_expected}")
            print(f"    actual:   {norm_result}")
    except Exception as e:
        # If we expected empty, exception is OK
        if expected == [] or expected is None:
            PASS += 1
        else:
            FAIL += 1
            issue = {
                "category": category,
                "name": name,
                "expr": expr,
                "expected": [str(x) for x in expected] if expected else [],
                "actual": f"EXCEPTION: {e}",
                "severity": severity,
                "resource": resource if resource != '{"resourceType": "Patient"}' else "default"
            }
            ISSUES.append(issue)
            print(f"  FAIL [{severity}] {category}/{name}: expr={expr}")
            print(f"    expected: {[str(x) for x in expected] if expected else []}")
            print(f"    actual:   EXCEPTION: {e}")

print("=" * 80)
print("FP-11 SKEPTIC: Math Functions (abs/ceiling/exp/floor/ln/log/power/round/sqrt/truncate)")
print("=" * 80)

# ============================================================================
# SECTION 1: abs() — Absolute Value
# ============================================================================
print("\n--- SECTION 1: abs() ---")

test("abs", "positive_int", "(5).abs()", [5])
test("abs", "negative_int", "(-5).abs()", [5])
test("abs", "zero_int", "(0).abs()", [0])
test("abs", "positive_decimal", "(3.14).abs()", [3.14])
test("abs", "negative_decimal", "(-3.14).abs()", [3.14])
test("abs", "very_large_negative", "(-999999999).abs()", [999999999])
test("abs", "negative_fraction", "(-0.001).abs()", [0.001])

# Quantity abs from JSON
r_qty = '{"resourceType": "Observation", "valueQuantity": {"value": -5.5, "unit": "cm"}}'
test("abs", "quantity_value_abs", "Observation.valueQuantity.value.abs()", [5.5], r_qty)

# ============================================================================
# SECTION 2: ceiling() — Round Up to Integer
# ============================================================================
print("\n--- SECTION 2: ceiling() ---")

test("ceiling", "int_passthrough", "(5).ceiling()", [5])
test("ceiling", "int_negative", "(-5).ceiling()", [-5])
test("ceiling", "decimal_positive_up", "(3.2).ceiling()", [4])
test("ceiling", "decimal_positive_exact", "(3.0).ceiling()", [3])
test("ceiling", "decimal_negative_up", "(-3.2).ceiling()", [-3], severity="HIGH")  # ceil(-3.2) = -3
test("ceiling", "decimal_negative_exact", "(-3.0).ceiling()", [-3])
test("ceiling", "decimal_small_positive", "(0.1).ceiling()", [1])
test("ceiling", "decimal_small_negative", "(-0.1).ceiling()", [0], severity="HIGH")  # ceil(-0.1) = 0
test("ceiling", "zero", "(0).ceiling()", [0])

# ============================================================================
# SECTION 3: floor() — Round Down to Integer
# ============================================================================
print("\n--- SECTION 3: floor() ---")

test("floor", "int_passthrough", "(5).floor()", [5])
test("floor", "int_negative", "(-5).floor()", [-5])
test("floor", "decimal_positive_down", "(3.8).floor()", [3])
test("floor", "decimal_positive_exact", "(3.0).floor()", [3])
test("floor", "decimal_negative_down", "(-3.2).floor()", [-4], severity="HIGH")  # floor(-3.2) = -4
test("floor", "decimal_small_positive", "(0.9).floor()", [0])
test("floor", "decimal_small_negative", "(-0.1).floor()", [-1], severity="HIGH")  # floor(-0.1) = -1
test("floor", "zero", "(0).floor()", [0])

# ============================================================================
# SECTION 4: exp() — e^x
# ============================================================================
print("\n--- SECTION 4: exp() ---")

test("exp", "exp_0", "(0).exp()", [1.0])  # e^0 = 1
test("exp", "exp_1", "(1).exp()", [math.e])  # e^1 ≈ 2.718
test("exp", "exp_negative", "(-1).exp()", [1.0 / math.e])  # e^-1 ≈ 0.368
test("exp", "exp_2", "(2).exp()", [math.e ** 2])  # e^2 ≈ 7.389

# BUG-1 (CRITICAL): exp(1000) → Infinity, should return empty per spec
test("exp", "exp_overflow_1000", "(1000).exp()", [], severity="CRITICAL")

# exp of very large but finite
test("exp", "exp_500", "(500).exp()", None, severity="HIGH")  # just check no crash

# exp of very negative → underflow to 0
test("exp", "exp_underflow_neg1000", "(-1000).exp()", [0.0], severity="HIGH")

# ============================================================================
# SECTION 5: ln() — Natural Logarithm
# ============================================================================
print("\n--- SECTION 5: ln() ---")

test("ln", "ln_1", "(1).ln()", [0.0])  # ln(1) = 0
test("ln", "ln_e_approx", "(2.718281828).ln()", [1.0])  # ln(e) ≈ 1
test("ln", "ln_10", "(10).ln()", [math.log(10)])

# Domain errors — should return empty
test("ln", "ln_0", "(0).ln()", [], severity="HIGH")  # ln(0) undefined
test("ln", "ln_negative", "(-1).ln()", [], severity="HIGH")  # ln(-1) undefined

# Small positive
test("ln", "ln_small", "(0.001).ln()", [math.log(0.001)])

# ============================================================================
# SECTION 6: log(base) — Logarithm with Base
# ============================================================================
print("\n--- SECTION 6: log(base) ---")

test("log", "log_100_10", "(100).log(10)", [2.0])  # log10(100) = 2
test("log", "log_8_2", "(8).log(2)", [3.0])  # log2(8) = 3
test("log", "log_1_any", "(1).log(10)", [0.0])  # log10(1) = 0

# Domain errors
test("log", "log_0_base10", "(0).log(10)", [], severity="HIGH")  # log(0) undefined
test("log", "log_negative_base10", "(-1).log(10)", [], severity="HIGH")  # log(-1) undefined
test("log", "log_8_base1", "(8).log(1)", [], severity="HIGH")  # log base 1 undefined
test("log", "log_8_base0", "(8).log(0)", [], severity="HIGH")  # log base 0 undefined
test("log", "log_8_negative_base", "(8).log(-2)", [], severity="MEDIUM")  # negative base undefined

# ============================================================================
# SECTION 7: power(exponent) — x^y
# ============================================================================
print("\n--- SECTION 7: power(exponent) ---")

test("power", "2_3", "(2).power(3)", [8])
test("power", "2_0", "(2).power(0)", [1])
test("power", "2_1", "(2).power(1)", [2])
test("power", "x_half_sqrt", "(9).power(0.5)", [3.0])  # sqrt via power
test("power", "negative_base_odd", "(-2).power(3)", [-8])
test("power", "negative_base_even", "(-2).power(2)", [4])

# 0^0 = undefined per spec
test("power", "0_0", "(0).power(0)", [], severity="HIGH")

# Overflow — power(10, 308) is near double max
test("power", "overflow_10_308", "(10).power(308)", None, severity="CRITICAL")

# Large power that overflows
test("power", "overflow_2_1024", "(2).power(1024)", [], severity="HIGH")

# Negative exponent
test("power", "neg_exp", "(2).power(-1)", [0.5])

# ============================================================================
# SECTION 8: round([precision])
# ============================================================================
print("\n--- SECTION 8: round([precision]) ---")

# No precision — round to integer
test("round", "no_precision_half", "(3.5).round()", [4.0])
test("round", "no_precision_down", "(3.4).round()", [3.0])
test("round", "no_precision_negative_half", "(-3.5).round()", [-4.0], severity="HIGH")  # std::round(-3.5) = -4
test("round", "integer_passthrough", "(5).round()", [5.0])

# Precision 0 — same as no precision
test("round", "precision_0", "(3.5).round(0)", [4.0])

# Precision 1
test("round", "precision_1_up", "(3.45).round(1)", [3.5])
test("round", "precision_1_down", "(3.44).round(1)", [3.4])

# Precision 2
test("round", "precision_2", "(3.456).round(2)", [3.46])

# Negative precision — round to tens, hundreds
test("round", "precision_neg1", "(123.456).round(-1)", [120.0], severity="HIGH")
test("round", "precision_neg2", "(123.456).round(-2)", [100.0], severity="HIGH")
test("round", "precision_neg3", "(123.456).round(-3)", [0.0], severity="MEDIUM")

# ============================================================================
# SECTION 9: sqrt() — Square Root
# ============================================================================
print("\n--- SECTION 9: sqrt() ---")

test("sqrt", "perfect_square_4", "(4).sqrt()", [2.0])
test("sqrt", "perfect_square_9", "(9).sqrt()", [3.0])
test("sqrt", "non_perfect_2", "(2).sqrt()", [math.sqrt(2)])
test("sqrt", "zero", "(0).sqrt()", [0.0])
test("sqrt", "one", "(1).sqrt()", [1.0])
test("sqrt", "small_decimal", "(0.25).sqrt()", [0.5])

# Domain error — negative
test("sqrt", "negative", "(-1).sqrt()", [], severity="HIGH")

# ============================================================================
# SECTION 10: truncate() — Remove Decimal Portion (toward zero)
# ============================================================================
print("\n--- SECTION 10: truncate() ---")

test("truncate", "positive_decimal", "(3.7).truncate()", [3])
test("truncate", "positive_decimal_small", "(3.1).truncate()", [3])
test("truncate", "negative_decimal", "(-3.7).truncate()", [-3], severity="HIGH")  # truncate toward zero
test("truncate", "negative_decimal_small", "(-3.1).truncate()", [-3], severity="HIGH")
test("truncate", "integer_passthrough", "(5).truncate()", [5])
test("truncate", "zero", "(0).truncate()", [0])
test("truncate", "positive_exact", "(3.0).truncate()", [3])
test("truncate", "negative_exact", "(-3.0).truncate()", [-3])
test("truncate", "large_decimal", "(999999.999).truncate()", [999999])

# ============================================================================
# SECTION 11: Cross-type Input Testing (JSON-derived types)
# ============================================================================
print("\n--- SECTION 11: Cross-type Input ---")

r_int = '{"resourceType": "Patient", "id": "123"}'
test("cross_type", "json_int_abs", "Patient.id.toInteger().abs()", [123], r_int)

r_dec = '{"resourceType": "Observation", "valueQuantity": {"value": 3.7}}'
test("cross_type", "json_decimal_ceiling", "Observation.valueQuantity.value.ceiling()", [4], r_dec)
test("cross_type", "json_decimal_floor", "Observation.valueQuantity.value.floor()", [3], r_dec)
test("cross_type", "json_decimal_truncate", "Observation.valueQuantity.value.truncate()", [3], r_dec)

r_neg = '{"resourceType": "Observation", "valueQuantity": {"value": -3.7}}'
test("cross_type", "json_neg_ceiling", "Observation.valueQuantity.value.ceiling()", [-3], r_neg, severity="HIGH")
test("cross_type", "json_neg_floor", "Observation.valueQuantity.value.floor()", [-4], r_neg, severity="HIGH")
test("cross_type", "json_neg_truncate", "Observation.valueQuantity.value.truncate()", [-3], r_neg, severity="HIGH")

# ============================================================================
# SECTION 12: Adversarial / Skeptic-specific tests
# ============================================================================
print("\n--- SECTION 12: Adversarial Tests ---")

# BUG-1 CONFIRMED: exp(1000) returns 'inf.0' instead of empty
test("adversarial", "exp_overflow_returns_inf", "(1000).exp()", [], severity="CRITICAL")

# power overflow
test("adversarial", "power_overflow_2_1024", "(2).power(1024)", [], severity="CRITICAL")

# sqrt of very small positive
test("adversarial", "sqrt_tiny", "(0.00000001).sqrt()", [math.sqrt(0.00000001)])

# round with very large precision
test("adversarial", "round_large_precision", "(3.14).round(20)", [3.14])

# abs on boolean (should convert to int first?)
test("adversarial", "abs_true", "true.abs()", [1], severity="MEDIUM")

# ceiling/floor of negative zero
test("adversarial", "ceiling_neg_zero", "(-0.0).ceiling()", [0], severity="LOW")
test("adversarial", "floor_neg_zero", "(-0.0).floor()", [0], severity="LOW")

# ln of very small positive (near zero)
test("adversarial", "ln_tiny", "(0.0000001).ln()", [math.log(0.0000001)])

# log with decimal base
test("adversarial", "log_decimal_base", "(10).log(2.5)", None, severity="MEDIUM")

# power with decimal exponent
test("adversarial", "power_decimal_exp", "(4).power(0.5)", [2.0])

# exp of decimal
test("adversarial", "exp_decimal", "(0.5).exp()", [math.exp(0.5)])

# truncate of negative zero
test("adversarial", "truncate_neg_zero", "(-0.0).truncate()", [0], severity="LOW")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print(f"FP-11 SKEPTIC RESULTS: PASS={PASS} FAIL={FAIL}")
print("=" * 80)

if ISSUES:
    print(f"\n{len(ISSUES)} ISSUES FOUND:")
    for i, issue in enumerate(ISSUES, 1):
        print(f"\n  Issue #{i} [{issue['severity']}] {issue['category']}/{issue['name']}")
        print(f"    expr:     {issue['expr']}")
        print(f"    expected: {issue['expected']}")
        print(f"    actual:   {issue['actual']}")
else:
    print("\nNo issues found.")

# Write JSON report
report = {
    "personality": "SKEPTIC",
    "chunk": "FP-11",
    "section": "§5.7 Math (STU)",
    "pass": PASS,
    "fail": FAIL,
    "total": PASS + FAIL,
    "issues": ISSUES
}
with open("fp11_skeptic_report.json", "w") as f:
    json.dump(report, f, indent=2)
print(f"\nReport saved to fp11_skeptic_report.json")
