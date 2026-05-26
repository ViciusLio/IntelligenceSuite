"""HTML template for the IntelligenceSuite chat interface."""

CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IntelligenceSuite</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
  .cursor::after { content:'▌'; animation:blink 1s infinite; color:#6366f1; margin-left:1px; }
  #messages { scroll-behavior: smooth; }
  .history-btn { transition: all .15s; }
  .history-btn:hover { background: rgba(255,255,255,.08); }
  .history-btn.active { background: rgba(99,102,241,.25); border-left: 3px solid #6366f1; padding-left: 9px; }
  .source-chip { display:inline-flex; align-items:center; gap:4px; background:#f1f5f9;
                 color:#475569; font-size:11px; padding:2px 8px; border-radius:999px;
                 margin:2px; white-space:nowrap; }
  pre { background:#1e293b; color:#e2e8f0; padding:12px; border-radius:8px;
        overflow-x:auto; font-size:13px; margin:8px 0; }
  code { background:#f1f5f9; padding:1px 5px; border-radius:4px; font-size:13px; }
  pre code { background:transparent; padding:0; }
</style>
</head>
<body class="flex h-screen bg-gray-100 overflow-hidden">

<!-- ── SIDEBAR ─────────────────────────────────────────────────────────── -->
<div class="w-72 bg-gray-900 text-white flex flex-col flex-shrink-0">

  <!-- Logo -->
  <div class="px-5 py-4 border-b border-gray-700/60">
    <div class="flex items-center gap-3 mb-3">
      <span class="text-2xl">🧠</span>
      <div>
        <p class="font-semibold text-sm text-white">IntelligenceSuite</p>
        <p id="srv-status" class="text-xs text-gray-400">connecting…</p>
      </div>
    </div>
    <div class="bg-gray-800 rounded-lg px-3 py-2 text-xs text-gray-300 flex justify-between">
      <span id="srv-chunks">— chunks</span>
      <span id="srv-llm" class="text-gray-400">—</span>
    </div>
  </div>

  <!-- History -->
  <div class="flex-1 overflow-y-auto py-3 px-2">
    <p class="text-[10px] text-gray-500 uppercase tracking-widest px-3 mb-2">History</p>
    <div id="history-list">
      <p class="text-xs text-gray-600 px-3 py-6 text-center">No conversations yet</p>
    </div>
  </div>

  <!-- Footer -->
  <div class="px-3 py-3 border-t border-gray-700/60 space-y-1">
    <button onclick="clearAll()"
            class="w-full text-xs text-gray-400 hover:text-white flex items-center gap-2
                   px-3 py-2 rounded-lg hover:bg-gray-800 transition">
      🗑 &nbsp;Clear conversation
    </button>
    <a href="/docs" target="_blank"
       class="block text-xs text-gray-600 hover:text-gray-400 px-3 py-1 transition">
      API docs →
    </a>
  </div>
</div>

<!-- ── MAIN ────────────────────────────────────────────────────────────── -->
<div class="flex-1 flex flex-col min-w-0">

  <!-- Top bar -->
  <div class="bg-white border-b px-6 py-3 flex items-center justify-between shadow-sm">
    <div>
      <h1 class="font-semibold text-gray-800 text-sm" id="module-title">Intelligence Chat</h1>
      <p class="text-xs text-gray-400">Semantic search · Source-cited answers · On-premise</p>
    </div>
    <div class="flex items-center gap-2">
      <div id="dot" class="w-2 h-2 rounded-full bg-gray-300"></div>
      <span id="dot-label" class="text-xs text-gray-400">—</span>
    </div>
  </div>

  <!-- Messages -->
  <div id="messages" class="flex-1 overflow-y-auto px-6 py-6 space-y-5">

    <!-- Welcome -->
    <div id="welcome" class="flex flex-col items-center justify-center h-full text-center py-16">
      <div class="text-5xl mb-5">🧠</div>
      <h2 class="text-xl font-semibold text-gray-700 mb-2">Ask anything about your knowledge base</h2>
      <p class="text-sm text-gray-400 max-w-sm mb-8">
        IntelligenceSuite retrieves the most relevant chunks from your indexed codebase
        or documents and generates a precise, source-cited answer — fully on-premise.
      </p>
      <!-- Suggestion pills — populated dynamically from /health module field -->
      <div class="flex flex-wrap gap-2 justify-center" id="suggestions"></div>
    </div>

  </div>

  <!-- Input -->
  <div class="bg-white border-t px-6 py-4 shadow-sm">
    <form id="chat-form" class="flex gap-3">
      <input id="q" type="text" autocomplete="off"
             placeholder="Ask anything about your codebase or documents…"
             class="flex-1 bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-sm
                    focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent">
      <button type="submit" id="send"
              class="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white
                     px-5 py-3 rounded-xl text-sm font-medium transition">
        Send →
      </button>
    </form>
    <p class="text-xs text-gray-400 text-center mt-2">
      Powered by IntelligenceSuite · Responses stream in real-time
    </p>
  </div>
</div>

<style>
  .sug { background:#f1f5f9; color:#475569; font-size:13px; padding:6px 16px;
         border-radius:999px; cursor:pointer; transition:.15s; border:none; }
  .sug:hover { background:#e2e8f0; }
</style>

<script>
// ── State ──────────────────────────────────────────────────────────────────
const turns   = [];       // {q, a, sources, ms, conf, backend, escalated}
let streaming     = false;
let activeTurn    = null;
let _moduleInited = false;
let _currentModule = 'code';   // set by checkHealth, used by clearAll

// ── Module suggestions ─────────────────────────────────────────────────────
const SUGGESTIONS = {
  code: [
    'Where is authentication handled?',
    'How does the retriever work?',
    'What LLM backends are supported?',
    'How is ChromaDB used?',
  ],
  doc: [
    'How are PDF documents parsed?',
    'What file formats are supported?',
    'How do I search for a specific topic?',
    'Where is the document indexing configured?',
  ],
  mentor: [
    'What is my onboarding path?',
    'How do I get started with the codebase?',
    'What resources are available for my role?',
    'Show me the architecture overview.',
  ],
};

const MODULE_TITLES = {
  code:   'Code Intelligence',
  doc:    'Doc Intelligence',
  mentor: 'Mentor Intelligence',
};

function renderSuggestions(module) {
  const sugs = SUGGESTIONS[module] || SUGGESTIONS.code;
  const el = document.getElementById('suggestions');
  if (!el) return;
  el.innerHTML = sugs.map(s =>
    `<button class="sug" onclick="useSuggestion(this)">${esc(s)}</button>`
  ).join('');
}

// ── Boot ───────────────────────────────────────────────────────────────────
(async function boot() {
  await checkHealth();
  setInterval(checkHealth, 20000);
})();

async function checkHealth() {
  try {
    const d = await (await fetch('/health')).json();
    set('srv-status',  '● online',           'text-xs text-green-400');
    set('srv-chunks',  (d.chunks_indexed||0) + ' chunks');
    set('srv-llm',     d.llm_backend || '—', 'text-xs text-gray-400');
    set('dot',         '',                    'w-2 h-2 rounded-full bg-green-400');
    set('dot-label',   (d.llm_backend||'?') + ' · ' + (d.chunks_indexed||0) + ' chunks', 'text-xs text-green-600');
    // Set module title + suggestions once (fallback to 'code' for older servers)
    if (!_moduleInited) {
      _currentModule = d.module || 'code';
      document.getElementById('module-title').textContent =
        MODULE_TITLES[_currentModule] || 'Intelligence Chat';
      renderSuggestions(_currentModule);
      _moduleInited = true;
    }
  } catch {
    set('srv-status', '● offline', 'text-xs text-red-400');
    set('dot', '',                  'w-2 h-2 rounded-full bg-red-400');
    set('dot-label', 'offline',     'text-xs text-red-500');
  }
}

// ── Submit ─────────────────────────────────────────────────────────────────
// NOTE: we use addEventListener, NOT onsubmit="...", because 'submit' is a
// reserved method on HTMLFormElement — inline handlers would call form.submit()
// (page reload) instead of our function.
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('chat-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const q = document.getElementById('q').value.trim();
    if (!q || streaming) return;
    document.getElementById('q').value = '';
    sendMessage(q);
  });
});

function useSuggestion(btn) {
  // Call sendMessage directly — do NOT dispatch a 'submit' event (same conflict)
  const q = btn.textContent.trim();
  if (!q || streaming) return;
  document.getElementById('q').value = '';
  sendMessage(q);
}

// ── Streaming ──────────────────────────────────────────────────────────────
async function sendMessage(question) {
  streaming = true;
  document.getElementById('send').disabled = true;
  document.getElementById('welcome')?.remove();

  const msgs = document.getElementById('messages');

  // User bubble
  msgs.insertAdjacentHTML('beforeend', `
    <div class="flex justify-end">
      <div class="bg-indigo-600 text-white rounded-2xl rounded-tr-sm
                  px-4 py-3 max-w-2xl text-sm leading-relaxed shadow-sm">
        ${esc(question)}
      </div>
    </div>`);

  // Assistant bubble
  const id = 'a' + Date.now();
  msgs.insertAdjacentHTML('beforeend', `
    <div id="${id}" class="flex gap-3 items-start">
      <div class="w-8 h-8 rounded-full bg-indigo-100 flex items-center
                  justify-center flex-shrink-0 text-base shadow-sm">🧠</div>
      <div class="flex-1 min-w-0">
        <div class="bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm border border-gray-100">
          <div id="${id}-txt" class="text-sm text-gray-700 leading-relaxed cursor whitespace-pre-wrap"></div>
        </div>
        <div id="${id}-src" class="mt-2 flex flex-wrap"></div>
        <div id="${id}-meta" class="mt-1 text-xs text-gray-400 px-1"></div>
      </div>
    </div>`);
  scroll();

  const txtEl  = document.getElementById(id + '-txt');
  const srcEl  = document.getElementById(id + '-src');
  const metaEl = document.getElementById(id + '-meta');

  let answer='', sources=[], meta={};
  const t0 = Date.now();

  try {
    const res = await fetch('/api/v1/stream', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({question, top_k:5, min_score:0.3})
    });

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buf     = '';

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});
      const lines = buf.split('\\n');
      buf = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const d = JSON.parse(line.slice(6));
          if (d.type === 'token') {
            answer += d.token;
            txtEl.textContent = answer;
            scroll();
          } else if (d.type === 'sources') {
            sources = d.sources;
          } else if (d.type === 'meta') {
            meta = d;
          } else if (d.type === 'done') {
            finalize();
          } else if (d.type === 'error') {
            txtEl.textContent = '⚠️ ' + d.error;
            txtEl.classList.remove('cursor');
          }
        } catch {}
      }
    }
  } catch(err) {
    txtEl.textContent = '⚠️ Connection error: ' + err.message;
    txtEl.classList.remove('cursor');
  }

  function finalize() {
    txtEl.classList.remove('cursor');

    // Sources chips
    if (sources.length) {
      srcEl.innerHTML = sources.map(s =>
        `<span class="source-chip">📎 ${esc(s.source)} · ${esc(s.type)} · ${s.score.toFixed(3)}</span>`
      ).join('');
    }

    // Meta line
    const ms = Date.now() - t0;
    const parts = [`⏱ ${ms}ms`];
    if (meta.confidence != null) parts.push(`🎯 ${meta.confidence.toFixed(2)}`);
    if (meta.backend)            parts.push(`🤖 ${meta.backend}`);
    if (meta.escalated)          parts.push('🔺 escalated');
    metaEl.textContent = parts.join(' · ');

    // Add to sidebar
    turns.push({q: question, a: answer, sources, ms,
                conf: meta.confidence, backend: meta.backend, escalated: meta.escalated});
    renderHistory();
    streaming = false;
    document.getElementById('send').disabled = false;
  }
}

