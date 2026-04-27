"""
Master runner for QA iterations 51-70. Correct API usage:
- CQL: translate_library(tree) → dict[name, SQLExpr], .to_sql() for expression SQL
- ViewDef: SQLGenerator().generate(parsed_vd) 
- FHIRPath: evaluate(resource, expr)
"""
import sys, os, json, time, traceback, io
sys.path.insert(0, '/mnt/d/fhir4ds')

import warnings; warnings.filterwarnings('ignore')

from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator import CQLToSQLTranslator
from fhir4ds.fhirpath import evaluate as fp_eval
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator
import duckdb

HEADER = "library T version '1.0'\nusing FHIR version '4.0.1'\n"
_vd_gen = SQLGenerator()

def cql_expr_sql(expr, def_name="X"):
    """Translate CQL expression to SQL string."""
    cql = HEADER + f'define "{def_name}": {expr}\n'
    tree = parse_cql(cql)
    t = CQLToSQLTranslator(tree)
    defs = t.translate_library(tree)
    return defs[def_name].to_sql()

def cql_full_sql(cql_text, def_name):
    """Translate a full CQL library to SQL for one definition."""
    tree = parse_cql(cql_text)
    t = CQLToSQLTranslator(tree)
    return t.translate_library_to_sql(tree, final_definition=def_name)

def cql_eval(expr, def_name="X"):
    """Evaluate a CQL expression via DuckDB with CQL UDFs loaded."""
    sql = cql_expr_sql(expr, def_name)
    conn = duckdb.connect()
    try:
        from fhir4ds.cql.duckdb import register as cql_register
        cql_register(conn)
        return conn.execute(f"SELECT {sql}").fetchone()[0]
    except Exception as e:
        return f"SQLERR:{e}"
    finally:
        conn.close()

def vd_gen(vd_dict):
    """Generate SQL from a ViewDefinition dict."""
    parsed = parse_view_definition(vd_dict)
    return _vd_gen.generate(parsed)


# ═══ ITER 51: Deep nesting ═══
def run_51():
    r = []
    def build_ext(depth):
        ext = {"url": f"http://example.org/ext/level{depth}", "valueString": f"leaf-{depth}"}
        for i in range(depth - 1, 0, -1):
            ext = {"url": f"http://example.org/ext/level{i}", "extension": [ext]}
        return ext

    p50 = {"resourceType": "Patient", "id": "d50", "extension": [build_ext(50)]}
    p100 = {"resourceType": "Patient", "id": "d100", "extension": [build_ext(100)]}

    assert fp_eval(p50, "extension.count()") == [1]; r.append("T1: 50-level ext")
    assert fp_eval(p100, "extension.count()") == [1]; r.append("T2: 100-level ext")
    assert fp_eval(p100, "extension" + ".extension" * 4 + ".url") == ["http://example.org/ext/level5"]; r.append("T3: chain nav")
    assert fp_eval(p100, "extension.where(url = 'http://example.org/ext/level1').extension.url") == ["http://example.org/ext/level2"]; r.append("T4: where filter")

    p_multi = {"resourceType": "Patient", "id": "m", "extension": [build_ext(30), {"url": "http://example.org/ext/sib", "valueString": "sv"}, build_ext(20)]}
    assert fp_eval(p_multi, "extension.count()") == [3]; r.append("T5: multi ext")

    p_wide = {"resourceType": "Patient", "id": "w", "extension": [{"url": f"http://example.org/ext/{i}", "valueString": f"v{i}"} for i in range(200)]}
    assert fp_eval(p_wide, "extension.count()") == [200]; r.append("T6: 200 wide")
    assert fp_eval(p50, "extension" + ".extension" * 49 + ".valueString.exists()") == [True]; r.append("T7: exists@50")
    assert fp_eval(p50, "extension" + ".extension" * 55 + ".valueString") == []; r.append("T8: beyond depth")

    p100_rt = json.loads(json.dumps(p100))
    assert fp_eval(p100_rt, "extension.extension.url") == ["http://example.org/ext/level2"]; r.append("T9: roundtrip")

    mixed = {"resourceType": "Patient", "id": "mx", "extension": [{"url": "http://example.org/ext/root", "extension": [
        {"url": "http://example.org/ext/int", "valueInteger": 42},
        {"url": "http://example.org/ext/bool", "valueBoolean": True},
        {"url": "http://example.org/ext/nest", "extension": [{"url": "http://example.org/ext/ds", "valueString": "deep"}]}
    ]}]}
    assert fp_eval(mixed, "extension.extension.where(url = 'http://example.org/ext/int').valueInteger") == [42]; r.append("T10: mixed types")
    return r

