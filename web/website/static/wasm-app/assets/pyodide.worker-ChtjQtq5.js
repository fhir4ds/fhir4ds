const h="https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";let n=null;self.onmessage=async l=>{const{id:s,type:e,cql:o,audit:r}=l.data;if(e==="init"){try{await m(),self.postMessage({id:0,ok:!0})}catch(t){self.postMessage({id:0,ok:!1,error:t instanceof Error?t.message:String(t)})}return}if(e==="translate"){const t=performance.now();try{if(!n)throw new Error("Pyodide not initialized");const i=await y(o??"",r??!1),c=g(i),p=performance.now()-t;self.postMessage({id:s,ok:!0,sql:c,timeMs:p})}catch(i){self.postMessage({id:s,ok:!1,error:i instanceof Error?i.message:String(i)})}}};async function m(){const{loadPyodide:l}=await import(`${h}pyodide.mjs`);n=await l({indexURL:h}),await n.loadPackage(["micropip"]);const s=new URL("./fhir4ds_v2-0.0.3-py3-none-any.whl",import.meta.url).href;console.log("[Pyodide Worker] Installing fhir4ds-v2 from:",s),n.globals.set("__wheel_url__",s),await n.runPythonAsync(`
import micropip

# Install pure-Python runtime dependencies first.
# duckdb is intentionally excluded — it's provided by DuckDB-WASM.
await micropip.install([
    "antlr4-python3-runtime>=4.10",
    "python-dateutil>=2.8",
])

# Install fhir4ds-v2 without auto-resolving deps to avoid the duckdb
# dependency resolution failure (duckdb has no pure Python wheel).
await micropip.install(__wheel_url__, deps=False)
`),n.runPython(`
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql import CQLToSQLTranslator
print("[Pyodide Worker] fhir4ds-v2 ready")
`),console.log("[Pyodide Worker] Initialization complete")}async function y(l,s){n.globals.set("_cql_input",l),n.globals.set("_audit_mode",s);const e=n.runPython(`
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
`),[o,r]=e.toJs?e.toJs():Array.from(e);if(r)throw new Error(String(r));return typeof o=="string"?o:String(o)}function g(l){return w(l)}function w(l){const s="list_extract(";let e=l,o=!0;for(;o;){o=!1;let r="",t=0;for(;t<e.length;){const i=e.indexOf(s,t);if(i===-1){r+=e.slice(t);break}let c=0,p=-1,a=i+s.length-1,f=!1,u="";for(;a<e.length;a++){const d=e[a];if(f)d===u&&e[a-1]!=="\\"&&(f=!1);else if(d==="'"||d==='"')f=!0,u=d;else if(d==="(")c++;else if(d===")"){if(c--,c===0)break}else d===","&&c===1&&(p=a)}if(c!==0||p===-1){r+=e.slice(t,i+1),t=i+1;continue}const _=e.slice(i+s.length,p).trim();if(/fhirpath/i.test(_)){r+=e.slice(t,i)+_,e=r+e.slice(a+1),o=!0,r="",t=0;continue}r+=e.slice(t,a+1),t=a+1}o||(e=r)}return e}
