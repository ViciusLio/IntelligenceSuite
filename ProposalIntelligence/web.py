"""UI HTML minimale per ProposalIntelligence (servita da ``pi-serve`` su ``/``).

Single-page: incolli le domande (una per riga), scegli la modalità e il numero
di esempi di stile, e ottieni le risposte generate — con le fonti di stile.
Tutto via ``POST /api/v1/proposal/answer``; nessuna dipendenza esterna oltre a
Tailwind via CDN.
"""

PROPOSAL_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ProposalIntelligence</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  .pulse { animation: pulse 1.2s infinite; }
  .ans { white-space: pre-wrap; }
  .chip { display:inline-flex; align-items:center; gap:4px; background:#1e293b;
          color:#94a3b8; font-size:11px; padding:2px 8px; border-radius:999px;
          margin:2px 4px 2px 0; white-space:nowrap; }
</style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen flex flex-col">

<header class="border-b border-gray-800 px-8 py-5 flex items-center gap-4">
  <span class="text-3xl">📝</span>
  <div class="flex-1">
    <h1 class="text-lg font-bold tracking-tight" style="color:#a78bfa">ProposalIntelligence</h1>
    <p class="text-xs text-gray-500">Risposte a questionari / gare nel tuo stile aziendale</p>
  </div>
  <div class="text-right text-xs">
    <div id="status" class="text-gray-500">verifico…</div>
    <div id="meta" class="text-gray-600 font-mono mt-0.5"></div>
  </div>
</header>

<main class="flex-1 w-full max-w-5xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-5 gap-6">

  <!-- Form -->
  <section class="lg:col-span-2 flex flex-col gap-4">
    <div>
      <label class="block text-xs text-gray-400 mb-1 font-semibold">Domande (una per riga)</label>
      <textarea id="questions" rows="10"
        class="w-full bg-gray-900 border border-gray-800 rounded-xl p-3 text-sm
               focus:outline-none focus:border-violet-600 resize-y"
        placeholder="Avete esperienza in progetti di migrazione cloud?&#10;Garantite la conformità alle normative di sicurezza?&#10;È previsto un servizio di assistenza continuativa?"></textarea>
    </div>

    <div class="flex gap-4">
      <div class="flex-1">
        <label class="block text-xs text-gray-400 mb-1 font-semibold">Modalità</label>
        <select id="mode"
          class="w-full bg-gray-900 border border-gray-800 rounded-xl p-2.5 text-sm
                 focus:outline-none focus:border-violet-600">
          <option value="anchored">anchored — fedele al corpus</option>
          <option value="commercial">commercial — più assertiva</option>
        </select>
      </div>
      <div class="w-24">
        <label class="block text-xs text-gray-400 mb-1 font-semibold">Esempi (top-k)</label>
        <input id="topk" type="number" min="1" max="10" value="4"
          class="w-full bg-gray-900 border border-gray-800 rounded-xl p-2.5 text-sm
                 focus:outline-none focus:border-violet-600">
      </div>
    </div>

    <button id="run" onclick="run()"
      class="bg-violet-700 hover:bg-violet-600 disabled:opacity-40 disabled:cursor-not-allowed
             text-sm py-3 rounded-xl font-semibold transition">
      Genera risposte
    </button>
    <p class="text-xs text-gray-600 leading-relaxed">
      Le risposte sono ancorate al corpus Q&A indicizzato (<code>pi-ingest</code> +
      <code>pi-embed</code>). Le fonti di stile recuperate sono mostrate sotto ogni risposta.
    </p>
  </section>

  <!-- Risultati -->
  <section id="results" class="lg:col-span-3 flex flex-col gap-4">
    <div id="placeholder" class="text-gray-600 text-sm border border-dashed border-gray-800
                                  rounded-2xl p-10 text-center">
      Le risposte generate compariranno qui.
    </div>
  </section>

</main>

<footer class="border-t border-gray-800 px-8 py-3 text-center text-xs text-gray-600">
  ProposalIntelligence · IntelligenceSuite
</footer>

<script>
const API = location.origin;

async function health() {
  try {
    const r = await fetch(API + '/health', { signal: AbortSignal.timeout(4000) });
    const d = await r.json();
    document.getElementById('status').textContent = '● online';
    document.getElementById('status').className = 'text-green-400';
    document.getElementById('meta').textContent =
      (d.chunks_indexed || 0) + ' coppie · ' + (d.llm_backend || '—');
    const sel = document.getElementById('mode');
    if (d.default_mode) sel.value = d.default_mode;
  } catch {
    document.getElementById('status').textContent = '○ offline';
    document.getElementById('status').className = 'text-gray-500';
  }
}

function esc(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function render(data) {
  const box = document.getElementById('results');
  box.innerHTML = '';
  if (!data.answers || !data.answers.length) {
    box.innerHTML = '<div class="text-gray-500 text-sm p-6">Nessuna risposta.</div>';
    return;
  }
  const head = document.createElement('div');
  head.className = 'text-xs text-gray-500';
  head.textContent = 'Modalità: ' + data.mode + ' · backend: ' + data.backend
                     + ' · ' + data.answers.length + ' risposte';
  box.appendChild(head);

  data.answers.forEach((a, i) => {
    const card = document.createElement('div');
    card.className = 'bg-gray-900 border border-gray-800 rounded-2xl p-5';
    const sources = (a.sources || []).map(s =>
      '<span class="chip">' + esc(s.source || '?')
      + (s.score != null ? ' · ' + Number(s.score).toFixed(2) : '') + '</span>'
    ).join('');
    card.innerHTML =
      '<div class="text-sm font-semibold text-violet-300 mb-2">'
        + (i + 1) + '. ' + esc(a.question) + '</div>'
      + '<div class="ans text-sm text-gray-200 leading-relaxed">' + esc(a.answer) + '</div>'
      + (sources ? '<div class="mt-3 pt-3 border-t border-gray-800">'
          + '<div class="text-[10px] uppercase tracking-wide text-gray-600 mb-1">Fonti di stile</div>'
          + sources + '</div>' : '');
    box.appendChild(card);
  });
}

async function run() {
  const raw = document.getElementById('questions').value;
  const questions = raw.split('\\n').map(s => s.trim()).filter(Boolean);
  if (!questions.length) return;

  const btn = document.getElementById('run');
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = 'Genero…';
  btn.classList.add('pulse');

  const box = document.getElementById('results');
  box.innerHTML = '<div class="text-gray-500 text-sm p-6 pulse">Genero ' + questions.length
                  + ' risposte…</div>';

  try {
    const r = await fetch(API + '/api/v1/proposal/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        questions,
        mode: document.getElementById('mode').value,
        top_k: parseInt(document.getElementById('topk').value, 10) || null,
      }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    render(await r.json());
  } catch (e) {
    box.innerHTML = '<div class="text-red-400 text-sm p-6">Errore: ' + esc(String(e))
                    + '<br><span class="text-gray-500">Server avviato e corpus indicizzato?</span></div>';
  } finally {
    btn.disabled = false;
    btn.textContent = old;
    btn.classList.remove('pulse');
  }
}

health();
</script>
</body>
</html>
"""
