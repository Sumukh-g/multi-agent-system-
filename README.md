# multi-agent-system

A local **Streamlit** application that runs multiple **Groq** LLM agents on one task. An orchestrator can run agents in parallel or in sequence, merge their outputs into a single report, and persist missions, chat history, and generated files on disk.

Everything runs on your machine. API calls go to Groq; web search uses DuckDuckGo. No separate backend server is required.

---

## What it does

1. You enter a **task** in the UI (or pick a template).
2. One or more agents (**Seer**, **Hunter**, **Scribe**) work on the same objective.
3. Each agent plans steps in a loop (JSON plan → optional tool call → observation) until it finishes or hits the step limit.
4. The orchestrator combines agent outputs into a **mission report** and shows it in the chat.
5. Results are stored in **SQLite**, and copies are written under `artifacts/`.

The UI also keeps a **conversation thread** (user / assistant messages), lets you reopen past chats, and export any assistant reply as **TXT**, **Word (.docx)**, or **PDF**.

---

## Requirements

- **Python 3.10+** (uses `list[str]` style hints and modern typing)
- A [Groq](https://console.groq.com) API key (one is enough; more keys improve handling of rate limits)
- Network access for Groq API and DuckDuckGo search

### Python packages

| Package | Purpose |
|---------|---------|
| `streamlit` | Web UI |
| `groq` | LLM API client |
| `duckduckgo-search` | `web_search` tool for agents |
| `python-dotenv` | Load `GROQ_API_KEYS` from `.env` |
| `python-docx` | Word export from the UI |
| `reportlab` | PDF export from the UI |

Install everything:

```bash
pip install -r requirements.txt
```

---

## Quick start

1. Clone the repository and open the project folder.

2. Create a `.env` file (copy from `.env.example`):

   ```env
   GROQ_API_KEYS=gsk_your_first_key,gsk_your_second_key
   ```

   - Keys are **comma-separated**, no spaces required (spaces around commas are trimmed).
   - **One key** is enough to run the app.
   - **Additional keys** are rotated automatically when Groq returns rate-limit errors.

3. Start the app:

   ```bash
   streamlit run app.py
   ```

4. Open the URL Streamlit prints (usually `http://localhost:8501`).

5. Type a task and click **Run**. Enable or disable agents and change models in the sidebar under **Agent configuration**.

---

## Using the UI

### Main area

- **Chat thread** — Your messages and the combined mission report appear as chat bubbles.
- **Template** — Presets: Custom, Lead generation, Research brief, Content draft (you can edit the text before running).
- **Task** — The objective passed to every enabled agent.
- **Run** — Starts a mission (requires at least one enabled agent and valid API keys).

Under each assistant message you can:

- **Save as TXT / Word / PDF** — Writes a file to `artifacts/` (e.g. `response_0.txt`).
- **API key stats** — Table of per-key usage, failures, cooldown, and health (when available).

### Sidebar (Settings)

| Control | Default | Description |
|---------|---------|-------------|
| New conversation | — | Clears the current chat and starts a new session on the next message |
| Previous conversations | — | Load up to 20 saved chat sessions from the database |
| Parallel execution | On | Run multiple agents at the same time |
| Max workers | 3 | Thread pool size (1–6); capped by number of enabled agents |
| Max steps per agent | 8 | Planner loop limit per agent (2–14) |
| Agent configuration | All on | Per-agent enable, model, and system prompt override |

### Bottom tabs

| Tab | Contents |
|-----|----------|
| **Log** | Live orchestrator and agent log lines from the current session |
| **Files** | List and download files in `artifacts/` (preview for `.md`, `.txt`, `.json`) |
| **History** | Search and inspect past missions; expand each agent run to see output and thought log |
| **Stats** | Total missions, successful missions, success rate, total agent runs |

---

## Agents

Three built-in agents share the same runtime (`GodAgent` in `agents.py`) but different default roles and prompts:

| Agent | Default role | Typical use |
|-------|----------------|-------------|
| **Seer** | Research | Facts, trends, structured analysis |
| **Hunter** | Lead discovery | Companies, contacts, ranking |
| **Scribe** | Content | Posts, copy, outlines |

Each agent:

- Uses the model you select: `llama-3.3-70b-versatile` (default) or `llama-3.1-8b-instant`.
- Runs up to **max steps** (sidebar). Each step asks the model for JSON: `thought`, `action`, `action_input`, `final_answer`.
- Can call **tools** (see below). If the planner does not set a final answer, a synthesis pass runs, then a short **review** pass refines the text.
- Returns `result` (shown in the report), `thought_log`, and metadata.

You can override each agent’s system prompt in the sidebar; changes apply on the next **Run**.

---

## Agent tools

Defined in `tools.py` and invoked only by agents (not by the chat export buttons):

| Tool | Description |
|------|-------------|
| `web_search` | DuckDuckGo text search; results cached **120 seconds** per query/result count |
| `extract_leads` | Regex extraction of emails, phone-like strings, and domains from text (up to 50 each) |
| `save_file` | Write text to `artifacts/<filename>` |
| `save_json` | Write JSON to `artifacts/<filename>` |
| `execute_command` | Run a shell command via `subprocess` (**simulated by default**) |

**`execute_command` safety**

- Default `simulate=True`: no real execution; returns a simulated success message.
- Commands matching dangerous substrings (`rm -rf`, `mkfs`, `shutdown`, etc.) are blocked.
- Real execution only happens if the agent passes `simulate: false` in `action_input` (use with care).

---

## Orchestration

`orchestrator.py` (`GodOrchestrator`):

- **Parallel mode** (default): Used when **Parallel execution** is on **and** more than one agent is enabled. Agents run in a `ThreadPoolExecutor` with `max_workers` (at most the number of enabled agents). They do **not** share context with each other in this mode.
- **Sequential mode**: Used when only one agent is enabled, or parallel is off. Each agent’s result is appended to `shared_context` for the next agent.
- Builds a markdown **Mission report** with a section per agent (name, role, model, result).
- Saves the mission to SQLite and writes:
  - `artifacts/mission_<id>_report.md`
  - `artifacts/mission_<id>_bundle.json` (objective, status, full outputs, key states)

Mission **status** is `success` if at least one agent completed without being dropped from the output list; otherwise `failed`.

---

## API key rotation

`key_manager.py` (`KeyRotator`):

- Reads keys from `GROQ_API_KEYS` or from keys passed in code.
- Picks a client per request using health score, cooldown, and usage (not strict round-robin only).
- On **rate limit** or other errors, marks the key failed and applies a cooldown (starts at **5s**, grows with repeated failures, capped at **30s** plus small jitter).
- Retries up to **`len(keys) * 3`** attempts across keys before failing.

The sidebar shows **Key index** for the rotator’s current queue head after a mission.

---

## Data storage

### SQLite (`missions.db`)

Created in the project root on first use (ignored by git via `.gitignore`).

| Table | Stores |
|-------|--------|
| `missions` | Objective, timestamp, status, final report |
| `agent_runs` | Per-agent output and thought log JSON for each mission |
| `chat_sessions` | Conversation title and timestamp |
| `chat_messages` | User/assistant messages linked to a session (optional `mission_id`) |

If you previously used `godbot_memory.db`, that file is separate; this project now uses **`missions.db`** only.

### Artifacts (`artifacts/`)

- Mission reports and JSON bundles (from the orchestrator).
- Agent-created files via `save_file` / `save_json`.
- UI exports (`response_*.txt`, `.docx`, `.pdf`).

Generated files under `artifacts/` are gitignored except `artifacts/.gitkeep`.

---

## Project layout

```
multi-agent-system/
├── app.py              # Streamlit UI, chat, export buttons
├── agents.py           # GodAgent, DEFAULT_PERSONAS, tool loop
├── orchestrator.py     # GodOrchestrator, MissionConfig, parallel/sequential runs
├── key_manager.py      # KeyRotator, failover, health metrics
├── tools.py            # Search, export helpers, command runner
├── memory_store.py     # SQLite access
├── requirements.txt
├── .env.example        # Template for API keys (copy to .env)
├── .gitignore
├── artifacts/          # Output files (created at runtime)
└── missions.db         # SQLite DB (created at runtime)
```

---

## Configuration reference

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEYS` | Yes | Comma-separated Groq API keys |

Loaded via `python-dotenv` from `.env` in the project root when `app.py` starts.

### Defaults (code)

| Setting | Value |
|---------|--------|
| Default model | `llama-3.3-70b-versatile` |
| Fast model option | `llama-3.1-8b-instant` |
| Agent temperature | `0.35` |
| Default max steps | `8` |
| Default max workers | `3` |
| Search cache TTL | `120` seconds |
| Command timeout (if not simulated) | `30` seconds |

---

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| “No Groq API keys configured” | `.env` exists, `GROQ_API_KEYS` is set, restart Streamlit after editing `.env` |
| “No agents enabled” | Enable at least one agent in the sidebar |
| Rate limits / slow retries | Add more keys to `GROQ_API_KEYS`; check **API key stats** after a run |
| Word/PDF export error | Run `pip install python-docx reportlab` |
| Empty or failed mission | Open **Log** tab; inspect **History** for agent thought logs |
| Past chat missing key stats | Stats are only stored in session for new runs; reloaded chats show messages only |

---

## Security notes

- **Never commit `.env`** — it is listed in `.gitignore`.
- Treat agent **execute_command** as untrusted unless you fully control prompts and tasks.
- Web search sends queries to DuckDuckGo; do not put secrets in tasks if that is a concern.
- The app binds to Streamlit’s default host; use only on trusted networks unless you configure Streamlit authentication/network settings yourself.

---

## License

No license file is included in this repository. Add one if you plan to distribute or open-source the project.