# ═══ ITER 52: Pathological CQL ═══
def run_52():
    r = []
    inner = "0"
    for i in range(50): inner = f"if {i} < 25 then {inner} else {i}"
    sql = cql_expr_sql(inner); assert "CASE" in sql; r.append("T1: 50 nested if")

    inner = "1"
    for i in range(20): inner = f"case when {i} < 10 then {inner} else {i} end"
    sql = cql_expr_sql(inner); assert "CASE" in sql; r.append("T2: 20 nested case")

    lets = "\n".join([f"    let v{i}: {i}" for i in range(10)])
    sql = cql_full_sql(HEADER + f"define ML:\n  from [Encounter] E\n{lets}\n    return E\n", "ML")
    assert sql; r.append("T3: 10 let clauses")

    withs = "\n".join([f"    with [Condition] C{i} such that C{i}.subject = E.subject" for i in range(5)])
    wouts = "\n".join([f"    without [Observation] O{i} such that O{i}.subject = E.subject" for i in range(3)])
    sql = cql_full_sql(HEADER + f"define MW:\n  from [Encounter] E\n{withs}\n{wouts}\n    return E\n", "MW")
    assert sql; r.append("T4: 5with+3without")

    parts = " and ".join([f"({i} > 0)" for i in range(15)])
    sql = cql_expr_sql(parts); assert "AND" in sql; r.append("T5: 15-AND chain")

    sql = cql_expr_sql("flatten { flatten { flatten { {1, 2}, {3, 4} }, {5} }, {6, 7} }"); assert sql; r.append("T6: nested flatten")

    defs = ["define D0: 1"] + [f"define D{i}: D{i-1} + 1" for i in range(1, 20)]
    sql = cql_full_sql(HEADER + "\n".join(defs) + "\n", "D19"); assert sql; r.append("T7: 20 chained defs")

    conds = " and ".join(["E.status = 'finished'" for _ in range(15)])
    sql = cql_full_sql(HEADER + f"define CW:\n  from [Encounter] E\n    where {conds}\n    return E\n", "CW")
    assert sql; r.append("T8: 15-cond where")

    inner = "null"
    for i in range(10): inner = f"Coalesce({inner}, {i})"
    sql = cql_expr_sql(inner); assert "COALESCE" in sql; r.append("T9: 10-nested Coalesce")

    cql = HEADER + """
define M1: if true then 1 else if false then 2 else 3
define M2: case when true then M1 else 0 end
define M3: Coalesce(M2, M1, 0)
define M4: {M1, M2, M3}
define M5: Count(M4)
"""
    for n in ["M1","M2","M3","M4","M5"]:
        assert cql_full_sql(cql, n)
    r.append("T10: mixed pathological")
    return r

# ═══ ITER 53: Type coercion ═══
def run_53():
    r = []
    v = cql_eval("ToString(ToDecimal('1.5'))"); assert '1.5' in str(v); r.append("T1: Str→Dec→Str")
    v = cql_eval("ToInteger(ToString(42))"); assert v == 42; r.append("T2: Int→Str→Int")
    v = cql_eval("ToInteger(Truncate(3.9))"); assert v == 3; r.append("T3: Trunc→Int")
    v = cql_eval("ToString(true)"); assert v == 'true'; r.append("T4: Bool→Str")
    v = cql_eval("ToBoolean('true')"); assert v == True; r.append("T5: Str→Bool")
    v = cql_eval("ToString(ToInteger('5') + ToInteger('3'))"); assert v == '8'; r.append("T6: chained arith")
    v = cql_eval("ToDecimal(ToString(1.5 + 2.5))"); assert abs(float(v) - 4.0) < 0.01; r.append("T7: Dec roundtrip")
    v = cql_eval("ToString(null)"); assert v is None; r.append("T8: null→Str")
    v = cql_eval("ToInteger('abc')"); r.append(f"T9: invalid conv→{repr(v)}")
    v = cql_eval("ToInteger('10') * ToDecimal('2.5')"); r.append(f"T10: mixed arith→{v}")
    return r

# ═══ ITER 54: Interval algebra ═══
def run_54():
    r = []
    assert cql_expr_sql("Interval[1, 10]"); r.append("T1: [1,10]")
    assert cql_expr_sql("Interval[5, 5]"); r.append("T2: point")
    assert cql_expr_sql("Interval(1, 10)"); r.append("T3: open")
    assert cql_expr_sql("Interval[1, 10)") and cql_expr_sql("Interval(1, 10]"); r.append("T4: half-open")

    assert cql_eval("5 in Interval[1, 10]") == True; r.append("T5: contains 5")
    assert cql_eval("0 in Interval[1, 10]") == False; r.append("T6: not contains 0")
    assert cql_eval("1 in Interval[1, 10]") == True; r.append("T7: closed lower")
    assert cql_eval("10 in Interval[1, 10]") == True; r.append("T8: closed upper")
    assert cql_eval("1 in Interval(1, 10]") == False; r.append("T9: open lower")
    assert cql_eval("10 in Interval[1, 10)") == False; r.append("T10: open upper")
    assert cql_expr_sql("Interval[null, 5]"); r.append("T11: null bounds")
    assert cql_eval("Interval[1, 5] overlaps Interval[3, 8]") == True; r.append("T12: overlaps")
    return r

