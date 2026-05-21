"""GodBot command center: chat-first UI, file export, and mission control."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import streamlit as st

from agents import DEFAULT_PERSONAS
from key_manager import KeyRotator
from memory_store import MemoryStore
from orchestrator import GodOrchestrator, MissionConfig
from tools import export_docx, export_pdf, export_txt

DEFAULT_MODEL_SMART = "llama-3.3-70b-versatile"
DEFAULT_MODEL_FAST = "llama-3.1-8b-instant"
MODEL_CHOICES = [DEFAULT_MODEL_SMART, DEFAULT_MODEL_FAST]

st.set_page_config(
    page_title="GodBot — Multi-Agent Control",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom CSS: clean, chat-style UI
st.markdown("""
<style>
    /* Main container */
    .stApp { max-width: 1200px; margin: 0 auto; }
    /* Chat container */
    .chat-container { padding: 1rem 0; }
    .message { margin-bottom: 1.25rem; clear: both; }
    .message-user { margin-left: 15%; }
    .message-assistant { margin-right: 15%; }
    .bubble { padding: 0.9rem 1.2rem; border-radius: 14px; line-height: 1.5; }
    .bubble-user {
        background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%);
        color: #fff; box-shadow: 0 2px 8px rgba(13,148,136,0.3);
    }
    .bubble-assistant {
        background: #1e293b; color: #e2e8f0; border: 1px solid #334155;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }
    .bubble-assistant .stMarkdown { color: #e2e8f0; }
    .message-label { font-size: 0.75rem; color: #94a3b8; margin-bottom: 4px; }
    .export-row { margin-top: 10px; padding-top: 10px; border-top: 1px solid #334155; }
    .export-row .stButton button { font-size: 0.8rem; padding: 0.35rem 0.6rem; }
    /* Input area */
    .input-area { background: #0f172a; padding: 1rem; border-radius: 12px; border: 1px solid #334155; }
    /* Sidebar */
    [data-testid="stSidebar"] { background: #0f172a; }
    [data-testid="stSidebar"] .stMarkdown { color: #e2e8f0; }
    /* Headers */
    h1 { font-size: 1.6rem !important; font-weight: 700 !important; }
    h2, h3 { color: #e2e8f0 !important; }
    /* Metrics cards */
    [data-testid="stMetricValue"] { font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# Session state
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None
if "terminal_log" not in st.session_state:
    st.session_state.terminal_log = []
if "active_key_index" not in st.session_state:
    st.session_state.active_key_index = 0
if "personas" not in st.session_state:
    st.session_state.personas = {
        k: {"enabled": True, "model": DEFAULT_MODEL_SMART, "prompt": v["prompt"]}
        for k, v in DEFAULT_PERSONAS.items()
    }


def log_terminal(message: str, level: str = "thought") -> None:
    color = "#00ff99" if level == "thought" else "#ff5577"
    st.session_state.terminal_log.append((message, color))


def build_rotator() -> KeyRotator | None:
    keys = [x.strip() for x in os.getenv("GROQ_API_KEYS", "").split(",") if x.strip()]
    return KeyRotator(api_keys=keys) if keys else None


def ensure_session() -> int:
    memory = MemoryStore()
    if st.session_state.current_session_id is None:
        st.session_state.current_session_id = memory.create_chat_session("New chat")
    return st.session_state.current_session_id


def add_to_chat(role: str, content: str, mission_id: int | None = None, key_states=None) -> None:
    session_id = ensure_session()
    memory = MemoryStore()
    # If this is the first user message, set session title from it
    if role == "user" and len(st.session_state.chat_messages) == 0:
        memory.update_chat_session_title(session_id, (content[:80] + "…") if len(content) > 80 else content)
    st.session_state.chat_messages.append({
        "role": role,
        "content": content,
        "mission_id": mission_id,
        "key_states": key_states,
    })
    memory.add_chat_message(session_id, role, content, mission_id)


def render_chat_message(msg: dict, index: int) -> None:
    role = msg["role"]
    content = msg["content"]
    key_states = msg.get("key_states")
    streamlit_role = "user" if role == "user" else "assistant"
    with st.chat_message(streamlit_role, avatar="🧑" if role == "user" else "⚡"):
        st.markdown(content)
        if role == "assistant" and content.strip():
            c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
            with c1:
                if st.button("📄 TXT", key=f"txt_{index}"):
                    try:
                        p = export_txt(f"godbot_reply_{index}.txt", content)
                        st.success(f"Saved: {p.name}")
                    except Exception as e:
                        st.error(str(e))
            with c2:
                if st.button("📝 Word", key=f"docx_{index}"):
                    try:
                        p = export_docx(f"godbot_reply_{index}.docx", content)
                        st.success(f"Saved: {p.name}")
                    except Exception as e:
                        st.error(str(e))
            with c3:
                if st.button("📕 PDF", key=f"pdf_{index}"):
                    try:
                        p = export_pdf(f"godbot_reply_{index}.pdf", content)
                        st.success(f"Saved: {p.name}")
                    except Exception as e:
                        st.error(str(e))
            with c4:
                if key_states is not None and len(key_states) > 0:
                    with st.expander("Key health"):
                        st.dataframe(key_states, use_container_width=True, hide_index=True)


# ----- Sidebar -----
with st.sidebar:
    st.header("⚙️ Settings")
    st.caption("Runtime & agents")

    if st.button("➕ New chat", use_container_width=True):
        st.session_state.chat_messages = []
        st.session_state.current_session_id = None
        st.session_state.terminal_log = []
        st.rerun()

    st.divider()
    memory = MemoryStore()
    past = memory.list_chat_sessions(20)
    if past:
        chosen = st.selectbox(
            "Past chats",
            options=[f"#{s['id']} — {s['title']}" for s in past],
            key="past_chats",
        )
        if st.button("Load selected chat", use_container_width=True) and chosen:
            sid = int(chosen.split("—")[0].replace("#", "").strip())
            st.session_state.current_session_id = sid
            st.session_state.chat_messages = []
            for m in memory.get_chat_messages(sid):
                st.session_state.chat_messages.append({
                    "role": m["role"],
                    "content": m["content"],
                    "mission_id": m.get("mission_id"),
                    "key_states": None,
                })
            st.rerun()

    st.info(f"Key index: {st.session_state.active_key_index + 1}")
    parallel = st.toggle("Parallel execution", value=True)
    max_workers = st.slider("Max workers", 1, 6, 3)
    max_steps = st.slider("Max steps per agent", 2, 14, 8)

    with st.expander("Agent configuration"):
        for agent_name in DEFAULT_PERSONAS:
            st.session_state.personas[agent_name]["enabled"] = st.checkbox(
                f"Enable {agent_name}",
                value=st.session_state.personas[agent_name]["enabled"],
                key=f"en_{agent_name}",
            )
            st.session_state.personas[agent_name]["model"] = st.selectbox(
                f"Model — {agent_name}",
                MODEL_CHOICES,
                index=MODEL_CHOICES.index(st.session_state.personas[agent_name]["model"]),
                key=f"model_{agent_name}",
            )
            st.session_state.personas[agent_name]["prompt"] = st.text_area(
                f"Prompt — {agent_name}",
                value=st.session_state.personas[agent_name]["prompt"],
                key=f"prompt_{agent_name}",
                height=100,
            )

# ----- Main: title + chat + input -----
st.title("GodBot")
st.caption("Multi-agent mission control · Chat history · Export to TXT, Word, or PDF")

# Chat history
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
for i, msg in enumerate(st.session_state.chat_messages):
    render_chat_message(msg, i)
st.markdown("</div>", unsafe_allow_html=True)

# Input area
st.markdown("---")
template = st.selectbox(
    "Quick template",
    ["Custom", "Lead Gen Blitz", "Deep Research Dossier", "Content Engine Batch"],
    key="template",
)
template_text = {
    "Lead Gen Blitz": "Find 30 high-fit B2B leads in AI infra, infer contacts, rank by intent, create outreach sequence.",
    "Deep Research Dossier": "Research the top 10 trends, competitors, and strategic opportunities in autonomous agent tooling.",
    "Content Engine Batch": "Create 20 tweets, 5 LinkedIn posts, and a long-form blog from latest AI agent market signals.",
}.get(template, "")

mission = st.text_area("Mission / question", value=template_text, height=120, placeholder="Describe what you want GodBot to do…")
deploy = st.button("Deploy mission", type="primary", use_container_width=True)

if deploy:
    if not mission.strip():
        st.warning("Enter a mission or question.")
        st.stop()

    add_to_chat("user", mission.strip())

    rotator = build_rotator()
    if rotator is None:
        add_to_chat("assistant", "Error: No Groq API keys configured. Add keys in `.env` as `GROQ_API_KEYS=key1,key2`.", key_states=[])
        st.rerun()

    memory = MemoryStore()
    orchestrator = GodOrchestrator(rotator, memory, log_terminal)
    enabled = [n for n, cfg in st.session_state.personas.items() if cfg["enabled"]]
    if not enabled:
        add_to_chat("assistant", "Error: No agents enabled. Enable at least one in Settings.", key_states=[])
        st.rerun()

    cfg = MissionConfig(
        objective=mission.strip(),
        enabled_agents=enabled,
        agent_models={name: p["model"] for name, p in st.session_state.personas.items()},
        agent_prompts={name: p["prompt"] for name, p in st.session_state.personas.items()},
        max_steps=max_steps,
        parallel_execution=parallel,
        max_workers=max_workers,
    )

    result = orchestrator.run_mission(cfg)
    st.session_state.active_key_index = rotator.active_index
    report = result["final_report"]
    key_states = result.get("key_states") or []

    add_to_chat(
        "assistant",
        f"**Mission #{result['mission_id']}** — {result['status']}\n\n---\n\n{report}",
        mission_id=result["mission_id"],
        key_states=key_states,
    )
    st.rerun()

# Tabs: Terminal, Artifacts, Memory, Metrics
st.divider()
tab_term, tab_art, tab_mem, tab_met = st.tabs(["Live terminal", "Artifacts", "Memory", "Metrics"])

with tab_term:
    lines = st.session_state.terminal_log[-500:]
    if not lines:
        st.info("No terminal output yet. Run a mission to see agent logs.")
    else:
        html = "<br>".join([f"<span style='color:{c};font-family:monospace;font-size:0.9em'>{m}</span>" for m, c in lines])
        st.markdown(
            f"<div style='background:#0e1117;border:1px solid #2a2f3a;padding:12px;border-radius:8px;min-height:200px;max-height:400px;overflow-y:auto'>{html}</div>",
            unsafe_allow_html=True,
        )
    if st.button("Clear terminal"):
        st.session_state.terminal_log = []
        st.rerun()

with tab_art:
    st.subheader("Generated files")
    files = sorted(Path("artifacts").glob("*"), reverse=True) if Path("artifacts").exists() else []
    if not files:
        st.info("No artifacts yet.")
    else:
        for i, f in enumerate(files):
            if f.is_file():
                st.markdown(f"**{f.name}**")
                if f.suffix in {".md", ".txt", ".json"}:
                    with st.expander("Preview"):
                        st.code(f.read_text(encoding="utf-8")[:6000])
                st.download_button(
                    "Download",
                    data=f.read_bytes(),
                    file_name=f.name,
                    key=f"dl_{i}_{f.name}",
                )

with tab_mem:
    st.subheader("Mission history")
    q = st.text_input("Search", key="mem_search")
    data = memory.search_missions(q, 50) if q else memory.list_recent_missions(50)
    st.dataframe(data, use_container_width=True, hide_index=True)
    if data:
        chosen = st.selectbox("Inspect", [row["id"] for row in data], key="inspect_mission")
        runs = memory.get_agent_runs(chosen)
        for run in runs:
            with st.expander(f"{run['agent_name']} ({run['model']})"):
                st.markdown(run["output"])
                st.code("\n".join(run["thought_log"][-80:]))

with tab_met:
    stats = memory.get_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Missions", stats["total_missions"])
    c2.metric("Successful", stats["successful_missions"])
    c3.metric("Success rate", f"{stats['success_rate'] * 100:.1f}%")
    c4.metric("Agent runs", stats["agent_runs"])
