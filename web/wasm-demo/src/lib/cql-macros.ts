const CQL_MACRO_SQL = [
  "CREATE MACRO IF NOT EXISTS Abs(x) AS system.abs(x)",
  "CREATE MACRO IF NOT EXISTS Ceiling(x) AS system.ceiling(x)",
  "CREATE MACRO IF NOT EXISTS Floor(x) AS system.floor(x)",
  "CREATE OR REPLACE MACRO Round(x) AS CASE WHEN x IS NULL THEN NULL ELSE CAST(FLOOR(CAST(x AS DOUBLE) + 0.5) AS DECIMAL(38, 8)) END",
  "CREATE OR REPLACE MACRO RoundTo(x, prec) AS CASE WHEN x IS NULL THEN NULL ELSE CAST(FLOOR(CAST(x AS DOUBLE) * POWER(10, prec) + 0.5) / POWER(10, prec) AS DECIMAL(38, 8)) END",
  "CREATE MACRO IF NOT EXISTS Sqrt(x) AS system.sqrt(x)",
  "CREATE MACRO IF NOT EXISTS Exp(x) AS system.exp(x)",
  "CREATE MACRO IF NOT EXISTS Ln(x) AS system.ln(x)",
  "CREATE MACRO IF NOT EXISTS Log(x) AS system.log(x)",
  "CREATE MACRO IF NOT EXISTS LogBase(x, base) AS system.ln(x) / system.ln(base)",
  "CREATE MACRO IF NOT EXISTS Power(x, y) AS system.pow(x, y)",
  "CREATE MACRO IF NOT EXISTS Truncate(x) AS system.trunc(x)",
  "CREATE MACRO IF NOT EXISTS Sign(x) AS system.sign(x)",
  "CREATE MACRO IF NOT EXISTS Mod(x, y) AS x % y",
  "CREATE MACRO IF NOT EXISTS Div(x, y) AS x // y",

  "CREATE MACRO IF NOT EXISTS Length(s) AS system.length(s)",
  "CREATE MACRO IF NOT EXISTS Upper(s) AS system.upper(s)",
  "CREATE MACRO IF NOT EXISTS Lower(s) AS system.lower(s)",
  "CREATE MACRO IF NOT EXISTS Concat(s1, s2) AS s1 || s2",
  "CREATE MACRO IF NOT EXISTS StartsWith(s, prefix) AS system.starts_with(s, prefix)",
  "CREATE MACRO IF NOT EXISTS EndsWith(s, suffix) AS system.ends_with(s, suffix)",
  "CREATE MACRO IF NOT EXISTS Contains(s, pattern) AS system.contains(s, pattern)",
  "CREATE MACRO IF NOT EXISTS Replace(s, from_str, to_str) AS system.replace(s, from_str, to_str)",
  "CREATE MACRO IF NOT EXISTS Split(s, delim) AS system.string_split(s, delim)",
  "CREATE MACRO IF NOT EXISTS SplitOnMatches(s, pattern) AS CASE WHEN s IS NULL OR pattern IS NULL THEN NULL ELSE regexp_split_to_array(s, pattern) END",
  "CREATE MACRO IF NOT EXISTS Trim(s) AS system.trim(s)",
  "CREATE MACRO IF NOT EXISTS LTrim(s) AS system.ltrim(s)",
  "CREATE MACRO IF NOT EXISTS RTrim(s) AS system.rtrim(s)",
  "CREATE MACRO IF NOT EXISTS Reverse(s) AS system.reverse(s)",
  'CREATE MACRO IF NOT EXISTS "Left"(s, n) AS system.left(s, n)',
  'CREATE MACRO IF NOT EXISTS "Right"(s, n) AS system.right(s, n)',
  "CREATE MACRO IF NOT EXISTS Substring(s, start) AS CASE WHEN s IS NULL OR start IS NULL OR start < 0 THEN NULL ELSE system.substring(s, start + 1) END",
  "CREATE MACRO IF NOT EXISTS SubstringLen(s, start, len) AS CASE WHEN s IS NULL OR start IS NULL OR start < 0 THEN NULL ELSE system.substring(s, start + 1, len) END",
  "CREATE MACRO IF NOT EXISTS PositionOf(pattern, s) AS CASE WHEN s IS NULL OR pattern IS NULL THEN NULL WHEN system.strpos(s, pattern) = 0 THEN -1 ELSE system.strpos(s, pattern) - 1 END",
  "CREATE MACRO IF NOT EXISTS Indexer(s, idx) AS CASE WHEN s IS NULL OR idx IS NULL THEN NULL WHEN idx < 0 OR idx >= system.length(s) THEN NULL ELSE system.substring(s, idx + 1, 1) END",
  "CREATE MACRO IF NOT EXISTS Matches(s, pattern) AS CASE WHEN s IS NULL OR pattern IS NULL THEN NULL ELSE regexp_matches(s, pattern) END",
  "CREATE MACRO IF NOT EXISTS ReplaceMatches(s, pattern, replacement) AS CASE WHEN s IS NULL OR pattern IS NULL OR replacement IS NULL THEN NULL ELSE regexp_replace(s, pattern, replace(regexp_replace(replace(replace(replacement, '\\$', '\u0001'), '\\\\', '\\'), '[$](\\d)', '\\\\\\1', 'g'), '\u0001', '$'), 'g') END",
  "CREATE MACRO IF NOT EXISTS Concatenate(s1, s2) AS CASE WHEN s1 IS NULL OR s2 IS NULL THEN NULL ELSE s1 || s2 END",
  "CREATE MACRO IF NOT EXISTS LastPositionOf(pattern, s) AS CASE WHEN s IS NULL OR pattern IS NULL THEN NULL WHEN system.strpos(system.reverse(s), system.reverse(pattern)) = 0 THEN -1 ELSE system.length(s) - system.strpos(system.reverse(s), system.reverse(pattern)) - system.length(pattern) + 1 END",

  "CREATE MACRO IF NOT EXISTS Now() AS CURRENT_TIMESTAMP",
  "CREATE MACRO IF NOT EXISTS Today() AS CURRENT_DATE",
  "CREATE MACRO IF NOT EXISTS TimeOfDay() AS CURRENT_TIME",
  "CREATE MACRO IF NOT EXISTS Year(dt) AS system.year(dt)",
  "CREATE MACRO IF NOT EXISTS Month(dt) AS system.month(dt)",
  "CREATE MACRO IF NOT EXISTS Day(dt) AS system.day(dt)",
  "CREATE MACRO IF NOT EXISTS Hour(dt) AS COALESCE(system.hour(TRY_CAST(system.ltrim(CAST(dt AS VARCHAR), 'T') AS TIME)), system.hour(TRY_CAST(dt AS TIMESTAMP)))",
  "CREATE MACRO IF NOT EXISTS Minute(dt) AS COALESCE(system.minute(TRY_CAST(system.ltrim(CAST(dt AS VARCHAR), 'T') AS TIME)), system.minute(TRY_CAST(dt AS TIMESTAMP)))",
  "CREATE MACRO IF NOT EXISTS Second(dt) AS COALESCE(system.second(TRY_CAST(system.ltrim(CAST(dt AS VARCHAR), 'T') AS TIME)), system.second(TRY_CAST(dt AS TIMESTAMP)))",
  "CREATE MACRO IF NOT EXISTS Millisecond(dt) AS COALESCE(system.millisecond(TRY_CAST(system.ltrim(CAST(dt AS VARCHAR), 'T') AS TIME)), system.millisecond(TRY_CAST(dt AS TIMESTAMP))) % 1000",
  "CREATE MACRO IF NOT EXISTS MakeDate(yr, mo, dy) AS system.make_date(yr, mo, dy)",
  "CREATE MACRO IF NOT EXISTS MakeTime(hr, mi, sc) AS system.make_time(hr, mi, sc)",
  "CREATE MACRO IF NOT EXISTS MakeDateTime(yr, mo, dy) AS system.make_timestamp(yr, mo, dy, 0, 0, 0)",

  "CREATE MACRO IF NOT EXISTS Median(x) AS system.median(x)",
  "CREATE MACRO IF NOT EXISTS Mode(x) AS system.mode(x)",
  "CREATE MACRO IF NOT EXISTS StdDev(x) AS system.stddev_samp(x)",
  "CREATE MACRO IF NOT EXISTS StdDevPop(x) AS system.stddev_pop(x)",
  "CREATE MACRO IF NOT EXISTS Variance(x) AS system.var_samp(x)",
  "CREATE MACRO IF NOT EXISTS VarPop(x) AS system.var_pop(x)",
  "CREATE MACRO IF NOT EXISTS AllTrue(x) AS system.bool_and(x)",
  "CREATE MACRO IF NOT EXISTS AnyTrue(x) AS system.bool_or(x)",
  "CREATE MACRO IF NOT EXISTS AllFalse(x) AS NOT system.bool_or(x)",
  "CREATE MACRO IF NOT EXISTS AnyFalse(x) AS NOT system.bool_and(x)",

  'CREATE MACRO IF NOT EXISTS "And"(a, b) AS a AND b',
  'CREATE MACRO IF NOT EXISTS "Or"(a, b) AS a OR b',
  'CREATE MACRO IF NOT EXISTS "Not"(a) AS NOT a',
  'CREATE MACRO IF NOT EXISTS "Coalesce"(a, b) AS COALESCE(a, b)',
  'CREATE MACRO IF NOT EXISTS "Xor"(a, b) AS (a OR b) AND NOT (a AND b)',
  `CREATE MACRO IF NOT EXISTS "Implies"(a, b) AS
        CASE
            WHEN a = false THEN true
            WHEN b = true THEN true
            WHEN a IS NULL OR b IS NULL THEN NULL
            ELSE NOT a OR b
        END`,
  'CREATE MACRO IF NOT EXISTS "IsNull"(x) AS x IS NULL',
  'CREATE MACRO IF NOT EXISTS "IsNotNull"(x) AS x IS NOT NULL',
  'CREATE MACRO IF NOT EXISTS "IfNull"(a, b) AS COALESCE(a, b)',
  'CREATE MACRO IF NOT EXISTS "IsTrue"(x) AS (x IS NOT NULL AND x = true)',
  'CREATE MACRO IF NOT EXISTS "IsFalse"(x) AS (x IS NOT NULL AND x = false)',

  "CREATE MACRO IF NOT EXISTS ToString(x) AS CAST(x AS VARCHAR)",
  "CREATE MACRO IF NOT EXISTS ToInteger(x) AS CAST(x AS INTEGER)",
  "CREATE MACRO IF NOT EXISTS ToDecimal(x) AS CAST(x AS DECIMAL)",
  "CREATE MACRO IF NOT EXISTS ToBoolean(x) AS CAST(x AS BOOLEAN)",
  "CREATE MACRO IF NOT EXISTS ToDate(x) AS CAST(x AS DATE)",
  "CREATE MACRO IF NOT EXISTS ToDateTime(x) AS CAST(x AS TIMESTAMP)",
  "CREATE MACRO IF NOT EXISTS ToTime(x) AS TRY_CAST(system.ltrim(CAST(x AS VARCHAR), 'T') AS TIME)",
  "CREATE MACRO IF NOT EXISTS QuantityToString(q) AS CASE WHEN q IS NULL THEN NULL WHEN typeof(q) = 'VARCHAR' AND q LIKE '{%' AND TRY_CAST(json_extract_string(q, '$.value') AS DECIMAL(38, 8)) IS NOT NULL THEN regexp_replace(regexp_replace(CAST(TRY_CAST(json_extract_string(q, '$.value') AS DECIMAL(38, 8)) AS VARCHAR), '0+$', ''), '[.]$', '') || ' ''' || COALESCE(json_extract_string(q, '$.unit'), json_extract_string(q, '$.code'), '1') || '''' ELSE CAST(q AS VARCHAR) END",

  "CREATE MACRO IF NOT EXISTS First(lst) AS CASE WHEN lst IS NULL OR system.array_length(lst) = 0 THEN NULL ELSE lst[1] END",
  "CREATE MACRO IF NOT EXISTS Last(lst) AS CASE WHEN lst IS NULL OR system.array_length(lst) = 0 THEN NULL ELSE lst[-1] END",
  "CREATE MACRO IF NOT EXISTS Skip(lst, n) AS CASE WHEN lst IS NULL OR n IS NULL OR n < 0 THEN NULL WHEN n >= system.array_length(lst) THEN [] ELSE lst[n + 1:] END",
  "CREATE MACRO IF NOT EXISTS Take(lst, n) AS CASE WHEN lst IS NULL THEN NULL WHEN n IS NULL OR n <= 0 THEN lst[1:0] ELSE lst[1:n] END",
  'CREATE OR REPLACE MACRO "Distinct"(lst) AS CASE WHEN lst IS NULL THEN NULL WHEN system.array_length(lst) = 0 THEN lst ELSE COALESCE((SELECT list(val ORDER BY pos) FROM (SELECT val, MIN(pos) as pos FROM (SELECT unnest(lst) AS val, generate_subscripts(lst, 1) AS pos) GROUP BY val)), []) END',
  "CREATE MACRO IF NOT EXISTS Tail(lst) AS CASE WHEN lst IS NULL THEN NULL WHEN system.array_length(lst) <= 1 THEN lst[1:0] ELSE lst[2:] END",
  "CREATE MACRO IF NOT EXISTS CQLIndexOf(lst, elem) AS CASE WHEN lst IS NULL OR elem IS NULL THEN NULL WHEN list_position(lst, elem) IS NULL THEN -1 WHEN list_position(lst, elem) = 0 THEN -1 ELSE list_position(lst, elem) - 1 END",
  "CREATE MACRO IF NOT EXISTS Combine(lst) AS CASE WHEN lst IS NULL THEN NULL ELSE system.array_to_string(list_filter(lst, x -> x IS NOT NULL), '') END",
  "CREATE MACRO IF NOT EXISTS CombineSep(lst, sep) AS CASE WHEN lst IS NULL THEN NULL ELSE system.array_to_string(list_filter(lst, x -> x IS NOT NULL), sep) END",
  "CREATE MACRO IF NOT EXISTS Product(lst) AS CASE WHEN lst IS NULL THEN NULL ELSE list_aggregate(list_transform(lst, _v -> TRY_CAST(_v AS DOUBLE)), 'product') END",
  "CREATE MACRO IF NOT EXISTS GeometricMean(lst) AS CASE WHEN lst IS NULL THEN NULL ELSE exp(list_aggregate(list_transform(lst, _v -> ln(TRY_CAST(_v AS DOUBLE))), 'avg')) END",
  "CREATE MACRO IF NOT EXISTS descendents(x) AS CASE WHEN x IS NULL THEN NULL ELSE x END",

  `CREATE OR REPLACE MACRO audit_and(a, b) AS (
        struct_pack(
            result   := struct_extract(a, 'result') AND struct_extract(b, 'result'),
            evidence := list_concat(
                COALESCE(struct_extract(a, 'evidence'), []),
                COALESCE(struct_extract(b, 'evidence'), [])
            )
        )
    )`,
  `CREATE OR REPLACE MACRO audit_or(a, b) AS (
        struct_pack(
            result   := struct_extract(a, 'result') OR struct_extract(b, 'result'),
            evidence := CASE
                WHEN struct_extract(a, 'result') THEN COALESCE(struct_extract(a, 'evidence'), [])
                WHEN struct_extract(b, 'result') THEN COALESCE(struct_extract(b, 'evidence'), [])
                ELSE list_distinct(list_concat(COALESCE(struct_extract(a, 'evidence'), []), COALESCE(struct_extract(b, 'evidence'), [])))
            END
        )
    )`,
  `CREATE OR REPLACE MACRO audit_or_all(a, b) AS (
        struct_pack(
            result   := struct_extract(a, 'result') OR struct_extract(b, 'result'),
            evidence := list_distinct(list_concat(
                COALESCE(struct_extract(a, 'evidence'), []),
                COALESCE(struct_extract(b, 'evidence'), [])
            ))
        )
    )`,
  `CREATE OR REPLACE MACRO audit_not(a) AS (
        struct_pack(
            result   := NOT struct_extract(a, 'result'),
            evidence := COALESCE(struct_extract(a, 'evidence'), [])
        )
    )`,
  `CREATE OR REPLACE MACRO audit_leaf(val) AS (
        struct_pack(
            result   := val,
            evidence := []::STRUCT(target VARCHAR, attribute VARCHAR, value VARCHAR, operator VARCHAR, threshold VARCHAR, trace VARCHAR[])[]
        )
    )`,
  `CREATE OR REPLACE MACRO audit_comparison(result_val, op, lhs, rhs, ev_attr, target_id) AS (
        struct_pack(
            result   := result_val,
            evidence := list_value(struct_pack(
                target      := CAST(target_id AS VARCHAR),
                attribute   := CAST(ev_attr AS VARCHAR),
                value       := CAST(lhs AS VARCHAR),
                operator    := CAST(op AS VARCHAR),
                threshold   := CAST(rhs AS VARCHAR),
                trace       := CAST([] AS VARCHAR[])
            ))::STRUCT(target VARCHAR, attribute VARCHAR, value VARCHAR, operator VARCHAR, threshold VARCHAR, trace VARCHAR[])[]
        )
    )`,
  "CREATE OR REPLACE MACRO compact_audit(aud) AS aud",
  `CREATE OR REPLACE MACRO audit_breadcrumb(aud, def_name) AS (
        struct_pack(
            result := struct_extract(aud, 'result'),
            evidence := list_transform(
                COALESCE(struct_extract(aud, 'evidence'), []),
                _ev -> struct_pack(
                    target := _ev.target,
                    attribute := _ev.attribute,
                    value := _ev.value,
                    operator := _ev.operator,
                    threshold := _ev.threshold,
                    trace := list_append(COALESCE(_ev.trace, CAST([] AS VARCHAR[])), def_name)
                )
            )
        )
    )`,

  // ── Type-disambiguation macros (BENCH-001 Option D parity with the
  // desktop macros/clinical.py surface). The CQL translator emits these
  // for `is Interval<DateTime>` / `is Interval<Quantity>` / `is Period` /
  // `is Range` checks and Quantity $.value unwrapping in comparison
  // coercion; without them any quantity comparison (e.g.
  // `O.valueQuantity.value > 140`) fails with a Catalog Error in the
  // browser runtime. NULL semantics match desktop: starts_with(NULL, '{')
  // is NULL → ELSE → FALSE.
  "CREATE MACRO IF NOT EXISTS cql_value_is_period(value) AS CASE WHEN starts_with(LTRIM(value), '{') THEN json_extract_string(value, '$.start') IS NOT NULL OR json_extract_string(value, '$.end') IS NOT NULL ELSE FALSE END",
  "CREATE MACRO IF NOT EXISTS cql_value_is_range(value) AS CASE WHEN starts_with(LTRIM(value), '{') THEN json_extract_string(value, '$.low') IS NOT NULL OR json_extract_string(value, '$.high') IS NOT NULL ELSE FALSE END",
  "CREATE MACRO IF NOT EXISTS cql_value_is_interval_like(value) AS CASE WHEN starts_with(LTRIM(value), '{') THEN json_extract_string(value, '$.start') IS NOT NULL OR json_extract_string(value, '$.end') IS NOT NULL OR json_extract_string(value, '$.low') IS NOT NULL OR json_extract_string(value, '$.high') IS NOT NULL ELSE FALSE END",
  "CREATE MACRO IF NOT EXISTS cql_quantity_value(value) AS CASE WHEN starts_with(LTRIM(value), '{') THEN json_extract_string(value, '$.value') ELSE value END",
  // ── List-equality macro layer (port of desktop macros/list.py). The
  // CQL translator emits CQLListContainsEq for `contains` / `in` over
  // FHIR list-valued navigation (e.g. C.code.coding.code contains 'x').
  // The C++ extension provides intervalEquals / quantityCompare used by
  // CQLListElementEqual. ORDER MATTERS: dependencies first.
  "CREATE MACRO IF NOT EXISTS CQLClinicalCodeSystem(_code_json) AS COALESCE(json_extract_string(_code_json, '$.system'), json_extract_string(_code_json, '$.codesystem'))",
  "CREATE MACRO IF NOT EXISTS CQLClinicalValueKind(_clinical_value) AS CASE WHEN TRY_CAST(CAST(_clinical_value AS VARCHAR) AS JSON) IS NULL THEN NULL WHEN json_type(TRY_CAST(CAST(_clinical_value AS VARCHAR) AS JSON), '$.codes') = 'ARRAY' THEN 'Concept' WHEN json_extract_string(TRY_CAST(CAST(_clinical_value AS VARCHAR) AS JSON), '$.code') IS NOT NULL AND json_type(TRY_CAST(CAST(_clinical_value AS VARCHAR) AS JSON), '$.value') IS NULL THEN 'Code' ELSE NULL END",
  "CREATE MACRO IF NOT EXISTS CQLClinicalValueHasShape(_clinical_value) AS CQLClinicalValueKind(_clinical_value) IS NOT NULL",

  // ── Clinical value-equality macros (port of desktop macros/list.py):
  // CQLClinicalValueEqual is referenced by CQLListElementEqual.
  "CREATE MACRO IF NOT EXISTS CQLClinicalCodeEqual(left_code, right_code) AS CASE WHEN CQLClinicalValueKind(left_code) != 'Code' OR CQLClinicalValueKind(right_code) != 'Code' THEN FALSE WHEN (json_extract_string(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON), '$.code') IS NULL) OR (json_extract_string(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON), '$.code') IS NULL) THEN FALSE WHEN ((CQLClinicalCodeSystem(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON)) IS NOT NULL) <> (CQLClinicalCodeSystem(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON)) IS NOT NULL)) THEN NULL WHEN json_extract_string(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON), '$.code') IS DISTINCT FROM json_extract_string(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON), '$.code') THEN FALSE WHEN CQLClinicalCodeSystem(TRY_CAST(CAST(left_code AS VARCHAR) AS JSON)) IS DISTINCT FROM CQLClinicalCodeSystem(TRY_CAST(CAST(right_code AS VARCHAR) AS JSON)) THEN FALSE ELSE TRUE END",
  "CREATE MACRO IF NOT EXISTS CQLClinicalConceptCodesEqual(left_concept, right_concept) AS CASE WHEN json_array_length(json_extract(TRY_CAST(CAST(left_concept AS VARCHAR) AS JSON), '$.codes')) != json_array_length(json_extract(TRY_CAST(CAST(right_concept AS VARCHAR) AS JSON), '$.codes')) THEN FALSE WHEN EXISTS (SELECT 1 FROM json_each(TRY_CAST(CAST(left_concept AS VARCHAR) AS JSON), '$.codes') AS _left_each JOIN json_each(TRY_CAST(CAST(right_concept AS VARCHAR) AS JSON), '$.codes') AS _right_each ON TRY_CAST(_left_each.key AS BIGINT) = TRY_CAST(_right_each.key AS BIGINT) WHERE CQLClinicalCodeEqual(TRY_CAST(_left_each.value AS JSON), TRY_CAST(_right_each.value AS JSON)) IS FALSE) THEN FALSE WHEN EXISTS (SELECT 1 FROM json_each(TRY_CAST(CAST(left_concept AS VARCHAR) AS JSON), '$.codes') AS _left_each JOIN json_each(TRY_CAST(CAST(right_concept AS VARCHAR) AS JSON), '$.codes') AS _right_each ON TRY_CAST(_left_each.key AS BIGINT) = TRY_CAST(_right_each.key AS BIGINT) WHERE CQLClinicalCodeEqual(TRY_CAST(_left_each.value AS JSON), TRY_CAST(_right_each.value AS JSON)) IS NULL) THEN NULL ELSE TRUE END",
  "CREATE MACRO IF NOT EXISTS CQLClinicalValueEqual(left_value, right_value) AS CASE WHEN CQLClinicalValueKind(left_value) IS NULL OR CQLClinicalValueKind(right_value) IS NULL THEN FALSE WHEN CQLClinicalValueKind(left_value) != CQLClinicalValueKind(right_value) THEN FALSE WHEN CQLClinicalValueKind(left_value) = 'Code' THEN CQLClinicalCodeEqual(left_value, right_value) ELSE CQLClinicalConceptCodesEqual(left_value, right_value) END",
  "CREATE MACRO IF NOT EXISTS CQLIntervalValueHasShape(_interval_value) AS CASE WHEN TRY_CAST(CAST(_interval_value AS VARCHAR) AS JSON) IS NULL THEN FALSE WHEN json_type(TRY_CAST(CAST(_interval_value AS VARCHAR) AS JSON), '$.lowClosed') = 'BOOLEAN' AND json_type(TRY_CAST(CAST(_interval_value AS VARCHAR) AS JSON), '$.highClosed') = 'BOOLEAN' AND (json_type(TRY_CAST(CAST(_interval_value AS VARCHAR) AS JSON), '$.low') IS NOT NULL OR json_type(TRY_CAST(CAST(_interval_value AS VARCHAR) AS JSON), '$.high') IS NOT NULL) THEN TRUE ELSE FALSE END",
  "CREATE MACRO IF NOT EXISTS CQLListElementEqual(left_value, right_value) AS CASE WHEN left_value IS NULL AND right_value IS NULL THEN TRUE WHEN left_value IS NULL OR right_value IS NULL THEN FALSE WHEN CQLClinicalValueHasShape(left_value) AND CQLClinicalValueHasShape(right_value) THEN CQLClinicalValueEqual(left_value, right_value) WHEN CQLClinicalValueHasShape(left_value) OR CQLClinicalValueHasShape(right_value) THEN FALSE WHEN CQLIntervalValueHasShape(left_value) AND CQLIntervalValueHasShape(right_value) THEN intervalEquals(CAST(left_value AS VARCHAR), CAST(right_value AS VARCHAR)) WHEN CQLIntervalValueHasShape(left_value) OR CQLIntervalValueHasShape(right_value) THEN FALSE WHEN starts_with(ltrim(CAST(left_value AS VARCHAR)), '{') AND starts_with(ltrim(CAST(right_value AS VARCHAR)), '{') AND system.contains(CAST(left_value AS VARCHAR), '\"value\"') AND system.contains(CAST(left_value AS VARCHAR), '\"unit\"') AND system.contains(CAST(right_value AS VARCHAR), '\"value\"') AND system.contains(CAST(right_value AS VARCHAR), '\"unit\"') THEN quantityCompare(CAST(left_value AS VARCHAR), CAST(right_value AS VARCHAR), '==') WHEN typeof(left_value) != typeof(right_value) AND (system.contains(typeof(left_value), 'INT') OR starts_with(typeof(left_value), 'DECIMAL') OR typeof(left_value) IN ('FLOAT', 'DOUBLE')) AND (system.contains(typeof(right_value), 'INT') OR starts_with(typeof(right_value), 'DECIMAL') OR typeof(right_value) IN ('FLOAT', 'DOUBLE')) THEN COALESCE(TRY_CAST(left_value AS DECIMAL(38,8)) = TRY_CAST(right_value AS DECIMAL(38,8)), FALSE) WHEN typeof(left_value) != typeof(right_value) THEN FALSE WHEN left_value = right_value THEN TRUE ELSE FALSE END",
  "CREATE MACRO IF NOT EXISTS CQLListContainsEq(lst, elem) AS CASE WHEN lst IS NULL THEN FALSE WHEN elem IS NULL THEN system.array_length(lst) != list_count(lst) WHEN EXISTS (SELECT 1 FROM (SELECT COALESCE(lst, []) AS _cql_contains_l) _cql_contains_t, UNNEST(_cql_contains_t._cql_contains_l) AS _cql_contains_u(_cql_contains_item) WHERE CQLListElementEqual(_cql_contains_item, elem) IS TRUE) THEN TRUE WHEN EXISTS (SELECT 1 FROM (SELECT COALESCE(lst, []) AS _cql_contains_l) _cql_contains_t, UNNEST(_cql_contains_t._cql_contains_l) AS _cql_contains_u(_cql_contains_item) WHERE CQLListElementEqual(_cql_contains_item, elem) IS NULL) THEN NULL ELSE FALSE END",
  // ── ConvertsToInteger (port of desktop udf/conversion.py semantics):
  // Boolean -> true; Integer -> true; Long -> range check; Decimal/FLOAT -> false
  // (CQL 1.5 Table 9-E has no Decimal->Integer conversion); integer-grammar
  // strings -> int32 range check; everything else false.
  "CREATE MACRO IF NOT EXISTS ConvertsToInteger(x) AS CASE WHEN x IS NULL THEN NULL WHEN typeof(x) = 'BOOLEAN' THEN TRUE WHEN typeof(x) IN ('TINYINT','SMALLINT','INTEGER') THEN TRUE WHEN typeof(x) = 'BIGINT' THEN CAST(x AS BIGINT) BETWEEN -2147483648 AND 2147483647 WHEN starts_with(typeof(x), 'DECIMAL') OR typeof(x) IN ('FLOAT','DOUBLE') THEN FALSE WHEN typeof(x) = 'VARCHAR' AND regexp_full_match(CAST(x AS VARCHAR), '^[+-]?[0-9]+$') THEN TRY_CAST(CAST(x AS VARCHAR) AS BIGINT) BETWEEN -2147483648 AND 2147483647 ELSE FALSE END",
];

export async function registerCQLMacros(conn: any): Promise<void> {
  for (const sql of CQL_MACRO_SQL) {
    await conn.query(sql);
  }
}
