"""IntelligenceSuite Launcher — navigation hub, no subprocess management."""

from __future__ import annotations
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="IntelligenceSuite Launcher", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IntelligenceSuite</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  .card { transition: transform .2s, box-shadow .2s; }
  .card:hover { transform: translateY(-3px); box-shadow: 0 10px 35px rgba(0,0,0,.4); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.35} }
  .dot-pulse { animation: pulse 2s infinite; }
</style>
</head>
<body class="bg-gray-950 text-white min-h-screen flex flex-col">

<header class="border-b border-gray-800 px-8 py-5 flex items-center gap-4">
  <span class="text-3xl">🧠</span>
  <div>
    <h1 class="text-lg font-bold tracking-tight">IntelligenceSuite</h1>
    <p class="text-xs text-gray-500">On-premise knowledge retrieval · Local AI</p>
  </div>
</header>

<main class="flex-1 flex items-center justify-center px-8 py-14">
  <div class="grid grid-cols-1 md:grid-cols-4 gap-6 w-full max-w-6xl">

    <!-- Code Intelligence -->
    <div class="card bg-gray-900 border border-gray-800 rounded-2xl p-7 flex flex-col gap-4">
      <div class="flex items-start justify-between">
        <span class="text-4xl">💻</span>
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-gray-600 dot-pulse" id="dot-code"></div>
          <span class="text-xs text-gray-500" id="label-code">checking…</span>
        </div>
      </div>
      <div>
        <h2 class="font-bold text-base mb-1" style="color:#818cf8">Code Intelligence</h2>
        <p class="text-xs text-gray-400 leading-relaxed">
          Ask questions about your source code in natural language.
        </p>
      </div>
      <div class="text-xs text-gray-600 font-mono">localhost:8080</div>
      <div class="text-xs text-gray-500" id="info-code">—</div>
      <a id="btn-code" href="http://localhost:8080" target="_blank"
         class="mt-auto block text-center bg-gray-700 hover:bg-indigo-700
                text-sm py-2.5 rounded-xl font-semibold transition">
        Apri →
      </a>
    </div>

    <!-- Doc Intelligence -->
    <div class="card bg-gray-900 border border-gray-800 rounded-2xl p-7 flex flex-col gap-4">
      <div class="flex items-start justify-between">
        <span class="text-4xl">📄</span>
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-gray-600 dot-pulse" id="dot-doc"></div>
          <span class="text-xs text-gray-500" id="label-doc">checking…</span>
        </div>
      </div>
      <div>
        <h2 class="font-bold text-base mb-1" style="color:#22d3ee">Doc Intelligence</h2>
        <p class="text-xs text-gray-400 leading-relaxed">
          Query documents in any language — PDF, DOCX, XLSX, Markdown.
        </p>
      </div>
      <div class="text-xs text-gray-600 font-mono">localhost:8081</div>
      <div class="text-xs text-gray-500" id="info-doc">—</div>
      <a id="btn-doc" href="http://localhost:8081" target="_blank"
         class="mt-auto block text-center bg-gray-700 hover:bg-cyan-700
                text-sm py-2.5 rounded-xl font-semibold transition">
        Apri →
      </a>
    </div>

    <!-- Mentor Intelligence -->
    <div class="card bg-gray-900 border border-gray-800 rounded-2xl p-7 flex flex-col gap-4">
      <div class="flex items-start justify-between">
        <span class="text-4xl">🎓</span>
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-gray-600 dot-pulse" id="dot-mentor"></div>
          <span class="text-xs text-gray-500" id="label-mentor">checking…</span>
        </div>
      </div>
      <div>
        <h2 class="font-bold text-base mb-1" style="color:#f472b6">Mentor Intelligence</h2>
        <p class="text-xs text-gray-400 leading-relaxed">
          Adaptive onboarding with session management and cross-domain retrieval.
        </p>
      </div>
      <div class="text-xs text-gray-600 font-mono">localhost:8082</div>
      <div class="text-xs text-gray-500" id="info-mentor">—</div>
      <a id="btn-mentor" href="http://localhost:8082" target="_blank"
         class="mt-auto block text-center bg-gray-700 hover:bg-pink-700
                text-sm py-2.5 rounded-xl font-semibold transition">
        Apri →
      </a>
    </div>

    <!-- Skill Intelligence -->
    <div class="card bg-gray-900 border border-gray-800 rounded-2xl p-7 flex flex-col gap-4">
      <div class="flex items-start justify-between">
        <span class="text-4xl">🧩</span>
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-gray-600 dot-pulse" id="dot-skill"></div>
          <span class="text-xs text-gray-500" id="label-skill">checking…</span>
        </div>
      </div>
      <div>
        <h2 class="font-bold text-base mb-1" style="color:#a3e635">Skill Intelligence</h2>
        <p class="text-xs text-gray-400 leading-relaxed">
          Step-by-step procedural guidance with cross-domain knowledge retrieval.
        </p>
      </div>
      <div class="text-xs text-gray-600 font-mono">localhost:8083</div>
      <div class="text-xs text-gray-500" id="info-skill">—</div>
      <a id="btn-skill" href="http://localhost:8083" target="_blank"
         class="mt-auto block text-center bg-gray-700 hover:bg-lime-700
                text-sm py-2.5 rounded-xl font-semibold transition">
        Apri →
      </a>
    </div>

  </div>
