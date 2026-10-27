let b=null,y=null;async function j(e){b||(y||(y=(async()=>{const{createDuckDBConnection:t}=await import("./duckdb-wasm-CCZ60a6p.js"),{conn:o}=await t(e);b={conn:o}})().catch(t=>{throw y=null,t})),await y)}async function p(e){return await j(),b.conn.query(e)}function d(e,t){if(e==null)return null;const o=typeof e;if(o==="bigint")return t!==void 0&&t>0?Number(e)/Math.pow(10,t):Number(e);if(o==="number"||o==="boolean"||o==="string")return e;if(Array.isArray(e))return e.map(i=>d(i));if(o==="object"){if(typeof e.toArray=="function")return d(e.toArray());const i=String(e);if(/^-?\d+(?:\.\d+)?$/.test(i)){const a=Number(i);return t!==void 0&&t>0?a/Math.pow(10,t):a}const s={};for(const[a,c]of Object.entries(e))typeof c!="function"&&(s[a]=d(c));return s}return String(e)}async function v(e,t,o=[],i){var c,u;await j();const s=["CREATE OR REPLACE TEMP TABLE __vd_src (resource JSON)"];if(t.length===0)s.push("INSERT INTO __vd_src SELECT NULL WHERE false");else for(let _=0;_<t.length;_+=150){const m=t.slice(_,_+150).map(q=>`('${JSON.stringify(q).replace(/'/g,"''")}')`).join(", ");s.push(`INSERT INTO __vd_src VALUES ${m}`)}const a={schema:1,ok:!0};try{for(const r of s)await p(r);for(const r of o)await p(r);if(i){const r=await i();for(const w of r)await p(w)}const l=await p(e),_=l.schema.fields.map(r=>r.name),m={};for(const r of l.schema.fields)m[r.name]=((c=r.type)==null?void 0:c.typeId)===7?r.scale??((u=r.type)==null?void 0:u.scale):void 0;const k=(await l.toArray()).map(r=>{const w={};for(const h of _)w[h]=d(r[h]===void 0?null:r[h],m[h]);return w});a.sql=e,a.columns=_,a.rows=JSON.parse(JSON.stringify(k))}catch(l){a.ok=!1,a.diagnostics=[{code:"evaluation_error",severity:"error",message:String(l instanceof Error?l.message:l)}]}return a}var N=Object.freeze({__proto__:null,initDuckDB:j,jsonSafe:d,runRaw:p,stageAndRunFlat:v});const E="https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";let n=null,S=!1;const f=[];function O(){S=!0;for(const e of f)e();f.length=0}async function g(){S||await new Promise(e=>f.push(e))}self.onmessage=async e=>{const t=e.data;try{const o=await T(t);self.postMessage(o)}catch(o){self.postMessage({id:t.id,type:t.type,ok:!1,error:o instanceof Error?o.message:String(o)})}};async function T(e){var i;if(e.type==="boot")return C();if(await g(),((i=e.view_definition)==null?void 0:i.resourceType)==="Library"){const s=await A(e.view_definition,e.setup_sql??[]);if(!s.ok)return{id:e.id,type:e.type,ok:!0,envelope:JSON.stringify({schema:1,ok:!1,diagnostics:s.diagnostics})};const c=!(s.setup_sql&&s.setup_sql.length)&&/\bomop\./i.test(s.sql??"")?await v(s.sql,e.resources,[],P):await v(s.sql,e.resources,s.setup_sql);return{id:e.id,type:e.type,ok:!0,envelope:JSON.stringify(c)}}const t=await R(e.view_definition);if(!t.ok)return{id:e.id,type:e.type,ok:!0,envelope:JSON.stringify({schema:1,ok:!1,diagnostics:t.diagnostics})};const o=await v(t.sql,e.resources,t.setup_sql);return{id:e.id,type:e.type,ok:!0,envelope:JSON.stringify(o)}}async function A(e,t){await g(),n.globals.set("__lib_json",JSON.stringify(e)),n.globals.set("__setup_json",JSON.stringify(t));const o=n.runPython(`
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
`);return JSON.parse(o)}async function P(){await g();const e=n.runPython(`
import json
from pathlib import Path
import fhir4ds.viewdef as _vd_pkg
from fhir4ds.viewdef.runner import build_composition_plan, render_view_sqls

_manifest = str(Path(_vd_pkg.__file__).parent / "resources" / "omop" / "manifest.json")
_plan = build_composition_plan(_manifest)
_views = render_view_sqls(_plan, Path(_manifest).parent, "__vd_src")
json.dumps({"plan": _plan, "views": _views})
`),{plan:t,views:o}=JSON.parse(e);await p(`CREATE SCHEMA IF NOT EXISTS "${t.schema}"`);const i={},s={};for(const c of o){await p(`CREATE OR REPLACE VIEW ${c.table_sql} AS
${c.sql}`);const u=await p(`SELECT * FROM ${c.table_sql} LIMIT 0`);i[c.name]=u.schema.fields.map(l=>l.name),s[c.name]=c.sql}n.globals.set("__plan_json",JSON.stringify(t)),n.globals.set("__columns_json",JSON.stringify(i)),n.globals.set("__sqls_json",JSON.stringify(s));const a=n.runPython(`
import json
from fhir4ds.viewdef.runner import render_composition_ddl
json.dumps(render_composition_ddl(
    json.loads(__plan_json),
    json.loads(__columns_json),
    sql_by_view=json.loads(__sqls_json),
))
`);return JSON.parse(a)}async function R(e){await g(),n.globals.set("__vd_json",JSON.stringify(e));const t=n.runPython(`
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
`);return JSON.parse(t)}async function C(){if(S)return{id:0,type:"boot",ok:!0};const e=Date.now();try{const{loadPyodide:t}=await import(`${E}pyodide.mjs`);n=await t({indexURL:E}),await n.loadPackage(["micropip","duckdb","orjson","pyarrow"]);const o=new URL("./fhir4ds_v2-0.0.19-py3-none-any.whl?v=90c6f25847f6",import.meta.url).href;n.globals.set("__wheel_url__",o),await n.runPythonAsync(`
import micropip, json

await micropip.install([
    "antlr4-python3-runtime>=4.10",
    "python-dateutil>=2.8",
])
await micropip.install(__wheel_url__, deps=False)
`),n.runPython(`
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator
_vd = parse_view_definition({"resource": "Patient", "select": [{"column": [{"name": "id", "path": "id"}]}]})
_sql = SQLGenerator(source_table="__vd_src").generate(_vd)
assert "id" in _sql, "viewdef boot smoke failed"

import fhir4ds
__wheel_version__ = fhir4ds.__version__
`);const i=n.runPython("__wheel_version__"),{initDuckDB:s}=await Promise.resolve().then(function(){return N});return await s(),O(),{id:0,type:"boot",ok:!0,wheelVersion:i,bootMs:Date.now()-e}}catch(t){for(const o of f)o();return f.length=0,{id:0,type:"boot",ok:!1,error:t instanceof Error?t.message:String(t)}}}