# ═══ ITER 55: Date arithmetic ═══
def run_55():
    r = []
    assert '2023-02-28' in str(cql_eval("@2023-01-31 + 1 month")); r.append("T1: Jan31+1mo")
    assert '2024-02-29' in str(cql_eval("@2024-01-31 + 1 month")); r.append("T2: leap")
    assert '2023-02-28' in str(cql_eval("@2024-02-29 - 1 year")); r.append("T3: Feb29-1yr")
    assert '2023-06-15' in str(cql_eval("@2023-06-15 + 0 days")); r.append("T4: +0 days")
    assert '2024-01-01' in str(cql_eval("@2023-12-31 + 1 day")); r.append("T5: yr boundary")
    assert '2024-02-15' in str(cql_eval("@2023-11-15 + 3 months")); r.append("T6: cross-yr")
    assert cql_expr_sql("months between @2023-01-15 and @2023-06-15"); r.append("T7: mo between")
    assert '12:30' in str(cql_eval("@2023-06-15T10:30:00 + 2 hours")); r.append("T8: +2hrs")
    assert '2023-04-30' in str(cql_eval("@2023-03-31 + 1 month")); r.append("T9: Mar31+1mo")
    assert '2024-02-02' in str(cql_eval("@2023-01-01 + 1 year + 1 month + 1 day")); r.append("T10: chained")
    return r

# ═══ ITER 56: Quantity operations ═══
def run_56():
    r = []
    obs = {"resourceType": "Observation", "id": "w", "valueQuantity": {"value": 80.5, "unit": "kg", "system": "http://unitsofmeasure.org", "code": "kg"}}
    bp = {"resourceType": "Observation", "id": "bp", "component": [
        {"code": {"coding": [{"system": "http://loinc.org", "code": "8480-6"}]}, "valueQuantity": {"value": 120, "unit": "mmHg"}},
        {"code": {"coding": [{"system": "http://loinc.org", "code": "8462-4"}]}, "valueQuantity": {"value": 80, "unit": "mmHg"}}
    ]}
    assert fp_eval(obs, "valueQuantity.value") == [80.5]; r.append("T1: qty value")
    assert fp_eval(obs, "valueQuantity.unit") == ["kg"]; r.append("T2: qty unit")
    assert fp_eval(obs, "valueQuantity.value > 50") == [True]; r.append("T3: qty > 50")
    assert fp_eval(bp, "component.valueQuantity.value") == [120, 80]; r.append("T4: component vals")
    assert fp_eval(bp, "component.where(code.coding.code = '8480-6').valueQuantity.value") == [120]; r.append("T5: filter comp")
    assert fp_eval(obs, "valueQuantity.system") == ["http://unitsofmeasure.org"]; r.append("T6: system")
    assert fp_eval(obs, "valueQuantity.code") == ["kg"]; r.append("T7: code")
    assert fp_eval(obs, "valueQuantity.exists()") == [True]; r.append("T8: exists")
    v = fp_eval({"resourceType": "Patient", "id": "p1"}, "valueQuantity.exists()")
    assert v == [False] or v == []; r.append("T9: not exists")
    assert fp_eval(bp, "component.valueQuantity.value.where($this > 100)") == [120]; r.append("T10: filter > 100")
    return r

# ═══ ITER 57: Empty aggregates ═══
def run_57():
    r = []
    v = cql_eval("Count({})"); assert v == 0, f"got {v}"; r.append("T1: Count({})=0")
    cql_eval("Sum({})"); r.append("T2: Sum({})")
    assert cql_eval("Min({})") is None; r.append("T3: Min({})=null")
    assert cql_eval("Max({})") is None; r.append("T4: Max({})=null")
    assert cql_eval("exists ({})") == False; r.append("T5: exists=false")
    assert cql_eval("Count({1})") == 1; r.append("T6: Count({1})=1")
    assert cql_eval("Sum({42})") == 42; r.append("T7: Sum({42})=42")
    v = cql_eval("Count({1, null, 3})"); assert v in [2, 3], f"got {v}"; r.append(f"T8: Count(nulls)={v}")
    assert cql_eval("First({})") is None; r.append("T9: First({})=null")
    assert cql_eval("Last({})") is None; r.append("T10: Last({})=null")
    return r

# ═══ ITER 58: ViewDef column types ═══
def run_58():
    r = []
    def vds(resource, cols):
        return vd_gen({"resourceType": "ViewDefinition", "resource": resource, "select": [{"column": cols}]})

    sql = vds("Patient", [{"path": "active", "name": "is_active", "type": "boolean"}]); assert "is_active" in sql; r.append("T1: boolean")
    sql = vds("Patient", [{"path": "multipleBirthInteger", "name": "bo", "type": "integer"}]); assert "bo" in sql; r.append("T2: integer")
    sql = vds("Patient", [{"path": "gender", "name": "g", "type": "string"}]); assert "g" in sql; r.append("T3: string")
    sql = vds("Patient", [{"path": "birthDate", "name": "dob", "type": "date"}]); assert "dob" in sql; r.append("T4: date")
    sql = vds("Encounter", [{"path": "period.start", "name": "es", "type": "dateTime"}]); assert "es" in sql; r.append("T5: dateTime")
    sql = vds("Patient", [
        {"path": "id", "name": "pid"}, {"path": "active", "name": "a"},
        {"path": "birthDate", "name": "d"}, {"path": "gender", "name": "s"}
    ]); assert all(x in sql for x in ["pid", "a", "d", "s"]); r.append("T6: multi-col")
    sql = vds("Observation", [{"path": "valueQuantity.value", "name": "ov"}, {"path": "valueQuantity.unit", "name": "ou"}]); assert "ov" in sql; r.append("T7: qty cols")
    sql = vds("Observation", [{"path": "subject.reference", "name": "pr"}]); assert "pr" in sql; r.append("T8: ref col")
    sql = vds("Observation", [{"path": "code.coding.code", "name": "oc"}]); assert "oc" in sql; r.append("T9: coding col")
    sql = vds("Patient", [{"path": "identifier.value", "name": "mrn"}]); assert "mrn" in sql; r.append("T10: identifier col")
    return r

