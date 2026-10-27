let S=null,b=null;async function q(e){S||(b||(b=(async()=>{const{createDuckDBConnection:t}=await import("./duckdb-wasm-CM5iA_Z5.js"),{conn:o}=await t(e);S={conn:o}})().catch(t=>{throw b=null,t})),await b)}async function _(e){return await q(),S.conn.query(e)}function m(e,t){if(e==null)return null;const o=typeof e;if(o==="bigint"){if(t!==void 0&&t>0)return Number(e)/Math.pow(10,t);const r=Number(e);return Number.isSafeInteger(r)?r:e.toString()}if(o==="number"||o==="boolean"||o==="string")return e;if(Array.isArray(e))return e.map(r=>m(r));if(o==="object"){if(typeof e.toArray=="function")return m(e.toArray());const r=String(e);if(/^-?\d+(?:\.\d+)?$/.test(r)){const n=Number(r);return t!==void 0&&t>0?n/Math.pow(10,t):n}const c={};for(const[n,i]of Object.entries(e))typeof i!="function"&&(c[n]=m(i));return c}return String(e)}async function j(e,t,o=[],r,c){var d,f;await q();const n=["CREATE OR REPLACE TEMP TABLE __vd_src (resource JSON)"];if(t.length===0)n.push("INSERT INTO __vd_src SELECT NULL WHERE false");else for(let p=0;p<t.length;p+=150){const h=t.slice(p,p+150).map(v=>`('${JSON.stringify(v).replace(/'/g,"''")}')`).join(", ");n.push(`INSERT INTO __vd_src VALUES ${h}`)}const i={schema:1,ok:!0};try{for(const a of n)await _(a);for(const a of o)await _(a);if(r){const a=await r();for(const u of a)await _(u)}let l=e;if(c){const a=await _(`SELECT * FROM (
${e}
) LIMIT 0`);l=await c(a.schema.fields.map(u=>u.name))}const p=await _(l),h=p.schema.fields.map(a=>a.name),v={};for(const a of p.schema.fields)v[a.name]=((d=a.type)==null?void 0:d.typeId)===7?a.scale??((f=a.type)==null?void 0:f.scale):void 0;const O=(await p.toArray()).map(a=>{const u={};for(const g of h)u[g]=m(a[g]===void 0?null:a[g],v[g]);return u});i.sql=l,i.columns=h,i.rows=JSON.parse(JSON.stringify(O))}catch(l){i.ok=!1,i.diagnostics=[{code:"evaluation_error",severity:"error",message:String(l instanceof Error?l.message:l)}]}return i}var T=Object.freeze({__proto__:null,initDuckDB:q,jsonSafe:m,runRaw:_,stageAndRunFlat:j});const k="https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";let s=null,E=!1;const w=[];function P(){E=!0;for(const e of w)e();w.length=0}async function y(){E||await new Promise(e=>w.push(e))}self.onmessage=async e=>{const t=e.data;try{const o=await A(t);self.postMessage(o)}catch(o){self.postMessage({id:t.id,type:t.type,ok:!1,error:o instanceof Error?o.message:String(o)})}};async function A(e){var c;if(e.type==="boot")return D();if(await y(),((c=e.view_definition)==null?void 0:c.resourceType)==="Library"){const n=await R(e.view_definition,e.setup_sql??[]);if(!n.ok)return{id:e.id,type:e.type,ok:!0,envelope:JSON.stringify({schema:1,ok:!1,diagnostics:n.diagnostics})};const i=!(n.setup_sql&&n.setup_sql.length),d=e.omop_table?l=>N(e.omop_table,n.sql,l):void 0,f=i&&/\bomop\./i.test(n.sql??"")?await j(n.sql,e.resources,[],L,d):await j(n.sql,e.resources,n.setup_sql,void 0,d);return{id:e.id,type:e.type,ok:!0,envelope:JSON.stringify(f)}}const t=await C(e.view_definition);if(!t.ok)return{id:e.id,type:e.type,ok:!0,envelope:JSON.stringify({schema:1,ok:!1,diagnostics:t.diagnostics})};const o=e.omop_table?n=>N(e.omop_table,t.sql,n):void 0,r=await j(t.sql,e.resources,t.setup_sql,void 0,o);return{id:e.id,type:e.type,ok:!0,envelope:JSON.stringify(r)}}async function N(e,t,o){return await y(),s.globals.set("__omop_table",e),s.globals.set("__omop_inner",t),s.globals.set("__omop_cols",JSON.stringify(o)),s.runPython(`
import json
from fhir4ds.viewdef.omop_runner import omop_key_projection_sql
omop_key_projection_sql(__omop_table, __omop_inner, json.loads(__omop_cols))
`)}async function R(e,t){await y(),s.globals.set("__lib_json",JSON.stringify(e)),s.globals.set("__setup_json",JSON.stringify(t));const o=s.runPython(`
import json
from pathlib import Path
import fhir4ds.viewdef as _v

try:
    from fhir4ds.sqlquery.parser import parse_library
    lib = parse_library(json.loads(__lib_json))
    contents = [c for c in lib.content if c.content_type.startswith("application/sql")]
    if not contents:
        raise ValueError("Library carries no application/sql content")
    sql = contents[0].data

    # Setup DDL ships WITH the sample (setup.sql, generated at build time
    # via the composition runner) — no Pyodide-side composition at runtime
    # (the in-Pyodide duckdb execution proved too heavy and crashed the
    # worker). The App passes it through __setup_json.
    setup_sql = json.loads(__setup_json)
    result = {"ok": True, "sql": sql, "setup_sql": setup_sql}
except Exception as exc:
    from fhir4ds.operations.errors import diagnostic_from_exception
    diag = diagnostic_from_exception(exc, context="sqlquery_library")
    result = {"ok": False, "diagnostics": [diag.to_dict()]}
json.dumps(result)
`);return JSON.parse(o)}async function L(){await y();const e=s.runPython(`
import json
from pathlib import Path
import fhir4ds.viewdef as _vd_pkg
from fhir4ds.viewdef.runner import build_composition_plan, render_view_sqls

_manifest = str(Path(_vd_pkg.__file__).parent / "resources" / "omop" / "manifest.json")
_plan = build_composition_plan(_manifest)
_views = render_view_sqls(_plan, Path(_manifest).parent, "__vd_src")
json.dumps({"plan": _plan, "views": _views})
`),{plan:t,views:o}=JSON.parse(e);await _(`CREATE SCHEMA IF NOT EXISTS "${t.schema}"`);const r={},c={};for(const i of o){await _(`CREATE OR REPLACE VIEW ${i.table_sql} AS
${i.sql}`);const d=await _(`SELECT * FROM ${i.table_sql} LIMIT 0`);r[i.name]=d.schema.fields.map(f=>f.name),c[i.name]=i.sql}s.globals.set("__plan_json",JSON.stringify(t)),s.globals.set("__columns_json",JSON.stringify(r)),s.globals.set("__sqls_json",JSON.stringify(c));const n=s.runPython(`
import json
from fhir4ds.viewdef.runner import render_composition_ddl
json.dumps(render_composition_ddl(
    json.loads(__plan_json),
    json.loads(__columns_json),
    sql_by_view=json.loads(__sqls_json),
))
`);return JSON.parse(n)}async function C(e){await y(),s.globals.set("__vd_json",JSON.stringify(e));const t=s.runPython(`
import json
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator

try:
    vd = parse_view_definition(json.loads(__vd_json))
    gen = SQLGenerator(source_table="__vd_src")
    sql = gen.generate(vd)
    # View-target joins (rev 2): inline each referenced library view as a
    # CTE (the spec allows materialize-or-inline). The conceptmap library
    # VD flattens monolithic ConceptMap resources staged in __vd_src.
    setup_sql = []
    view_targets = sorted({j.view for j in vd.joins if j.view})
    if view_targets:
        from pathlib import Path
        import fhir4ds.viewdef as _v
        omop_dir = Path(_v.__file__).parent / "resources" / "omop"
        schema = gen.view_schema or "omop"
        ctes = ['CREATE SCHEMA IF NOT EXISTS "' + schema + '"']
        for vt in view_targets:
            stem = next((s for s in json.load(open(omop_dir / "manifest.json"))["views"]
                         if s.replace("-view", "").replace("-", "_") == vt
                         or s == vt or s.replace(".json", "") == vt), None)
            if stem is None:
                # try by VD name match against each library VD
                for f in omop_dir.glob("*-view.json"):
                    cand = json.load(open(f))
                    if cand.get("name") == vt:
                        stem = f.name.replace(".json", "")
                        break
            if stem is not None:
                tvd = parse_view_definition(json.load(open(omop_dir / (stem + ".json"))))
                tgen = SQLGenerator(source_table="__vd_src")
                tgen.view_schema = schema
                tsql = tgen.generate(tvd)
                ctes.append('CREATE OR REPLACE VIEW "' + schema + '"."' + vt + '" AS\\n' + tsql)
    result = {"ok": True, "sql": sql, "setup_sql": ctes if view_targets else []}
except Exception as exc:
    from fhir4ds.operations.errors import diagnostic_from_exception
    diag = diagnostic_from_exception(exc, context="flatten_view")
    result = {"ok": False, "diagnostics": [diag.to_dict()]}
json.dumps(result)
`);return JSON.parse(t)}async function D(){if(E)return{id:0,type:"boot",ok:!0};const e=Date.now();try{const{loadPyodide:t}=await import(`${k}pyodide.mjs`);s=await t({indexURL:k}),await s.loadPackage(["micropip","duckdb","orjson","pyarrow"]);const o=new URL("./fhir4ds_v2-0.0.19-py3-none-any.whl?v=06fa7c4e7e5f",import.meta.url).href;s.globals.set("__wheel_url__",o),await s.runPythonAsync(`
import micropip, json

await micropip.install([
    "antlr4-python3-runtime>=4.10",
    "python-dateutil>=2.8",
])
await micropip.install(__wheel_url__, deps=False)
`),s.runPython(`
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator
_vd = parse_view_definition({"resource": "Patient", "select": [{"column": [{"name": "id", "path": "id"}]}]})
_sql = SQLGenerator(source_table="__vd_src").generate(_vd)
assert "id" in _sql, "viewdef boot smoke failed"

import fhir4ds
__wheel_version__ = fhir4ds.__version__
`);const r=s.runPython("__wheel_version__"),{initDuckDB:c}=await Promise.resolve().then(function(){return T});return await c(),P(),{id:0,type:"boot",ok:!0,wheelVersion:r,bootMs:Date.now()-e}}catch(t){for(const o of w)o();return w.length=0,{id:0,type:"boot",ok:!1,error:t instanceof Error?t.message:String(t)}}}
