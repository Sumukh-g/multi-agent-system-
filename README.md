# multi-agent-system

Local Streamlit app that runs several Groq-backed agents on a shared mission. One orchestrator coordinates agents, rotates API keys on rate limits, and stores mission output in SQLite.

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set your keys:

```
GROQ_API_KEYS=key_one,key_two
```

Keys are available from [console.groq.com](https://console.groq.com). You only need one key; extra keys are used when one hits a rate limit.

```bash
streamlit run app.py
```

## Layout

| File | Role |
|------|------|
| `app.py` | Streamlit UI |
| `orchestrator.py` | Runs agents in parallel or sequence, merges output |
| `agents.py` | ReAct-style agents (Seer, Hunter, Scribe) |
| `key_manager.py` | Groq client pool and failover |
| `tools.py` | Search, file export, safe command runner |
| `memory_store.py` | Missions, chat sessions, agent runs |

## Notes

- Shell commands in `execute_command` are simulated by default.
- Dangerous command patterns are blocked.
- Web search results are cached for two minutes.
- Exports (txt, docx, pdf) are written under `artifacts/`.