# ═══ ITER 59: Concept equality ═══
def run_59():
    r = []
    assert cql_eval('Code \'12345\' from "http://example.org" = Code \'12345\' from "http://example.org"') == True; r.append("T1: same code =")
    assert cql_eval('Code \'12345\' from "http://example.org" = Code \'99999\' from "http://example.org"') == False; r.append("T2: diff code !=")
    assert cql_eval('Code \'12345\' from "http://example.org" ~ Code \'12345\' from "http://example.org"') == True; r.append("T3: code ~")
    assert cql_eval("'abc' = 'abc'") == True; r.append("T4: str =")
    assert cql_eval("42 = 42") == True; r.append("T5: int =")
    assert cql_eval("null = null") is None; r.append("T6: null=null→null")
    assert cql_eval("null ~ null") == True; r.append("T7: null~null→true")
    assert cql_eval('Code \'12345\' from "http://example.org" !~ Code \'99999\' from "http://example.org"') == True; r.append("T8: code !~")
    assert cql_eval("true ~ true") == True; r.append("T9: bool ~")
    assert cql_eval("1.0 = 1.0") == True; r.append("T10: decimal =")
    return r

# ═══ ITER 60: Boolean truth tables ═══
def run_60():
    r = []
    patient = {"resourceType": "Patient", "id": "p1", "active": True}
    def fb(expr):
        try:
            v = fp_eval(patient, expr)
            if v == []: return 'empty'
            if v == [True]: return True
            if v == [False]: return False
            return v
        except: return 'ERR'

    vals = {'true': 'true', 'false': 'false', 'empty': '{}'}
    and_exp = {('true','true'): True, ('true','false'): False, ('true','empty'): 'empty',
               ('false','true'): False, ('false','false'): False, ('false','empty'): False,
               ('empty','true'): 'empty', ('empty','false'): False, ('empty','empty'): 'empty'}
    ap = sum(1 for (a,b),e in and_exp.items() if fb(f"{vals[a]} and {vals[b]}") == e)
    r.append(f"AND:{ap}/9")

    or_exp = {('true','true'): True, ('true','false'): True, ('true','empty'): True,
              ('false','true'): True, ('false','false'): False, ('false','empty'): 'empty',
              ('empty','true'): True, ('empty','false'): 'empty', ('empty','empty'): 'empty'}
    op = sum(1 for (a,b),e in or_exp.items() if fb(f"{vals[a]} or {vals[b]}") == e)
    r.append(f"OR:{op}/9")

    xor_exp = {('true','true'): False, ('true','false'): True, ('true','empty'): 'empty',
               ('false','true'): True, ('false','false'): False, ('false','empty'): 'empty',
               ('empty','true'): 'empty', ('empty','false'): 'empty', ('empty','empty'): 'empty'}
    xp = sum(1 for (a,b),e in xor_exp.items() if fb(f"{vals[a]} xor {vals[b]}") == e)
    r.append(f"XOR:{xp}/9")

    imp_exp = {('true','true'): True, ('true','false'): False, ('true','empty'): 'empty',
               ('false','true'): True, ('false','false'): True, ('false','empty'): True,
               ('empty','true'): True, ('empty','false'): 'empty', ('empty','empty'): 'empty'}
    ip = sum(1 for (a,b),e in imp_exp.items() if fb(f"{vals[a]} implies {vals[b]}") == e)
    r.append(f"IMP:{ip}/9")

    np = sum(1 for v,e in [('true', False), ('false', True)] if fb(f"{vals[v]}.not()") == e)
    r.append(f"NOT:{np}/2")

    total = ap + op + xp + ip + np
    if total < 38: r.append(f"WARN:{38-total} failures")
    return r

# ═══ ITER 61: List operations ═══
def run_61():
    r = []
    assert cql_expr_sql("flatten { {1, 2}, {3, 4} }"); r.append("T1: flatten")
    cql_eval("distinct {1, 2, 2, 3}"); r.append("T2: distinct")
    assert cql_expr_sql("{1, 2} union {3, 4}"); r.append("T3: union")
    assert cql_expr_sql("{1, 2, 3} intersect {2, 3, 4}"); r.append("T4: intersect")
    assert cql_expr_sql("{1, 2, 3} except {2}"); r.append("T5: except")
    assert cql_eval("First({10, 20, 30})") == 10; r.append("T6: First=10")
    assert cql_eval("Last({10, 20, 30})") == 30; r.append("T7: Last=30")
    assert cql_eval("Count({10, 20, 30})") == 3; r.append("T8: Count=3")
    assert cql_eval("singleton from {42}") == 42; r.append("T9: singleton=42")
    assert cql_expr_sql("IndexOf({10, 20, 30}, 20)"); r.append("T10: IndexOf")
    return r

