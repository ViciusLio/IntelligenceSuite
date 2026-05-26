"""IntelligenceSuite Launcher — start/stop/monitor all three modules from one page."""

from __future__ import annotations
import logging
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

# ── Module registry ─────────────────────────────────────────────────────────
MODULES: dict[str, dict] = {
    "code": {
        "name":        "Code Intelligence",
        "description": "Ask questions about your source code in natural language",
        "icon":        "💻",
        "port":        8080,
        "color":       "#6366f1",
        "cli":         "ci-serve",
        "module":      "CodeIntelligence.rag_server",
        "chunks_cmd":  "ci-parse",
    },
    "doc": {
        "name":        "Doc Intelligence",
        "description": "Query documents, PDFs, DOCX, XLSX in any language",
        "icon":        "📄",
        "port":        8081,
        "color":       "#06b6d4",
        "cli":         "di-serve",
        "module":      "DocIntelligence.doc_server",
        "chunks_cmd":  "di-ingest",
    },
    "mentor": {
        "name":        "Mentor Intelligence",
        "description": "Adaptive onboarding with session-based learning paths",
        "icon":        "🎓",
        "port":        8082,
        "color":       "#ec4899",
        "cli":         "mi-serve",
        "module":      "MentorIntelligence.mentor_server",
        "chunks_cmd":  "mi-ingest",
    },
}

# In-memory process handles (module key → Popen)
_procs: dict[str, subprocess.Popen] = {}


# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="IntelligenceSuite Launcher", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ── Helpers ──────────────────────────────────────────────────────────────────
def _alive(key: str) -> bool:
    """True if we started the process and it's still running."""
    p = _procs.get(key)
    return p is not None and p.poll() is None


def _health_url(port: int) -> str:
    return f"http://localhost:{port}/health"


def _resolve_cmd(cli: str, module: str) -> list[str]:
    """Find the best command to launch a module server.

    Priority:
      1. shutil.which — honours current PATH (conda activate, venv, etc.)
      2. Scripts/ sibling of sys.executable — works when launcher runs inside
         the same venv/conda env as the installed CLI scripts
      3. python -m <module> — universal fallback
    """
    # 1. PATH lookup
    found = shutil.which(cli)
    if found:
        return [found]

    # 2. Same Scripts/ dir as the running Python
    scripts_dir = Path(sys.executable).parent
    for suffix in ("", ".exe", ".cmd", ".bat"):
        candidate = scripts_dir / (cli + suffix)
        if candidate.exists():
            return [str(candidate)]

    # 3. python -m fallback
    logger.warning("CLI %s not found — falling back to python -m %s", cli, module)
    return [sys.executable, "-m", module]


def _start(key: str) -> dict:
    mod = MODULES[key]
    if _alive(key):
        return {"status": "already_running"}

    cmd = _resolve_cmd(mod["cli"], mod["module"])
    logger.info("Starting %s with: %s", key, cmd)
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(Path.cwd()),
        )
        _procs[key] = p
        return {"status": "starting", "pid": p.pid, "port": mod["port"], "cmd": str(cmd[0])}
    except Exception as exc:
        logger.error("Failed to start %s: %s", key, exc)
        return {"status": "error", "detail": str(exc), "cmd": str(cmd)}


def _stop(key: str) -> dict:
    p = _procs.pop(key, None)
    if p is None:
        return {"status": "not_managed"}
    p.terminate()
    return {"status": "stopped"}


# ── REST endpoints ───────────────────────────────────────────────────────────
@app.get("/api/status")
def status():
    result = {}
    for key, mod in MODULES.items():
        running = False
        chunks  = 0
        try:
            r = httpx.get(_health_url(mod["port"]), timeout=1.5)
            if r.status_code == 200:
                running = True
                chunks  = r.json().get("chunks_indexed", 0)
        except Exception:
            pass
        result[key] = {
            "running":     running,
            "managed":     _alive(key),
            "port":        mod["port"],
            "chunks":      chunks,
            "url":         f"http://localhost:{mod['port']}",
        }
    return JSONResponse(result)


@app.post("/api/start/{key}")
def start(key: str):
    if key not in MODULES:
        return JSONResponse({"error": "unknown module"}, status_code=400)
    return JSONResponse(_start(key))


@app.post("/api/stop/{key}")
def stop(key: str):
    if key not in MODULES:
        return JSONResponse({"error": "unknown module"}, status_code=400)
    return JSONResponse(_stop(key))


