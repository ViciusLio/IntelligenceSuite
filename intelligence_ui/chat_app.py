"""
IntelligenceSuite — Streamlit Chat UI  [DEPRECATED]
=====================================================
.. deprecated::
    This Streamlit interface is superseded by the built-in streaming chat UI
    served directly from each RAG server at http://localhost:808x/.
    The built-in UI requires no extra dependencies, streams responses token
    by token, and adapts its suggestions to each module (code / doc / mentor).

    This file is kept for reference only and will be removed in a future release.

Streamlit chat interface for CodeIntelligence, DocIntelligence, MentorIntelligence.

Run:
    pip install streamlit
    streamlit run intelligence_ui/chat_app.py
"""

from __future__ import annotations
import streamlit as st
import httpx
import time

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="IntelligenceSuite Chat",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Module config ─────────────────────────────────────────────────────────────
MODULES = {
    "💻 Code Intelligence":  {"url": "http://localhost:8080", "domain": "code",   "color": "#4CAF50"},
    "📄 Doc Intelligence":   {"url": "http://localhost:8081", "domain": "doc",    "color": "#2196F3"},
    "🎓 Mentor Intelligence": {"url": "http://localhost:8082", "domain": "mentor", "color": "#FF9800"},
}

# ── Session state init ────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []          # list of {role, content, sources, meta}
if "selected_turn" not in st.session_state:
    st.session_state.selected_turn = None   # index of turn shown in sidebar detail

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧠 IntelligenceSuite")
    st.markdown("---")

    # Module selector
    module_name = st.selectbox(
        "Module",
        list(MODULES.keys()),
        index=0,
        label_visibility="collapsed",
    )
    module = MODULES[module_name]

    # Server status
    try:
        r = httpx.get(f"{module['url']}/health", timeout=2.0)
        info = r.json()
        st.success(f"✅ Server online — {info.get('chunks_indexed', 0)} chunks indexed")
        st.caption(f"LLM: {info.get('llm_backend', '?')} {'✅' if info.get('llm_available') else '⚠️'}")
    except Exception:
        st.error("⚠️ Server offline — run the serve command first")
        st.code({"💻 Code Intelligence": "ci-serve",
                 "📄 Doc Intelligence":  "di-serve",
                 "🎓 Mentor Intelligence": "mi-serve"}[module_name])

    st.markdown("---")

    # Conversation history — clickable turns
    turns = [(i, st.session_state.messages[i])
             for i in range(0, len(st.session_state.messages), 2)
             if i + 1 < len(st.session_state.messages)]

    if turns:
        st.markdown(f"**History** ({len(turns)} turns)")
        for idx, (i, msg) in enumerate(turns):
            q_short = msg["content"][:45] + "…" if len(msg["content"]) > 45 else msg["content"]
            is_selected = st.session_state.selected_turn == i
            label = f"{'▶ ' if is_selected else ''}{idx + 1}. {q_short}"
            if st.button(label, key=f"turn_{i}", use_container_width=True):
                st.session_state.selected_turn = None if is_selected else i

        # Show selected turn detail
        if st.session_state.selected_turn is not None:
            t = st.session_state.selected_turn
            if t + 1 < len(st.session_state.messages):
                st.markdown("---")
                st.markdown("**Question**")
                st.info(st.session_state.messages[t]["content"])
                ans = st.session_state.messages[t + 1]
                st.markdown("**Answer**")
                st.success(ans["content"][:400] + ("…" if len(ans["content"]) > 400 else ""))
                if ans.get("sources"):
                    st.markdown("**Sources**")
                    for s in ans["sources"][:3]:
                        st.caption(f"📎 {s['source']} ({s['type']}) — score {s['score']:.3f}")
                if ans.get("meta"):
                    meta = ans["meta"]
                    st.caption(f"⏱ {meta.get('latency_ms', 0):.0f} ms · "
                               f"conf {meta.get('confidence', 0):.2f} · "
                               f"{meta.get('backend', '?')}"
                               f"{' · 🔺 escalated' if meta.get('escalated') else ''}")
    else:
        st.caption("No conversations yet.")

    st.markdown("---")
    if st.button("🗑 Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.selected_turn = None
        st.rerun()

# ── Main chat area ────────────────────────────────────────────────────────────
st.markdown(f"### {module_name}")
st.markdown("---")

# Render existing messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander(f"📎 {len(msg['sources'])} sources", expanded=False):
                for s in msg["sources"]:
                    st.markdown(
                        f"**{s['source']}** &nbsp;·&nbsp; `{s['type']}` &nbsp;·&nbsp; "
                        f"score `{s['score']:.3f}`"
                    )
        if msg.get("meta"):
            meta = msg["meta"]
            cols = st.columns(4)
            cols[0].caption(f"⏱ {meta.get('latency_ms', 0):.0f} ms")
            cols[1].caption(f"🎯 conf {meta.get('confidence', 0):.2f}")
            cols[2].caption(f"🤖 {meta.get('backend', '?')}")
            if meta.get("escalated"):
                cols[3].caption("🔺 escalated")

# ── Chat input ────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask anything about your codebase or documents…"):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Query the server
    with st.chat_message("assistant"):
        with st.spinner("Searching…"):
            try:
                resp = httpx.post(
                    f"{module['url']}/api/v1/query",
                    json={
                        "question": prompt,
                        "top_k":    5,
                        "domain":   module["domain"],
                        "min_score": 0.3,
                    },
                    timeout=120.0,
                )
                resp.raise_for_status()
                data = resp.json()

                answer  = data["answer"]
                sources = data.get("sources", [])
                meta    = {
                    "latency_ms":  data.get("latency_ms", 0),
                    "confidence":  data.get("confidence", 0),
                    "backend":     data.get("backend", "?"),
                    "escalated":   data.get("escalated", False),
                }

                st.markdown(answer)

                if sources:
                    with st.expander(f"📎 {len(sources)} sources", expanded=False):
                        for s in sources:
                            st.markdown(
                                f"**{s['source']}** &nbsp;·&nbsp; `{s['type']}` &nbsp;·&nbsp; "
                                f"score `{s['score']:.3f}`"
                            )

                cols = st.columns(4)
                cols[0].caption(f"⏱ {meta['latency_ms']:.0f} ms")
                cols[1].caption(f"🎯 conf {meta['confidence']:.2f}")
                cols[2].caption(f"🤖 {meta['backend']}")
                if meta["escalated"]:
                    cols[3].caption("🔺 escalated")

            except httpx.ConnectError:
                answer  = f"⚠️ Cannot connect to {module['url']}. Start the server first."
                sources = []
                meta    = {}
                st.error(answer)
            except Exception as e:
                answer  = f"⚠️ Error: {e}"
                sources = []
                meta    = {}
                st.error(answer)

    # Save assistant message
    st.session_state.messages.append({
        "role":    "assistant",
        "content": answer,
        "sources": sources,
        "meta":    meta,
    })