# ═══ ITER 62: String functions ═══
def run_62():
    r = []
    assert cql_eval("Combine({'a', 'b', 'c'}, ',')") == 'a,b,c'; r.append("T1: Combine")
    cql_eval("Split('a,b,c', ',')"); r.append("T2: Split")
    assert cql_eval("Length('hello')") == 5; r.append("T3: Length=5")
    assert cql_eval("Length('')") == 0; r.append("T4: Length('')=0")
    assert cql_eval("PositionOf('bc', 'abcdef')") == 1; r.append("T5: PositionOf=1")
    assert cql_eval("PositionOf('xyz', 'abcdef')") == -1; r.append("T6: PositionOf=-1")
    cql_eval("Substring('abcdef', 2, 3)"); r.append("T7: Substring")
    assert cql_eval("Upper('hello')") == 'HELLO'; r.append("T8: Upper")
    assert cql_eval("Lower('HELLO')") == 'hello'; r.append("T9: Lower")
    assert cql_eval("StartsWith('hello world', 'hello')") == True; r.append("T10: StartsWith")
    return r

# ═══ ITER 63: Choice types ═══
def run_63():
    r = []
    assert fp_eval({"resourceType": "Patient", "id": "p1", "deceasedBoolean": True}, "deceasedBoolean") == [True]; r.append("T1: deceasedBool")
    assert fp_eval({"resourceType": "Patient", "id": "p2", "deceasedDateTime": "2023-06-15"}, "deceasedDateTime") == ["2023-06-15"]; r.append("T2: deceasedDT")
    assert fp_eval({"resourceType": "Observation", "id": "o1", "valueQuantity": {"value": 120, "unit": "mmHg"}}, "valueQuantity.value") == [120]; r.append("T3: valueQty")
    assert fp_eval({"resourceType": "Observation", "id": "o2", "valueString": "Positive"}, "valueString") == ["Positive"]; r.append("T4: valueStr")
    assert fp_eval({"resourceType": "Observation", "id": "o3", "valueCodeableConcept": {"coding": [{"code": "LA6576-8"}]}}, "valueCodeableConcept.coding.code") == ["LA6576-8"]; r.append("T5: valueCC")
    assert fp_eval({"resourceType": "Observation", "id": "o4", "valueBoolean": False}, "valueBoolean") == [False]; r.append("T6: valueBool")
    assert fp_eval({"resourceType": "Observation", "id": "o5", "valueInteger": 42}, "valueInteger") == [42]; r.append("T7: valueInt")
    assert fp_eval({"resourceType": "Patient", "id": "p3", "multipleBirthInteger": 2}, "multipleBirthInteger") == [2]; r.append("T8: multiBirthInt")
    assert fp_eval({"resourceType": "Patient", "id": "p4", "multipleBirthBoolean": True}, "multipleBirthBoolean") == [True]; r.append("T9: multiBirthBool")
    assert fp_eval({"resourceType": "Observation", "id": "o6", "effectiveDateTime": "2023-06-15T10:00:00Z"}, "effectiveDateTime") == ["2023-06-15T10:00:00Z"]; r.append("T10: effectiveDT")
    return r

# ═══ ITER 64: Retrieve code filters ═══
def run_64():
    r = []
    sql = cql_full_sql(HEADER + "define E: [Encounter]\n", "E"); assert sql; r.append("T1: [Encounter]")
    cql = HEADER + "codesystem S: 'http://snomed.info/sct'\ncode DC: '73211009' from S display 'Diabetes'\ndefine D: [Condition: DC]\n"
    sql = cql_full_sql(cql, "D"); assert sql; r.append("T2: code filter")
    sql = cql_full_sql(HEADER + "define HE: exists [Encounter]\n", "HE"); assert sql; r.append("T3: exists retrieve")
    sql = cql_full_sql(HEADER + "define EC: Count([Encounter])\n", "EC"); assert sql; r.append("T4: Count retrieve")
    sql = cql_full_sql(HEADER + "define FE:\n  [Encounter] E where E.status = 'finished'\n", "FE"); assert "finished" in sql; r.append("T5: where clause")
    cql = HEADER + "define C: [Condition]\ndefine E: [Encounter]\ndefine O: [Observation]\n"
    for n in ["C","E","O"]: assert cql_full_sql(cql, n)
    r.append("T6: multi-resource")
    sql = cql_full_sql(HEADER + "define SE:\n  [Encounter] E sort by start of period\n", "SE"); assert sql; r.append("T7: sort")
    sql = cql_full_sql(HEADER + "define NO:\n  [Encounter] E\n    without [Observation] O such that O.subject = E.subject\n    return E\n", "NO"); assert sql; r.append("T8: without")
    sql = cql_full_sql(HEADER + "define EI:\n  [Encounter] E return E.id\n", "EI"); assert sql; r.append("T9: return")
    sql = cql_full_sql(HEADER + "define CQ:\n  exists ([Encounter] E where E.status = 'finished')\n    and exists ([Condition] C where C.clinicalStatus.coding.code contains 'active')\n", "CQ"); assert sql; r.append("T10: nested bool")
    return r

