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
  .conv-item { transition: background .12s; }
  .conv-item.active { background: rgba(99,102,241,.22); border-left:3px solid #6366f1; }
  .source-chip { display:inline-flex; align-items:center; gap:4px; background:#f1f5f9;
                 color:#475569; font-size:11px; padding:2px 8px; border-radius:999px;
                 margin:2px; white-space:nowrap; }
  pre  { background:#1e293b; color:#e2e8f0; padding:12px; border-radius:8px;
         overflow-x:auto; font-size:13px; margin:8px 0; }
  code { background:#f1f5f9; padding:1px 5px; border-radius:4px; font-size:13px; }
  pre code { background:transparent; padding:0; }
  .del-btn { opacity:0; transition:opacity .12s; }
  .conv-item:hover .del-btn { opacity:1; }
  .sug { background:#f1f5f9; color:#475569; font-size:13px; padding:6px 16px;
         border-radius:999px; cursor:pointer; transition:.15s; border:none; }
  .sug:hover { background:#e2e8f0; }
  #sidebar { width: 260px; min-width: 260px; }
</style>
</head>
<body class="flex h-screen bg-gray-100 overflow-hidden">

<!-- ═══════════════════════ SIDEBAR ═══════════════════════════════════════ -->
<div id="sidebar" class="bg-gray-900 text-white flex flex-col flex-shrink-0">

  <!-- Logo + module info -->
  <div class="px-4 py-4 border-b border-gray-700/60 flex-shrink-0">
    <div class="flex items-center gap-3 mb-3">
      <span class="text-2xl">🧠</span>
      <div class="min-w-0">
        <p class="font-semibold text-sm text-white truncate" id="module-name">IntelligenceSuite</p>
        <p id="srv-status" class="text-xs text-gray-400">connecting…</p>
      </div>
    </div>
    <div class="bg-gray-800 rounded-lg px-3 py-2 text-xs text-gray-300 flex justify-between">
      <span id="srv-chunks">— chunks</span>
      <span id="srv-llm" class="text-gray-400">—</span>
    </div>
  </div>

  <!-- New Chat button -->
  <div class="px-3 pt-3 pb-1 flex-shrink-0">
    <button onclick="newChat()"
            class="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl
                   bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold
                   transition">
      <span class="text-base leading-none">＋</span> New Chat
    </button>
  </div>

  <!-- Conversation list -->
  <div class="flex-1 overflow-y-auto py-2 px-2">
    <div id="conv-list">
      <p class="text-xs text-gray-600 px-3 py-6 text-center">No conversations yet</p>
    </div>
  </div>

  <!-- Footer -->
  <div class="px-3 py-3 border-t border-gray-700/60 space-y-1 flex-shrink-0">
    <a href="http://localhost:8079" target="_blank"
       class="w-full text-xs text-gray-500 hover:text-gray-300 flex items-center gap-2
              px-3 py-2 rounded-lg hover:bg-gray-800 transition">
      🚀 &nbsp;Launcher
    </a>
    <a href="/docs" target="_blank"
       class="block text-xs text-gray-600 hover:text-gray-400 px-3 py-1 transition">
      API docs →
    </a>
  </div>
</div>

<!-- ═══════════════════════ MAIN ══════════════════════════════════════════ -->
<div class="flex-1 flex flex-col min-w-0">

  <!-- Top bar -->
  <div class="bg-white border-b px-6 py-3 flex items-center justify-between shadow-sm flex-shrink-0">
    <div>
      <h1 class="font-semibold text-gray-800 text-sm" id="module-title">Intelligence Chat</h1>
      <p class="text-xs text-gray-400">Semantic search · Source-cited answers · On-premise</p>
    </div>
    <div class="flex items-center gap-3">
      <div id="dot" class="w-2 h-2 rounded-full bg-gray-300"></div>
      <span id="dot-label" class="text-xs text-gray-400">—</span>
    </div>
  </div>

  <!-- Messages -->
  <div id="messages" class="flex-1 overflow-y-auto px-6 py-6 space-y-5">

    <!-- Welcome (shown when no conversation is active) -->
    <div id="welcome" class="flex flex-col items-center justify-center h-full text-center py-16">
      <div class="text-5xl mb-5">🧠</div>
      <h2 class="text-xl font-semibold text-gray-700 mb-2">Ask anything about your knowledge base</h2>
      <p class="text-sm text-gray-400 max-w-sm mb-8">
        IntelligenceSuite retrieves the most relevant chunks from your indexed codebase
        or documents and generates a precise, source-cited answer — fully on-premise.
      </p>
      <div class="flex flex-wrap gap-2 justify-center" id="suggestions"></div>
    </div>

  </div>

  <!-- Input -->
  <div class="bg-white border-t px-6 py-4 shadow-sm flex-shrink-0">
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

<script>
// ════════════════════════════════════════════════════════════════════════════
//  STATE
// ════════════════════════════════════════════════════════════════════════════
let streaming      = false;
let _module        = 'code';   // resolved from /health
let _moduleInited  = false;
let _currentId     = null;     // active conversation ID (null = no conversation)
let _conversations = [];       // [{id, title, created, messages:[{role,content,sources,meta}]}]

// ════════════════════════════════════════════════════════════════════════════
//  SUGGESTIONS / TITLES
// ════════════════════════════════════════════════════════════════════════════
const SUGGESTIONS = {
  code:   ['Where is authentication handled?',
           'How does the retriever work?',
           'What LLM backends are supported?',
           'How is ChromaDB used?'],
  doc:    ['How are PDF documents parsed?',
           'What file formats are supported?',
           'What is the confidence threshold for escalation?',
           'How do I index a new document folder?'],
  mentor: ['Come inizio il mio onboarding?',
           'Quali strumenti devo installare il primo giorno?',
           'Come funziona il pipeline di embedding?',
           'Spiega l\\'architettura dei tre moduli.'],
};
const MODULE_TITLES = { code:'Code Intelligence', doc:'Doc Intelligence', mentor:'Mentor Intelligence' };
const MODULE_NAMES  = { code:'CodeIntelligence',  doc:'DocIntelligence',  mentor:'MentorIntelligence'  };

// ════════════════════════════════════════════════════════════════════════════
//  LOCALSTORAGE
// ════════════════════════════════════════════════════════════════════════════
function _key()  { return 'is_convs_' + _module; }
function _cidKey() { return 'is_cur_' + _module; }

function _load() {
  try { _conversations = JSON.parse(localStorage.getItem(_key()) || '[]'); }
  catch { _conversations = []; }
  _currentId = localStorage.getItem(_cidKey()) || null;
}

function _save() {
  try {
    localStorage.setItem(_key(), JSON.stringify(_conversations));
    if (_currentId) localStorage.setItem(_cidKey(), _currentId);
    else            localStorage.removeItem(_cidKey());
  } catch {}
}

function _getConv(id) { return _conversations.find(c => c.id === id) || null; }

// ════════════════════════════════════════════════════════════════════════════
//  CONVERSATION MANAGEMENT
// ════════════════════════════════════════════════════════════════════════════
function newChat() {
  _currentId = null;
  _save();
  _showWelcome();
  renderConvList();
}

function _createConv(title) {
  const conv = { id: 'c' + Date.now(), title: title.slice(0,45) + (title.length>45?'…':''),
                 created: Date.now(), messages: [] };
  _conversations.unshift(conv);
  _currentId = conv.id;
  _save();
  return conv;
}

function loadConv(id) {
  _currentId = id;
  _save();
  const conv = _getConv(id);
  if (!conv) { newChat(); return; }

  // Clear messages area and re-render stored messages
  _clearMessages();
  for (const msg of conv.messages) {
    if (msg.role === 'user') {
      _appendUserBubble(msg.content);
    } else {
      _appendAssistantBubble(msg.content, msg.sources || [], msg.meta || {});
    }
  }
  renderConvList();
}

function deleteConv(id, evt) {
  evt.stopPropagation();
  _conversations = _conversations.filter(c => c.id !== id);
  if (_currentId === id) { _currentId = null; _showWelcome(); }
  _save();
  renderConvList();
}

// ════════════════════════════════════════════════════════════════════════════
//  SIDEBAR RENDER
// ════════════════════════════════════════════════════════════════════════════
function renderConvList() {
  const el = document.getElementById('conv-list');
  if (!_conversations.length) {
    el.innerHTML = '<p class="text-xs text-gray-600 px-3 py-6 text-center">No conversations yet</p>';
    return;
  }

  // Group by date
  const now       = Date.now();
  const today     = new Date(); today.setHours(0,0,0,0);
  const todayMs   = today.getTime();
  const yesterMs  = todayMs - 86400000;
  const weekMs    = todayMs - 7*86400000;

  const groups = [['Today',[]], ['Yesterday',[]], ['This week',[]], ['Older',[]]];
  for (const c of _conversations) {
    if      (c.created >= todayMs)  groups[0][1].push(c);
    else if (c.created >= yesterMs) groups[1][1].push(c);
    else if (c.created >= weekMs)   groups[2][1].push(c);
    else                            groups[3][1].push(c);
  }

  let html = '';
  for (const [label, convs] of groups) {
    if (!convs.length) continue;
    html += `<p class="text-[10px] text-gray-500 uppercase tracking-widest px-3 mt-3 mb-1 select-none">${label}</p>`;
    for (const c of convs) {
      const active = c.id === _currentId;
      html += `
        <div class="conv-item relative flex items-center rounded-lg mb-0.5 cursor-pointer pr-1
                    ${active ? 'active pl-[9px]' : 'pl-3 hover:bg-gray-800'}"
             onclick="loadConv('${c.id}')">
          <span class="flex-1 text-xs text-gray-300 py-2 leading-relaxed truncate pr-6">
            ${esc(c.title)}
          </span>
          <button onclick="deleteConv('${c.id}',event)"
                  class="del-btn absolute right-2 text-gray-600 hover:text-red-400
                         text-[11px] px-1 py-1 leading-none rounded">✕</button>
        </div>`;
    }
  }
  el.innerHTML = html;
}

// ════════════════════════════════════════════════════════════════════════════
//  MESSAGE RENDERING HELPERS
// ════════════════════════════════════════════════════════════════════════════
function _clearMessages() {
  document.getElementById('messages').innerHTML = '';
}

function _showWelcome() {
  _clearMessages();
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
  renderSuggestions(_module);
}

function _appendUserBubble(text) {
  document.getElementById('messages').insertAdjacentHTML('beforeend', `
    <div class="flex justify-end">
      <div class="bg-indigo-600 text-white rounded-2xl rounded-tr-sm
                  px-4 py-3 max-w-2xl text-sm leading-relaxed shadow-sm">
        ${esc(text)}
      </div>
    </div>`);
  _scroll();
}

function _appendAssistantBubble(text, sources, meta) {
  const id = 'a' + Date.now() + Math.random().toString(36).slice(2,6);
  document.getElementById('messages').insertAdjacentHTML('beforeend', `
    <div class="flex gap-3 items-start">
      <div class="w-8 h-8 rounded-full bg-indigo-100 flex items-center
                  justify-center flex-shrink-0 text-base shadow-sm">🧠</div>
      <div class="flex-1 min-w-0">
        <div class="bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm border border-gray-100">
          <div class="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">${esc(text)}</div>
        </div>
        <div class="mt-2 flex flex-wrap">
          ${(sources||[]).map(s =>
            `<span class="source-chip">📎 ${esc(s.source)} · ${esc(s.type)} · ${s.score.toFixed(3)}</span>`
          ).join('')}
        </div>
        ${meta && Object.keys(meta).length ? `
        <div class="mt-1 text-xs text-gray-400 px-1">
          ${[meta.ms ? '⏱ '+meta.ms+'ms' : '',
             meta.confidence != null ? '🎯 '+meta.confidence.toFixed(2) : '',
             meta.backend ? '🤖 '+meta.backend : '',
             meta.escalated ? '🔺 escalated' : ''].filter(Boolean).join(' · ')}
        </div>` : ''}
      </div>
    </div>`);
  _scroll();
}

// ════════════════════════════════════════════════════════════════════════════
//  HEALTH CHECK + BOOT
// ════════════════════════════════════════════════════════════════════════════
function renderSuggestions(mod) {
  const el = document.getElementById('suggestions');
  if (!el) return;
  el.innerHTML = (SUGGESTIONS[mod] || SUGGESTIONS.code).map(s =>
    `<button class="sug" onclick="useSuggestion(this)">${esc(s)}</button>`
  ).join('');
}

async function checkHealth() {
  try {
    const d = await (await fetch('/health')).json();
    _set('srv-status', '● online',  'text-xs text-green-400');
    _set('srv-chunks', (d.chunks_indexed||0) + ' chunks');
    _set('srv-llm',    d.llm_backend || '—', 'text-xs text-gray-400');
    _set('dot',        '', 'w-2 h-2 rounded-full bg-green-400');
    _set('dot-label',  (d.llm_backend||'?') + ' · ' + (d.chunks_indexed||0) + ' chunks',
                       'text-xs text-green-600');
    if (!_moduleInited) {
      _module = d.module || 'code';
      document.getElementById('module-title').textContent = MODULE_TITLES[_module] || 'Intelligence Chat';
      document.getElementById('module-name').textContent  = MODULE_NAMES[_module]  || 'IntelligenceSuite';
      _moduleInited = true;
      _load();                  // load conversations for this module from localStorage
      renderConvList();
      // If there was an active conversation, restore it; otherwise show welcome
      if (_currentId && _getConv(_currentId)) {
        loadConv(_currentId);
      } else {
        renderSuggestions(_module);
      }
    }
  } catch {
    _set('srv-status', '● offline', 'text-xs text-red-400');
    _set('dot', '',                  'w-2 h-2 rounded-full bg-red-400');
    _set('dot-label', 'offline',     'text-xs text-red-500');
  }
}

(async function boot() {
  await checkHealth();
  setInterval(checkHealth, 20000);
})();

// ════════════════════════════════════════════════════════════════════════════
//  FORM SUBMIT
// ════════════════════════════════════════════════════════════════════════════
// NOTE: addEventListener instead of onsubmit="..." to avoid the HTMLFormElement
// .submit shadow bug that causes a page reload instead of calling our handler.
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
  const q = btn.textContent.trim();
  if (!q || streaming) return;
  document.getElementById('q').value = '';
  sendMessage(q);
}

// ════════════════════════════════════════════════════════════════════════════
//  STREAMING
// ════════════════════════════════════════════════════════════════════════════
async function sendMessage(question) {
  streaming = true;
  document.getElementById('send').disabled = true;
  document.getElementById('welcome')?.remove();

  // Create / reuse conversation
  if (!_currentId) {
    _createConv(question);
    renderConvList();
  }

  // Save user message immediately
  const conv = _getConv(_currentId);
  if (conv) conv.messages.push({ role:'user', content:question });
  _save();

  // User bubble
  _appendUserBubble(question);

  // Streaming assistant bubble
  const bubbleId = 'a' + Date.now();
  document.getElementById('messages').insertAdjacentHTML('beforeend', `
    <div id="${bubbleId}" class="flex gap-3 items-start">
      <div class="w-8 h-8 rounded-full bg-indigo-100 flex items-center
                  justify-center flex-shrink-0 text-base shadow-sm">🧠</div>
      <div class="flex-1 min-w-0">
        <div class="bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm border border-gray-100">
          <div id="${bubbleId}-txt" class="text-sm text-gray-700 leading-relaxed cursor whitespace-pre-wrap"></div>
        </div>
        <div id="${bubbleId}-src" class="mt-2 flex flex-wrap"></div>
        <div id="${bubbleId}-meta" class="mt-1 text-xs text-gray-400 px-1"></div>
      </div>
    </div>`);
  _scroll();

  const txtEl  = document.getElementById(bubbleId + '-txt');
  const srcEl  = document.getElementById(bubbleId + '-src');
  const metaEl = document.getElementById(bubbleId + '-meta');

  let answer = '', sources = [], meta = {};
  const t0 = Date.now();

  try {
    const res = await fetch('/api/v1/stream', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({question, top_k:5, min_score:0.3})
    });
    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

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
            _scroll();
          } else if (d.type === 'sources') {
            sources = d.sources;
          } else if (d.type === 'meta') {
            meta = d;
          } else if (d.type === 'done') {
            _finalize();
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

  function _finalize() {
    txtEl.classList.remove('cursor');
    const ms = Date.now() - t0;

    // Sources
    if (sources.length) {
      srcEl.innerHTML = sources.map(s =>
        `<span class="source-chip">📎 ${esc(s.source)} · ${esc(s.type)} · ${s.score.toFixed(3)}</span>`
      ).join('');
    }

    // Meta
    const metaParts = [`⏱ ${ms}ms`];
    if (meta.confidence != null) metaParts.push(`🎯 ${meta.confidence.toFixed(2)}`);
    if (meta.backend)            metaParts.push(`🤖 ${meta.backend}`);
    if (meta.escalated)          metaParts.push('🔺 escalated');
    metaEl.textContent = metaParts.join(' · ');

    // Persist assistant message to conversation
    const convNow = _getConv(_currentId);
    if (convNow) {
      convNow.messages.push({
        role:'assistant', content:answer, sources,
        meta:{ ms, confidence:meta.confidence, backend:meta.backend, escalated:meta.escalated }
      });
      _save();
    }

    streaming = false;
    document.getElementById('send').disabled = false;
  }
}

// ════════════════════════════════════════════════════════════════════════════
//  UTILITIES
// ════════════════════════════════════════════════════════════════════════════
function _scroll() {
  const el = document.getElementById('messages');
  el.scrollTop = el.scrollHeight;
}

function _set(id, text, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  if (text !== '') el.textContent = text;
  if (cls)         el.className   = cls;
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
</script>
</body>
</html>"""