</main>

<footer class="border-t border-gray-800 px-8 py-3 text-center text-xs text-gray-600">
  IntelligenceSuite · <span id="footer-status">checking…</span>
</footer>

<script>
const MODULES = [
  { key:'code',   port:8080, hover:'hover:bg-indigo-700' },
  { key:'doc',    port:8081, hover:'hover:bg-cyan-700'   },
  { key:'mentor', port:8082, hover:'hover:bg-pink-700'   },
  { key:'skill',  port:8083, hover:'hover:bg-lime-700'   },
];
const CLI = { code:'ci-serve', doc:'di-serve', mentor:'mi-serve', skill:'si-serve' };

async function poll() {
  let online = 0;
  for (const m of MODULES) {
    try {
      const r = await fetch('http://localhost:' + m.port + '/health',
                            { signal: AbortSignal.timeout(2000) });
      const d = r.ok ? await r.json() : null;
      if (d) { setOnline(m, d); online++; } else setOffline(m);
    } catch { setOffline(m); }
  }
  document.getElementById('footer-status').textContent =
    online === MODULES.length ? 'Tutti i moduli online ✓'
    : online === 0            ? 'Nessun modulo attivo — avvia i server dalla CLI'
    :                           online + ' / ' + MODULES.length + ' moduli online';
}

function setOnline(m, d) {
  document.getElementById('dot-'   + m.key).className = 'w-2 h-2 rounded-full bg-green-400';
  document.getElementById('label-' + m.key).textContent = '● online';
  document.getElementById('label-' + m.key).className   = 'text-xs text-green-400';
  const count = d.skills_count != null
    ? d.skills_count + ' skills'
    : (d.chunks_indexed || 0) + ' chunks';
  document.getElementById('info-'  + m.key).textContent =
    count + ' · ' + (d.llm_backend || '—');
  const btn = document.getElementById('btn-' + m.key);
  btn.className = btn.className.replace('bg-gray-700', 'bg-green-700');
}

function setOffline(m) {
  document.getElementById('dot-'   + m.key).className = 'w-2 h-2 rounded-full bg-gray-600 dot-pulse';
  document.getElementById('label-' + m.key).textContent = '○ offline';
  document.getElementById('label-' + m.key).className   = 'text-xs text-gray-500';
  document.getElementById('info-'  + m.key).textContent = CLI[m.key];
  const btn = document.getElementById('btn-' + m.key);
  btn.className = btn.className.replace('bg-green-700', 'bg-gray-700');
}

poll();
setInterval(poll, 5000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(_HTML)


def main():
    from intelligence_core.config import settings
    port = getattr(settings, "launcher_port", 8079)

    import threading, webbrowser, time
    def _open():
        time.sleep(1.2)
        webbrowser.open(f"http://localhost:{port}")
    threading.Thread(target=_open, daemon=True).start()

    print(f"  🧠  IntelligenceSuite Launcher → http://localhost:{port}")
    uvicorn.run(app, host=settings.api_host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