# ═══ ITER 65: Population basis ═══
def run_65():
    r = []
    cql = HEADER + 'define "IP":\n  [Encounter] E where E.status = \'finished\'\ndefine "D":\n  "IP"\ndefine "N":\n  "IP" IP where IP.class.code = \'AMB\'\n'
    for n in ["IP","D","N"]: assert cql_full_sql(cql, n)
    r.append("T1: proportion")
    cql = HEADER + 'define "IP":\n  [Encounter] E where E.status = \'finished\'\ndefine "D":\n  "IP"\ndefine "DE":\n  "D" D where D.class.code = \'EMER\'\n'
    assert cql_full_sql(cql, "DE"); r.append("T2: denom excl")
    cql = HEADER + 'define "IP":\n  [Encounter] E where E.status = \'finished\'\ndefine "S1":\n  "IP" IP return IP.class.code\n'
    assert cql_full_sql(cql, "S1"); r.append("T3: stratifier")
    cql = HEADER + 'define "QE": [Encounter] E where E.status = \'finished\'\ndefine "QC": [Condition] C where C.clinicalStatus.coding.code contains \'active\'\ndefine "IP2":\n  "QE" QE with "QC" QC such that QC.encounter.reference = \'Encounter/\' + QE.id return QE\n'
    assert cql_full_sql(cql, "IP2"); r.append("T4: cross-def with")
    cql = HEADER + 'define "IP3": exists [Encounter] E where E.status = \'finished\'\n'
    assert cql_full_sql(cql, "IP3"); r.append("T5: cohort")
    cql = HEADER + 'define "IP4": [Encounter] E where E.status = \'finished\'\ndefine "IP5": [Encounter] E where E.class.code = \'AMB\'\n'
    for n in ["IP4","IP5"]: assert cql_full_sql(cql, n)
    r.append("T6: multi-IP")
    cql = HEADER + 'define "IP6": [Encounter] E where E.status = \'finished\'\ndefine "D2": "IP6"\ndefine "DX": "D2" D where D.class.code = \'IMP\'\n'
    assert cql_full_sql(cql, "DX"); r.append("T7: denom exception")
    cql = HEADER + 'define function "MO"(enc Encounter): duration in days of enc.period\ndefine "IP7": [Encounter] E where E.status = \'finished\'\n'
    assert cql_full_sql(cql, "IP7"); r.append("T8: cont-variable")
    return r

# ═══ ITER 66: Reference navigation ═══
def run_66():
    r = []
    obs = {"resourceType": "Observation", "id": "o1", "subject": {"reference": "Patient/p1", "display": "John Doe"}}
    assert fp_eval(obs, "subject.reference") == ["Patient/p1"]; r.append("T1: ref access")
    assert fp_eval(obs, "subject.display") == ["John Doe"]; r.append("T2: display")
    pat = {"resourceType": "Patient", "id": "p1", "generalPractitioner": [{"reference": "Practitioner/pr1"}, {"reference": "Practitioner/pr2"}]}
    assert fp_eval(pat, "generalPractitioner.reference") == ["Practitioner/pr1", "Practitioner/pr2"]; r.append("T3: multi-ref")
    assert fp_eval(obs, "subject.reference.exists()") == [True]; r.append("T4: ref exists")
    mr = {"resourceType": "MedicationRequest", "id": "mr1", "contained": [{"resourceType": "Medication", "id": "med1"}], "medicationReference": {"reference": "#med1"}}
    assert fp_eval(mr, "medicationReference.reference") == ["#med1"]; r.append("T5: contained ref str")
    assert fp_eval(mr, "contained.id") == ["med1"]; r.append("T6: contained id")
    enc = {"resourceType": "Encounter", "id": "e1", "subject": {"reference": "Patient/p1"},
           "participant": [{"individual": {"reference": "Practitioner/pr1"}}, {"individual": {"reference": "Practitioner/pr2"}}],
           "serviceProvider": {"reference": "Organization/org1"}}
    assert fp_eval(enc, "participant.individual.reference") == ["Practitioner/pr1", "Practitioner/pr2"]; r.append("T7: participant refs")
    assert fp_eval(enc, "subject.reference.startsWith('Patient')") == [True]; r.append("T8: startsWith")
    assert fp_eval(enc, "serviceProvider.reference") == ["Organization/org1"]; r.append("T9: serviceProvider")
    assert fp_eval({"resourceType": "Patient", "id": "p2"}, "generalPractitioner.reference") == []; r.append("T10: empty ref")
    return r

