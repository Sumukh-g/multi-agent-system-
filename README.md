# GodBot: Hyper-Advanced Multi-Agent Intelligence System

GodBot is a local-first, performance-oriented, multi-agent architecture designed around a centralized "God Brain" orchestration layer and adaptive Groq key management.

## Why this is now significantly more advanced

This codebase is no longer a small demo scaffold. It includes:

- **Adaptive Key Orchestration** with health scoring, latency tracking, exponential cooldown, and failover retries.
- **High-performance Tooling** with cached web search, lead extraction, safe command execution, artifact + JSON persistence.
- **Advanced Agent Runtime** with structured ReAct planning, tool routing, fallback synthesis, and self-critique post-processing.
- **God Brain Orchestrator** supporting parallel or sequential execution modes, output synthesis, and artifact bundling.
- **Persistent Mission Intelligence** (SQLite) with mission search, run history, and operational metrics.
- **Powerful Streamlit Command Center** with mission templates, parallelism controls, agent-level config, memory search, artifact explorer, and KPI dashboard.

## Architecture

- `key_manager.py` — adaptive centralized Groq key carousel.
- `tools.py` — web search/cache, lead extraction, command execution, artifact I/O.
- `agents.py` — high-capability ReAct agents (Seer/Hunter/Scribe).
- `orchestrator.py` — God Brain execution coordinator.
- `memory_store.py` — mission/run persistence and analytics.
- `app.py` — multi-tab Streamlit operations dashboard.

## Quickstart

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root (or copy from `.env.example`):

```
GROQ_API_KEYS=your_key_1,your_key_2,your_key_3
```

Get API keys at [console.groq.com](https://console.groq.com). Then:

```bash
streamlit run app.py
```

## Safety + Performance Notes

- Dangerous shell patterns are blocked in `execute_command`.
- Command execution defaults to simulation unless explicitly disabled.
- Web results are cached to reduce duplicate search overhead.
- Key manager tracks per-key reliability/latency for better runtime decisions.
