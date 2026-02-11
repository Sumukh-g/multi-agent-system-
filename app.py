"""GodBot command center with advanced controls, analytics, and mission memory."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from agents import DEFAULT_PERSONAS
from key_manager import KeyRotator
from memory_store import MemoryStore
from orchestrator import GodOrchestrator, MissionConfig

DEFAULT_MODEL_SMART = "llama-3.3-70b-versatile"
DEFAULT_MODEL_FAST = "llama-3.1-8b-instant"
MODEL_CHOICES = [DEFAULT_MODEL_SMART, DEFAULT_MODEL_FAST]

st.set_page_config(page_title="GodBot - World-Class Multi-Agent Control", layout="wide")
st.title("⚡ GODBOT :: Hyper-Advanced Mission Control")
st.caption("Adaptive key carousel • Parallel orchestration • Persistent mission intelligence")

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


def render_terminal() -> None:
    lines = st.session_state.terminal_log[-700:]
    html = "<br>".join([f"<span style='color:{c};font-family:monospace'>{m}</span>" for m, c in lines])
    st.markdown(
        f"<div style='background:#0e1117;border:1px solid #2a2f3a;padding:10px;border-radius:8px;min-height:280px'>{html}</div>",
        unsafe_allow_html=True,
    )


with st.sidebar:
    st.header("🧠 Brain + Runtime")
    st.info(f"Active Key Index: {st.session_state.active_key_index + 1}")
    parallel = st.toggle("Parallel Agent Execution", value=True)
    max_workers = st.slider("Max parallel workers", min_value=1, max_value=6, value=3)
    max_steps = st.slider("Max reasoning steps per agent", min_value=2, max_value=14, value=8)

    with st.expander("⚙️ Agent Configuration", expanded=True):
        for agent_name in DEFAULT_PERSONAS:
            st.markdown(f"#### {agent_name}")
            st.session_state.personas[agent_name]["enabled"] = st.checkbox(
                f"Enable {agent_name}", value=st.session_state.personas[agent_name]["enabled"], key=f"en_{agent_name}"
            )
            st.session_state.personas[agent_name]["model"] = st.selectbox(
                f"Model for {agent_name}",
                MODEL_CHOICES,
                index=MODEL_CHOICES.index(st.session_state.personas[agent_name]["model"]),
                key=f"model_{agent_name}",
            )
            st.session_state.personas[agent_name]["prompt"] = st.text_area(
                f"System Prompt Override ({agent_name})",
                value=st.session_state.personas[agent_name]["prompt"],
                key=f"prompt_{agent_name}",
                height=130,
            )

mission_tab, artifact_tab, memory_tab, metrics_tab = st.tabs(["🎯 Mission", "📦 Artifacts", "🗃️ Memory", "📊 Metrics"])

with mission_tab:
    template = st.selectbox(
        "Mission template",
        [
            "Custom",
            "Lead Gen Blitz",
            "Deep Research Dossier",
            "Content Engine Batch",
        ],
    )
    template_text = {
        "Lead Gen Blitz": "Find 30 high-fit B2B leads in AI infra, infer contacts, rank by intent, create outreach sequence.",
        "Deep Research Dossier": "Research the top 10 trends, competitors, and strategic opportunities in autonomous agent tooling.",
        "Content Engine Batch": "Create 20 tweets, 5 LinkedIn posts, and a long-form blog from latest AI agent market signals.",
    }.get(template, "")

    mission = st.text_area("Mission objective", value=template_text, height=150)
    col_a, col_b = st.columns([1, 1])
    with col_a:
        deploy = st.button("🚀 DEPLOY GODBOT", type="primary")
    with col_b:
        clear = st.button("🧹 Clear Terminal")

    if clear:
        st.session_state.terminal_log = []

    st.subheader("Live Terminal")
    render_terminal()

    if deploy:
        st.session_state.terminal_log = []
        if not mission.strip():
            log_terminal("Mission objective is empty.", "error")
            st.stop()

        rotator = build_rotator()
        if rotator is None:
            log_terminal("Missing GROQ_API_KEYS (expected comma-separated keys).", "error")
            st.stop()

        memory = MemoryStore()
        orchestrator = GodOrchestrator(rotator, memory, log_terminal)

        enabled = [name for name, cfg in st.session_state.personas.items() if cfg["enabled"]]
        if not enabled:
            log_terminal("No agents enabled.", "error")
            st.stop()

        cfg = MissionConfig(
            objective=mission,
            enabled_agents=enabled,
            agent_models={name: p["model"] for name, p in st.session_state.personas.items()},
            agent_prompts={name: p["prompt"] for name, p in st.session_state.personas.items()},
            max_steps=max_steps,
            parallel_execution=parallel,
            max_workers=max_workers,
        )

        result = orchestrator.run_mission(cfg)
        st.session_state.active_key_index = rotator.active_index
        st.success(f"Mission #{result['mission_id']} status={result['status']}")
        st.markdown("### Master Report")
        st.markdown(result["final_report"])
        st.markdown("### Key Health Snapshot")
        st.dataframe(result["key_states"], use_container_width=True)

with artifact_tab:
    st.subheader("Artifact Explorer")
    files = sorted(Path("artifacts").glob("*"), reverse=True) if Path("artifacts").exists() else []
    if not files:
        st.info("No artifacts found.")
    else:
        for file in files:
            if file.is_file():
                st.markdown(f"- `{file.name}`")
                if file.suffix in {".md", ".txt", ".json"}:
                    with st.expander(f"Preview {file.name}"):
                        st.code(file.read_text(encoding="utf-8")[:8000])

with memory_tab:
    memory = MemoryStore()
    st.subheader("Mission Memory")
    q = st.text_input("Search missions")
    data = memory.search_missions(q, 50) if q else memory.list_recent_missions(50)
    st.dataframe(data, use_container_width=True)
    if data:
        chosen = st.selectbox("Inspect mission", [row["id"] for row in data])
        runs = memory.get_agent_runs(chosen)
        for run in runs:
            with st.expander(f"{run['agent_name']} ({run['model']})"):
                st.markdown(run["output"])
                st.code("\n".join(run["thought_log"][-100:]))

with metrics_tab:
    memory = MemoryStore()
    stats = memory.get_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Missions", stats["total_missions"])
    c2.metric("Successful Missions", stats["successful_missions"])
    c3.metric("Success Rate", f"{stats['success_rate'] * 100:.1f}%")
    c4.metric("Agent Runs", stats["agent_runs"])