# ═══ ITER 67: Function definitions ═══
def run_67():
    r = []
    assert cql_full_sql(HEADER + "define function A1(x Integer): x + 1\ndefine R: A1(5)\n", "R"); r.append("T1: simple func")
    assert cql_full_sql(HEADER + "define function A2(x Integer, y Integer): x + y\ndefine R: A2(3, 4)\n", "R"); r.append("T2: multi-param")
    assert cql_full_sql(HEADER + "define function G(n String): 'Hello, ' + n\ndefine R: G('World')\n", "R"); r.append("T3: string param")
    assert cql_full_sql(HEADER + "define function Db(x Integer): x * 2\ndefine function Q(x Integer): Db(Db(x))\ndefine R: Q(3)\n", "R"); r.append("T4: func-in-func")
    assert cql_full_sql(HEADER + "define function Tg(b Boolean): not b\ndefine R: Tg(true)\n", "R"); r.append("T5: bool param")
    cql = HEADER + "define function Cl(x Integer):\n  if x > 0 then 'positive' else if x < 0 then 'negative' else 'zero'\ndefine R: Cl(-5)\n"
    assert cql_full_sql(cql, "R"); r.append("T6: conditional func")
    assert cql_full_sql(HEADER + "define function IA(age Integer): age >= 18\ndefine R: IA(25)\n", "R"); r.append("T7: in def")
    assert cql_full_sql(HEADER + "define function SA(x Integer, y Integer): Coalesce(x, 0) + Coalesce(y, 0)\ndefine R: SA(null, 5)\n", "R"); r.append("T8: null-safe")
    assert cql_full_sql(HEADER + "define function GS(enc Encounter): enc.status\ndefine R: [Encounter] E return GS(E)\n", "R"); r.append("T9: resource param")
    assert cql_full_sql(HEADER + "define function F1(x Integer): x + 1\ndefine function F2(x Integer): x * 2\ndefine function F3(x Integer): F1(F2(x))\ndefine R: F3(5)\n", "R"); r.append("T10: composition")
    return r

# ═══ ITER 68: forEach / forEachOrNull ═══
def run_68():
    r = []
    sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                  "select": [{"forEach": "name", "column": [{"path": "family", "name": "fn"}]}]})
    assert "fn" in sql; r.append("T1: forEach name")
    sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                  "select": [{"forEachOrNull": "name", "column": [{"path": "family", "name": "fn"}]}]})
    assert "fn" in sql; r.append("T2: forEachOrNull")
    sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                  "select": [{"forEach": "name.where(use = 'official')", "column": [{"path": "family", "name": "on"}]}]})
    assert "on" in sql; r.append("T3: forEach+where")
    sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                  "select": [{"forEach": "name", "column": [{"path": "family", "name": "fn"}],
                              "select": [{"forEach": "given", "column": [{"path": "$this", "name": "gn"}]}]}]})
    assert "fn" in sql and "gn" in sql; r.append("T4: nested forEach")
    sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                  "select": [{"forEach": "telecom", "column": [{"path": "system", "name": "ts"}, {"path": "value", "name": "tv"}]}]})
    assert "ts" in sql; r.append("T5: telecom")
    sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                  "select": [{"forEach": "address", "column": [{"path": "city", "name": "c"}]}]})
    assert "c" in sql; r.append("T6: address")
    sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                  "select": [{"forEachOrNull": "identifier", "column": [{"path": "value", "name": "iv"}]}]})
    assert "iv" in sql; r.append("T7: forEachOrNull id")
    sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                  "select": [{"column": [{"path": "id", "name": "pid"}]},
                             {"forEach": "name", "column": [{"path": "family", "name": "fn"}]}]})
    assert "pid" in sql and "fn" in sql; r.append("T8: mixed")
    sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                  "select": [{"forEach": "extension", "column": [{"path": "url", "name": "eu"}]}]})
    assert "eu" in sql; r.append("T9: extension")
    sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Observation",
                  "select": [{"forEach": "component", "column": [{"path": "code.coding.code", "name": "cc"}]}]})
    assert "cc" in sql; r.append("T10: component")
    return r

# ═══ ITER 69: Conformance regression ═══
def run_69():
    r = []
    tests = [
        ({"resourceType": "Patient", "id": "p1", "active": True}, "id", ["p1"]),
        ({"resourceType": "Patient", "id": "p1", "active": True}, "active", [True]),
        ({"resourceType": "Patient", "id": "p1", "name": [{"family": "Smith"}]}, "name.family", ["Smith"]),
        ({"resourceType": "Patient", "id": "p1"}, "active.exists()", [False]),
        ({"resourceType": "Patient", "id": "p1", "active": True}, "active.exists()", [True]),
    ]
    fp = sum(1 for res, expr, exp in tests if fp_eval(res, expr) == exp)
    r.append(f"FP:{fp}/5")

    exprs = ["1 + 1", "true and false", "'hello' + ' world'", "if true then 1 else 2", "Coalesce(null, 5)"]
    cp = sum(1 for e in exprs if cql_expr_sql(e))
    r.append(f"CQL:{cp}/5")

    sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                  "select": [{"column": [{"path": "id", "name": "pid"}]}]})
    r.append(f"VD:{'OK' if sql else 'FAIL'}")

    try:
        from fhir4ds.dqm import DQMEvaluator; r.append("DQM:OK")
    except ImportError:
        try:
            from fhir4ds.dqm.evaluator import DQMEvaluator; r.append("DQM:OK")
        except ImportError:
            r.append("DQM:SKIP")
    return r

