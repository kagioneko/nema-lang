#!/usr/bin/env python3
"""
demo.wasm を読み込んで自己完結型の browser_demo/index.html を生成する。
事前に demo.nema → WASM のコンパイルが必要:
  python3 nema.py browser_demo/demo.nema --wasm
"""

import base64
import os

HERE = os.path.dirname(os.path.abspath(__file__))
WASM_PATH = os.path.join(HERE, "demo.wasm")
OUT_PATH = os.path.join(HERE, "index.html")


def main():
    with open(WASM_PATH, "rb") as f:
        wasm_b64 = base64.b64encode(f.read()).decode("ascii")

    html = generate_html(wasm_b64)
    with open(OUT_PATH, "w") as f:
        f.write(html)

    size = os.path.getsize(OUT_PATH)
    print(f"✅ 生成: {OUT_PATH} ({size:,} bytes)")
    print(f"   ブラウザで開く: file://{OUT_PATH}")


def generate_html(wasm_b64: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nema Language — WebAssembly Demo</title>
  <style>
    :root {{
      --bg:      #0f1117;
      --surface: #181b28;
      --card:    #1e2230;
      --border:  #2a2d3d;
      --accent:  #7c6ff7;
      --pass:    #4ecca3;
      --fail:    #ff6b6b;
      --text:    #e4e4f0;
      --muted:   #6b7280;
      --mono: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
      min-height: 100vh;
      padding: 2.5rem 1.5rem 3rem;
    }}

    /* ── Header ── */
    header {{
      text-align: center;
      margin-bottom: 2.5rem;
    }}
    header h1 {{
      font-size: 1.75rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    header h1 .brand {{ color: var(--accent); }}
    header p {{
      color: var(--muted);
      margin-top: 0.4rem;
      font-size: 0.88rem;
    }}
    .badges {{
      display: flex;
      gap: 0.5rem;
      justify-content: center;
      margin-top: 0.75rem;
      flex-wrap: wrap;
    }}
    .badge {{
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      padding: 3px 10px;
      border-radius: 999px;
      border: 1px solid;
    }}
    .badge-wasm {{ color: #7c6ff7; border-color: #7c6ff740; background: #7c6ff710; }}
    .badge-ver  {{ color: var(--pass); border-color: #4ecca340; background: #4ecca310; }}
    .badge-oss  {{ color: #ffd166;    border-color: #ffd16640; background: #ffd16610; }}

    /* ── Grid ── */
    .agents {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 1.5rem;
      max-width: 860px;
      margin: 0 auto;
    }}

    /* ── Agent Card ── */
    .agent-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }}

    .agent-header {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border);
    }}
    .agent-dot {{
      width: 10px; height: 10px;
      border-radius: 50%;
      background: var(--accent);
      flex-shrink: 0;
    }}
    .agent-name {{
      font-size: 1.1rem;
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .attractor-badge {{
      margin-left: auto;
      font-size: 0.72rem;
      color: var(--muted);
      background: #ffffff08;
      padding: 3px 10px;
      border-radius: 8px;
      font-family: var(--mono);
      letter-spacing: 0.04em;
      transition: color 0.3s;
    }}

    /* ── NeuroState Sliders ── */
    .neurostate {{ display: flex; flex-direction: column; gap: 7px; }}

    .ns-row {{
      display: grid;
      grid-template-columns: 38px 1fr 44px;
      align-items: center;
      gap: 8px;
    }}
    .ns-label {{
      font-family: var(--mono);
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.02em;
    }}
    .ns-value {{
      font-family: var(--mono);
      font-size: 0.78rem;
      text-align: right;
      color: var(--muted);
      transition: color 0.2s;
    }}

    input[type="range"] {{
      -webkit-appearance: none;
      appearance: none;
      width: 100%;
      height: 5px;
      border-radius: 3px;
      background: var(--border);
      outline: none;
      cursor: pointer;
    }}
    input[type="range"]::-webkit-slider-thumb {{
      -webkit-appearance: none;
      width: 15px; height: 15px;
      border-radius: 50%;
      background: currentColor;
      cursor: pointer;
      box-shadow: 0 0 0 3px currentColor20;
    }}
    input[type="range"]::-moz-range-thumb {{
      width: 15px; height: 15px;
      border-radius: 50%;
      background: currentColor;
      cursor: pointer;
      border: none;
    }}

    /* ── Function Rows ── */
    .fns {{ display: flex; flex-direction: column; gap: 0.55rem; }}

    .fn-row {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.65rem 0.85rem;
      background: #ffffff03;
      border: 1px solid var(--border);
      border-radius: 12px;
      transition: border-color 0.15s;
    }}
    .fn-row:hover {{ border-color: #ffffff18; }}

    .fn-status {{
      width: 9px; height: 9px;
      border-radius: 50%;
      flex-shrink: 0;
      transition: background 0.25s, box-shadow 0.25s;
      background: var(--muted);
    }}
    .fn-status.pass {{
      background: var(--pass);
      box-shadow: 0 0 8px #4ecca380;
    }}
    .fn-status.fail {{ background: var(--fail); box-shadow: none; }}

    .fn-info {{ flex: 1; min-width: 0; }}
    .fn-name {{
      font-family: var(--mono);
      font-size: 0.83rem;
      font-weight: 600;
    }}
    .fn-gate {{
      font-size: 0.7rem;
      color: var(--muted);
      margin-top: 2px;
      font-family: var(--mono);
    }}

    .fn-result {{
      font-family: var(--mono);
      font-size: 0.8rem;
      color: var(--muted);
      flex-shrink: 0;
      min-width: 56px;
      text-align: right;
      transition: color 0.2s;
    }}
    .fn-result.pass {{ color: var(--pass); }}
    .fn-result.fail {{ color: var(--fail); }}

    /* ── Footer ── */
    footer {{
      text-align: center;
      margin-top: 3rem;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.8;
    }}
    footer a {{ color: var(--accent); text-decoration: none; }}
    footer a:hover {{ text-decoration: underline; }}

    /* ── Loading ── */
    #loading {{
      text-align: center;
      padding: 3rem;
      color: var(--muted);
    }}
    .spinner {{
      display: inline-block;
      width: 18px; height: 18px;
      border: 2px solid var(--border);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
      margin-right: 8px;
      vertical-align: middle;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

    /* ── Legend ── */
    .legend {{
      max-width: 860px;
      margin: 1.5rem auto 0;
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 1.2rem;
      justify-content: center;
      font-size: 0.72rem;
      color: var(--muted);
    }}
    .legend-item {{ display: flex; align-items: center; gap: 5px; }}
    .legend-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
  </style>
</head>
<body>

<header>
  <h1><span class="brand">Nema</span> Language — WebAssembly Demo</h1>
  <p>NeuroState-gated agents compiled from <code style="color:var(--accent)">.nema</code> source and running natively in your browser</p>
  <div class="badges">
    <span class="badge badge-wasm">WebAssembly</span>
    <span class="badge badge-ver">nema-lang v0.3.1</span>
    <span class="badge badge-oss">MIT License</span>
  </div>
</header>

<div id="loading">
  <span class="spinner"></span>Loading WASM module&hellip;
</div>

<div id="app" style="display:none">
  <div class="agents" id="agents-container"></div>
  <div class="legend" id="legend"></div>
</div>

<footer>
  <p>
    <a href="https://github.com/kagioneko/nema-lang" target="_blank">github.com/kagioneko/nema-lang</a>
    &nbsp;·&nbsp;
    <a href="https://pypi.org/project/nema-lang/" target="_blank">PyPI: nema-lang</a>
  </p>
  <p style="margin-top:4px">
    Sliders write directly to WASM f64 globals &mdash;
    gate conditions are checked in real time
  </p>
</footer>

<script>
// ── WASM binary (base64-embedded) ────────────────────────────────────────────
const WASM_B64 = "{wasm_b64}";

// ── NeuroState field metadata ─────────────────────────────────────────────────
const NS_FIELDS = [
  {{ key: "dp",   color: "#ff6b6b", title: "Dopamine"       }},
  {{ key: "s",    color: "#4ecca3", title: "Serotonin"      }},
  {{ key: "ac",   color: "#ffd166", title: "Acetylcholine"  }},
  {{ key: "ox",   color: "#06d6a0", title: "Oxytocin"       }},
  {{ key: "gaba", color: "#118ab2", title: "GABA"           }},
  {{ key: "e",    color: "#ef476f", title: "Endorphin"      }},
];

// ── Attractor inference (mirrors Nema stdlib) ─────────────────────────────────
function nearestAttractor(s) {{
  if (s.dp > 0.8 && s.ac > 0.7)          return "flow";
  if (s.dp > 0.7 && s.s  < 0.5)          return "explore";
  if (s.ox > 0.7 && s.e  > 0.6)          return "social";
  if (s.s  > 0.7 && s.gaba > 0.6)        return "rest";
  if (s.s  < 0.3)                         return "crisis ⚠";
  return "neutral";
}}

// ── Agent definitions (mirrors demo.nema) ────────────────────────────────────
const AGENTS = [
  {{
    name: "Emilia",
    fns: [
      {{ name: "explore",    gate: "dp > 0.6",              exp: "Emilia_explore"    }},
      {{ name: "rest",       gate: "s > 0.5 ∧ gaba > 0.4", exp: "Emilia_rest"       }},
      {{ name: "connect",    gate: "ox > 0.6",              exp: "Emilia_connect"    }},
      {{ name: "mood_score", gate: "— always —",            exp: "Emilia_mood_score" }},
    ]
  }},
  {{
    name: "Kernel",
    fns: [
      {{ name: "process",    gate: "dp > 0.7 ∧ ac > 0.5",  exp: "Kernel_process"    }},
      {{ name: "sleep_mode", gate: "gaba > 0.6",            exp: "Kernel_sleep_mode" }},
      {{ name: "status",     gate: "— always —",            exp: "Kernel_status"     }},
    ]
  }}
];

// ── Helpers ───────────────────────────────────────────────────────────────────
function b64ToBytes(b64) {{
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf;
}}

function fmtResult(v) {{
  if (v === -1) return "blocked";
  return v.toFixed(4);
}}

// ── UI builders ───────────────────────────────────────────────────────────────
function buildCard(agent) {{
  const card = document.createElement("div");
  card.className = "agent-card";
  card.innerHTML = `
    <div class="agent-header">
      <div class="agent-dot"></div>
      <span class="agent-name">${{agent.name}}</span>
      <span class="attractor-badge" id="${{agent.name}}_attractor">…</span>
    </div>
    <div class="neurostate" id="${{agent.name}}_ns"></div>
    <div class="fns" id="${{agent.name}}_fns"></div>
  `;

  const ns = card.querySelector(`#${{agent.name}}_ns`);
  for (const f of NS_FIELDS) {{
    const row = document.createElement("div");
    row.className = "ns-row";
    row.innerHTML = `
      <span class="ns-label" style="color:${{f.color}}" title="${{f.title}}">${{f.key}}</span>
      <input type="range" id="${{agent.name}}_${{f.key}}_sl"
             min="0" max="1" step="0.01" value="0.5"
             style="accent-color:${{f.color}};color:${{f.color}}">
      <span class="ns-value" id="${{agent.name}}_${{f.key}}_val">0.50</span>
    `;
    ns.appendChild(row);
  }}

  const fns = card.querySelector(`#${{agent.name}}_fns`);
  for (const fn of agent.fns) {{
    const row = document.createElement("div");
    row.className = "fn-row";
    row.innerHTML = `
      <div class="fn-status" id="${{agent.name}}_${{fn.name}}_st"></div>
      <div class="fn-info">
        <div class="fn-name">${{fn.name}}()</div>
        <div class="fn-gate">${{fn.gate}}</div>
      </div>
      <div class="fn-result" id="${{agent.name}}_${{fn.name}}_res">…</div>
    `;
    fns.appendChild(row);
  }}

  return card;
}}

function buildLegend() {{
  const leg = document.getElementById("legend");
  for (const f of NS_FIELDS) {{
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML = `<div class="legend-dot" style="background:${{f.color}}"></div>${{f.key}} = ${{f.title}}`;
    leg.appendChild(item);
  }}
}}

// ── State update (called on every slider change) ──────────────────────────────
let wasmExports = null;

function refreshAgent(agent) {{
  const state = {{}};

  // 1. Read sliders → write to WASM globals
  for (const f of NS_FIELDS) {{
    const sl = document.getElementById(`${{agent.name}}_${{f.key}}_sl`);
    const v = parseFloat(sl.value);
    state[f.key] = v;

    document.getElementById(`${{agent.name}}_${{f.key}}_val`).textContent = v.toFixed(2);

    if (wasmExports) {{
      const g = wasmExports[`${{agent.name}}_${{f.key}}`];
      if (g) g.value = v;
    }}
  }}

  // 2. Attractor label
  const attr = nearestAttractor(state);
  const attrEl = document.getElementById(`${{agent.name}}_attractor`);
  attrEl.textContent = attr;
  attrEl.style.color = attr === "crisis ⚠" ? "var(--fail)"
                      : attr === "flow"     ? "#ffd166"
                      : attr === "explore"  ? "#ff6b6b"
                      : attr === "social"   ? "#06d6a0"
                      : "var(--muted)";

  // 3. Call WASM functions → update status dots + result values
  if (!wasmExports) return;
  for (const fn of agent.fns) {{
    const stEl  = document.getElementById(`${{agent.name}}_${{fn.name}}_st`);
    const resEl = document.getElementById(`${{agent.name}}_${{fn.name}}_res`);
    try {{
      const result = wasmExports[fn.exp]();
      if (result === -1) {{
        stEl.className  = "fn-status fail";
        resEl.textContent = "blocked";
        resEl.className = "fn-result fail";
      }} else {{
        stEl.className  = "fn-status pass";
        resEl.textContent = result.toFixed(4);
        resEl.className = "fn-result pass";
      }}
    }} catch (e) {{
      stEl.className = "fn-status fail";
      resEl.textContent = "error";
      resEl.className = "fn-result fail";
    }}
  }}
}}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
async function init() {{
  // Build UI
  const container = document.getElementById("agents-container");
  for (const agent of AGENTS) container.appendChild(buildCard(agent));
  buildLegend();

  // Instantiate WASM
  const bytes = b64ToBytes(WASM_B64);
  const {{ instance }} = await WebAssembly.instantiate(bytes.buffer);
  wasmExports = instance.exports;

  // Wire sliders: read initial values from WASM globals, attach handlers
  for (const agent of AGENTS) {{
    for (const f of NS_FIELDS) {{
      const sl = document.getElementById(`${{agent.name}}_${{f.key}}_sl`);
      const g  = wasmExports[`${{agent.name}}_${{f.key}}`];
      if (g) sl.value = g.value.toFixed(2);
      sl.addEventListener("input", () => refreshAgent(agent));
    }}
    refreshAgent(agent);
  }}

  document.getElementById("loading").style.display = "none";
  document.getElementById("app").style.display = "block";
}}

init().catch(err => {{
  document.getElementById("loading").innerHTML =
    `<p style="color:var(--fail)">⚠ WASM load error: ${{err.message}}</p>`;
}});
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
