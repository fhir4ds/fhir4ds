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
  "CREATE MACRO IF NOT EXISTS QuantityToString(q) AS CASE WHEN q IS NULL THEN NULL WHEN typeof(q) = 'VARCHAR' AND q LIKE '{%' THEN CAST(json_extract(q, '$.value') AS VARCHAR) || ' ''' || COALESCE(json_extract_string(q, '$.unit'), json_extract_string(q, '$.code'), '1') || '''' ELSE CAST(q AS VARCHAR) END",

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
];

export async function registerCQLMacros(conn: any): Promise<void> {
  for (const sql of CQL_MACRO_SQL) {
    await conn.query(sql);
  }
}