@app.post("/api/start-all")
def start_all():
    return JSONResponse({k: _start(k) for k in MODULES})


# ── Launcher HTML ────────────────────────────────────────────────────────────
_LAUNCHER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IntelligenceSuite — Launcher</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  .card { transition: transform .2s, box-shadow .2s; }
  .card:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(0,0,0,.35); }
  .dot-pulse { animation: pulse 2s cubic-bezier(.4,0,.6,1) infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  .btn { transition: all .15s; }
</style>
</head>
<body class="bg-gray-950 text-white min-h-screen flex flex-col">

<!-- Header -->
<header class="border-b border-gray-800 px-8 py-5 flex items-center justify-between">
  <div class="flex items-center gap-4">
    <span class="text-3xl">🧠</span>
    <div>
      <h1 class="text-lg font-bold tracking-tight">IntelligenceSuite</h1>
      <p class="text-xs text-gray-500">On-premise knowledge retrieval · Local AI</p>
    </div>
  </div>
  <button onclick="startAll()"
          class="btn bg-indigo-600 hover:bg-indigo-500 px-5 py-2.5 rounded-xl
                 text-sm font-semibold flex items-center gap-2">
    ▶&nbsp; Start All
  </button>
</header>

<!-- Cards grid -->
<main class="flex-1 flex items-center justify-center px-8 py-12">
  <div class="grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-5xl">

    <!-- Code Intelligence -->
    <div class="card bg-gray-900 border border-gray-800 rounded-2xl p-7 flex flex-col gap-5">
      <div class="flex items-start justify-between">
        <div class="text-4xl">💻</div>
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-gray-600 dot-pulse" id="dot-code"></div>
          <span class="text-xs text-gray-500" id="label-code">checking…</span>
        </div>
      </div>
      <div>
        <h2 class="font-bold text-base mb-1" style="color:#818cf8">Code Intelligence</h2>
        <p class="text-xs text-gray-400 leading-relaxed">
          Ask questions about your source code in natural language. Supports Python, TS, Go, SQL, YAML.
        </p>
      </div>
      <div class="text-xs text-gray-600 font-mono">localhost:8080</div>
      <div class="text-xs text-gray-500" id="chunks-code">— chunks indexed</div>
      <div class="flex gap-2 mt-auto">
        <a href="http://localhost:8080" target="_blank"
           class="btn flex-1 text-center bg-gray-800 hover:bg-gray-700 text-sm
                  py-2 rounded-lg font-medium">
          Open →
        </a>
        <button onclick="toggle('code')" id="btn-code"
                class="btn flex-1 bg-indigo-700 hover:bg-indigo-600 text-sm
                       py-2 rounded-lg font-medium">
          Start
        </button>
      </div>
    </div>

    <!-- Doc Intelligence -->
    <div class="card bg-gray-900 border border-gray-800 rounded-2xl p-7 flex flex-col gap-5">
      <div class="flex items-start justify-between">
        <div class="text-4xl">📄</div>
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-gray-600 dot-pulse" id="dot-doc"></div>
          <span class="text-xs text-gray-500" id="label-doc">checking…</span>
        </div>
      </div>
      <div>
        <h2 class="font-bold text-base mb-1" style="color:#22d3ee">Doc Intelligence</h2>
        <p class="text-xs text-gray-400 leading-relaxed">
          Query company documents in any language. PDF (with OCR fallback), DOCX, XLSX, Markdown.
        </p>
      </div>
      <div class="text-xs text-gray-600 font-mono">localhost:8081</div>
      <div class="text-xs text-gray-500" id="chunks-doc">— chunks indexed</div>
      <div class="flex gap-2 mt-auto">
        <a href="http://localhost:8081" target="_blank"
           class="btn flex-1 text-center bg-gray-800 hover:bg-gray-700 text-sm
                  py-2 rounded-lg font-medium">
          Open →
        </a>
        <button onclick="toggle('doc')" id="btn-doc"
                class="btn flex-1 bg-cyan-700 hover:bg-cyan-600 text-sm
                       py-2 rounded-lg font-medium">
          Start
        </button>
      </div>
    </div>

    <!-- Mentor Intelligence -->
    <div class="card bg-gray-900 border border-gray-800 rounded-2xl p-7 flex flex-col gap-5">
      <div class="flex items-start justify-between">
        <div class="text-4xl">🎓</div>
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-gray-600 dot-pulse" id="dot-mentor"></div>
          <span class="text-xs text-gray-500" id="label-mentor">checking…</span>
        </div>
      </div>
      <div>
        <h2 class="font-bold text-base mb-1" style="color:#f472b6">Mentor Intelligence</h2>
        <p class="text-xs text-gray-400 leading-relaxed">
          Adaptive onboarding with profile detection, session management and cross-domain retrieval.
        </p>
      </div>
      <div class="text-xs text-gray-600 font-mono">localhost:8082</div>
      <div class="text-xs text-gray-500" id="chunks-mentor">— chunks indexed</div>
      <div class="flex gap-2 mt-auto">
        <a href="http://localhost:8082" target="_blank"
           class="btn flex-1 text-center bg-gray-800 hover:bg-gray-700 text-sm
                  py-2 rounded-lg font-medium">
          Open →
        </a>
        <button onclick="toggle('mentor')" id="btn-mentor"
                class="btn flex-1 bg-pink-700 hover:bg-pink-600 text-sm
                       py-2 rounded-lg font-medium">
          Start
        </button>
      </div>
    </div>

  </div>
</main>

<!-- Footer -->
<footer class="border-t border-gray-800 px-8 py-3 text-center text-xs text-gray-700">
  IntelligenceSuite Launcher · <span id="footer-status">polling…</span>
</footer>

<script>
// Classi fisse per i bottoni — niente regex
const BTN_BASE = 'btn flex-1 text-sm py-2 rounded-lg font-medium';
const BTN_STOP = BTN_BASE + ' bg-gray-700 hover:bg-red-900 text-gray-400 hover:text-red-300';
const BTN_START = {
  code:   BTN_BASE + ' bg-indigo-700 hover:bg-indigo-600',
  doc:    BTN_BASE + ' bg-cyan-700 hover:bg-cyan-600',
  mentor: BTN_BASE + ' bg-pink-700 hover:bg-pink-600',
};

// ── Poll /api/status — aggiorna dot, label, chunks e testo bottone ──────────
async function poll() {
  try {
    const data = await (await fetch('/api/status')).json();
    let allOk = true;
    for (const [key, s] of Object.entries(data)) {
      const dot   = document.getElementById('dot-'    + key);
      const label = document.getElementById('label-'  + key);
      const btn   = document.getElementById('btn-'    + key);
      const chnk  = document.getElementById('chunks-' + key);
      if (!dot || !btn || btn.disabled) continue;  // skip se mid-action

      if (s.running) {
        dot.className     = 'w-2 h-2 rounded-full bg-green-400';
        label.textContent = '● online';
        label.className   = 'text-xs text-green-400';
        chnk.textContent  = s.chunks + ' chunks indexed';
        btn.textContent   = 'Stop';
        btn.className     = BTN_STOP;
      } else {
        dot.className     = 'w-2 h-2 rounded-full bg-gray-600';
        label.textContent = '○ offline';
        label.className   = 'text-xs text-gray-500';
        chnk.textContent  = '— chunks indexed';
        btn.textContent   = 'Start';
        btn.className     = BTN_START[key];
        allOk = false;
      }
    }
    document.getElementById('footer-status').textContent =
      allOk ? 'Tutti i moduli online ✓' : 'Alcuni moduli offline';
  } catch(e) {
    document.getElementById('footer-status').textContent = 'Errore: ' + e.message;
  }
}

// ── Toggle Start/Stop — fire-and-forget, il poll aggiorna lo stato ──────────
async function toggle(key) {
  const btn     = document.getElementById('btn-' + key);
  const isStart = btn.textContent.trim() === 'Start';
  btn.disabled    = true;
  btn.textContent = isStart ? '⏳ Avvio…' : '⏳ Stop…';
  try {
    await fetch('/api/' + (isStart ? 'start' : 'stop') + '/' + key, { method: 'POST' });
  } catch(e) {
    document.getElementById('footer-status').textContent = 'Errore: ' + e.message;
  }
  btn.disabled = false;
  poll();
}

// ── Start All ────────────────────────────────────────────────────────────────
async function startAll() {
  try { await fetch('/api/start-all', { method: 'POST' }); } catch(e) {}
  poll();
}

// Boot
poll();
setInterval(poll, 4000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(_LAUNCHER_HTML)


# ── Entry point ──────────────────────────────────────────────────────────────
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