// ── History sidebar ─────────────────────────────────────────────────────────
function renderHistory() {
  const el = document.getElementById('history-list');
  if (!turns.length) {
    el.innerHTML = '<p class="text-xs text-gray-600 px-3 py-6 text-center">No conversations yet</p>';
    return;
  }
  el.innerHTML = turns.map((t, i) => {
    const short = t.q.length > 36 ? t.q.slice(0,36) + '…' : t.q;
    const active = activeTurn === i;
    return `<button onclick="selectTurn(${i})"
              class="history-btn w-full text-left px-3 py-2 rounded-lg mb-0.5 ${active?'active':''}">
              <div class="flex gap-2 items-start">
                <span class="text-indigo-400 text-[11px] font-bold mt-0.5 flex-shrink-0">${i+1}</span>
                <span class="text-gray-300 text-xs leading-relaxed">${esc(short)}</span>
              </div>
            </button>`;
  }).join('');
}

function selectTurn(i) {
  activeTurn = activeTurn === i ? null : i;
  renderHistory();
}

function clearAll() {
  turns.length = 0;
  activeTurn   = null;
  streaming    = false;
  document.getElementById('messages').innerHTML = `
    <div id="welcome" class="flex flex-col items-center justify-center h-full text-center py-16">
      <div class="text-5xl mb-5">🧠</div>
      <h2 class="text-xl font-semibold text-gray-700 mb-2">Ask anything about your knowledge base</h2>
      <p class="text-sm text-gray-400 max-w-sm mb-8">
        IntelligenceSuite retrieves the most relevant chunks and generates a precise,
        source-cited answer — fully on-premise.
      </p>
      <div class="flex flex-wrap gap-2 justify-center" id="suggestions"></div>
    </div>`;
  renderSuggestions(_currentModule);   // re-populate pills after clearing
  renderHistory();
  document.getElementById('send').disabled = false;
}

// ── Helpers ────────────────────────────────────────────────────────────────
function scroll() {
  const el = document.getElementById('messages');
  el.scrollTop = el.scrollHeight;
}

function set(id, text, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  if (text !== '') el.textContent = text;
  if (cls)         el.className = cls;
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
</script>
</body>
</html>"""