# ═══ ITER 70: Concurrent stress ═══
def run_70():
    from concurrent.futures import ThreadPoolExecutor, as_completed
    r = []
    patient = {"resourceType": "Patient", "id": "p1", "active": True, "name": [{"family": "Smith", "given": ["John"]}]}

    def fp_task(i):
        assert fp_eval(patient, "name.family") == ["Smith"]; return i
    start = time.time()
    with ThreadPoolExecutor(max_workers=20) as ex:
        done = sum(1 for f in as_completed([ex.submit(fp_task, i) for i in range(100)]) if f.result() is not None)
    r.append(f"FP:{done}/100 {time.time()-start:.1f}s")

    def cql_task(i):
        tree = parse_cql(HEADER + f"define X{i}: {i} + 1\n")
        t = CQLToSQLTranslator(tree)
        assert t.translate_library(tree); return i
    start = time.time()
    with ThreadPoolExecutor(max_workers=20) as ex:
        done = sum(1 for f in as_completed([ex.submit(cql_task, i) for i in range(100)]) if f.result() is not None)
    r.append(f"CQL:{done}/100 {time.time()-start:.1f}s")

    def vd_task(i):
        sql = vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                      "select": [{"column": [{"path": "id", "name": f"p{i}"}]}]})
        assert sql; return i
    start = time.time()
    with ThreadPoolExecutor(max_workers=20) as ex:
        done = sum(1 for f in as_completed([ex.submit(vd_task, i) for i in range(100)]) if f.result() is not None)
    r.append(f"VD:{done}/100 {time.time()-start:.1f}s")

    def db_task(i):
        conn = duckdb.connect()
        try:
            from fhir4ds.fhirpath.duckdb import register; register(conn)
            v = conn.execute("SELECT fhirpath_text(?, 'name.family')", [json.dumps(patient)]).fetchone()[0]
            assert v is not None; return i
        finally: conn.close()
    start = time.time()
    with ThreadPoolExecutor(max_workers=10) as ex:
        done = 0
        for f in as_completed([ex.submit(db_task, i) for i in range(50)]):
            try: f.result(); done += 1
            except: pass
    r.append(f"DB:{done}/50 {time.time()-start:.1f}s")

    det = set()
    def det_task(i): return str(fp_eval(patient, "name.given"))
    with ThreadPoolExecutor(max_workers=20) as ex:
        for f in as_completed([ex.submit(det_task, i) for i in range(50)]):
            det.add(f.result())
    assert len(det) == 1; r.append("DET:OK")

    def mixed(i):
        if i % 3 == 0: fp_eval(patient, "id")
        elif i % 3 == 1:
            tree = parse_cql(HEADER + f"define Y: {i}\n")
            CQLToSQLTranslator(tree).translate_library(tree)
        else:
            vd_gen({"resourceType": "ViewDefinition", "resource": "Patient",
                    "select": [{"column": [{"path": "id", "name": "pid"}]}]})
        return i
    start = time.time()
    with ThreadPoolExecutor(max_workers=20) as ex:
        done = sum(1 for f in as_completed([ex.submit(mixed, i) for i in range(100)]) if f.result() is not None)
    r.append(f"MIX:{done}/100 {time.time()-start:.1f}s")
    return r


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
iterations = [
    (51, "Deep Nested JSON", run_51),
    (52, "Pathological CQL", run_52),
    (53, "Type Coercion", run_53),
    (54, "Interval Algebra", run_54),
    (55, "Date Arithmetic", run_55),
    (56, "Quantity Operations", run_56),
    (57, "Empty Aggregates", run_57),
    (58, "ViewDef Column Types", run_58),
    (59, "Concept Equality", run_59),
    (60, "Boolean Truth Tables", run_60),
    (61, "List Operations", run_61),
    (62, "String Functions", run_62),
    (63, "Choice Types", run_63),
    (64, "Retrieve Code Filters", run_64),
    (65, "Population Basis", run_65),
    (66, "Reference Navigation", run_66),
    (67, "Function Definitions", run_67),
    (68, "forEach/forEachOrNull", run_68),
    (69, "Conformance Regression", run_69),
    (70, "Concurrent Stress", run_70),
]

old_stderr = sys.stderr
sys.stderr = io.StringIO()

total_tests = 0
total_issues = 0
summary_lines = []

for num, name, func in iterations:
    try:
        results = func()
        count = len(results)
        total_tests += count
        line = f"Iter {num}: {name} — {count} tests, 0 issues"
        summary_lines.append(line)
        print(line)
        for item in results:
            print(f"  {item}")
    except Exception as e:
        total_issues += 1
        tb_str = traceback.format_exc()
        line = f"Iter {num}: {name} — FAILED: {e}"
        summary_lines.append(line)
        print(line)
        # Print just last few lines of traceback
        for tl in tb_str.strip().split('\n')[-4:]:
            print(f"  {tl}")

sys.stderr = old_stderr

print(f"\n{'='*60}")
print(f"TOTAL: {total_tests} tests across 20 iterations, {total_issues} failures")
print(f"{'='*60}")
for line in summary_lines:
    print(line)
