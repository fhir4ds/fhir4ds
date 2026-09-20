const u="https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";let l=null;self.onmessage=async a=>{const{id:o,type:e,cql:s,audit:r}=a.data;if(e==="init"){try{await y(),self.postMessage({id:0,ok:!0})}catch(t){self.postMessage({id:0,ok:!1,error:t instanceof Error?t.message:String(t)})}return}if(e==="translate"){const t=performance.now();try{if(!l)throw new Error("Pyodide not initialized");const i=await m(s??"",r??!1),c=g(i),d=performance.now()-t;self.postMessage({id:o,ok:!0,sql:c,timeMs:d})}catch(i){self.postMessage({id:o,ok:!1,error:i instanceof Error?i.message:String(i)})}}};async function y(){const{loadPyodide:a}=await import(`${u}pyodide.mjs`);l=await a({indexURL:u}),await l.loadPackage(["micropip","duckdb","orjson","pyarrow"]);const o=new URL("./fhir4ds_v2-0.0.15-py3-none-any.whl",import.meta.url).href;console.log("[Pyodide Worker] Installing fhir4ds-v2 from:",o),l.globals.set("__wheel_url__",o),await l.runPythonAsync(`
import micropip

# Install pure-Python runtime dependencies first.
# Pyodide-hosted binary packages are loaded via pyodide.loadPackage() before this block.
await micropip.install([
    "antlr4-python3-runtime>=4.10",
    "python-dateutil>=2.8",
])

# Install fhir4ds-v2 without auto-resolving deps to avoid native dependency
# resolution through PyPI wheels.
await micropip.install(__wheel_url__, deps=False)
`),l.runPython(`
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql import CQLToSQLTranslator
print("[Pyodide Worker] fhir4ds-v2 ready")
`),console.log("[Pyodide Worker] Initialization complete")}async function m(a,o){l.globals.set("_cql_input",a),l.globals.set("_audit_mode",o);const e=l.runPython(`
import traceback
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql import CQLToSQLTranslator

_error = None
_sql = None
try:
    _library = parse_cql(_cql_input)
    _translator = CQLToSQLTranslator()
    if _audit_mode:
        _translator.context.set_audit_mode(True)
    _sql = _translator.translate_library_to_population_sql(_library)
except Exception as e:
    lines = traceback.format_exc().strip().splitlines()
    last = next((l.strip() for l in reversed(lines) if l.strip() and not l.startswith("During")), str(e))
    _error = f"{type(e).__name__}: {last.split(': ', 1)[-1]}"

[_sql, _error]
`),[s,r]=e.toJs?e.toJs():Array.from(e);if(r)throw new Error(String(r));return typeof s=="string"?s:String(s)}function g(a){return w(a)}function w(a){const o="list_extract(";let e=a,s=!0;for(;s;){s=!1;let r="",t=0;for(;t<e.length;){const i=e.indexOf(o,t);if(i===-1){r+=e.slice(t);break}let c=0,d=-1,n=i+o.length-1,f=!1,h="";for(;n<e.length;n++){const p=e[n];if(f)p===h&&e[n-1]!=="\\"&&(f=!1);else if(p==="'"||p==='"')f=!0,h=p;else if(p==="(")c++;else if(p===")"){if(c--,c===0)break}else p===","&&c===1&&(d=n)}if(c!==0||d===-1){r+=e.slice(t,i+1),t=i+1;continue}const _=e.slice(i+o.length,d).trim();if(/fhirpath_text/i.test(_)&&!/\bfhirpath\(/.test(_)){r+=e.slice(t,i)+_,e=r+e.slice(n+1),s=!0,r="",t=0;continue}r+=e.slice(t,n+1),t=n+1}s||(e=r)}return e}
