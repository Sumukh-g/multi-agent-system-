"""Advanced agent runtime for GodBot."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from key_manager import KeyRotator
from tools import execute_command, extract_leads, save_file, save_json, web_search

ToolFn = Callable[..., object]


@dataclass
class AgentStep:
    thought: str
    action: str
    action_input: dict[str, Any]
    final_answer: str


@dataclass
class GodAgent:
    name: str
    role: str
    model: str
    key_manager: KeyRotator
    system_prompt: str
    max_steps: int = 8
    temperature: float = 0.35
    thought_log: list[str] = field(default_factory=list)

    def _chat(self, prompt: str) -> str:
        def call(client):
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
            )
            return resp.choices[0].message.content or ""

        return self.key_manager.run_with_failover(call)

    def _tools(self) -> dict[str, ToolFn]:
        return {
            "web_search": web_search,
            "execute_command": execute_command,
            "save_file": save_file,
            "save_json": save_json,
            "extract_leads": extract_leads,
        }

    def _planner_prompt(self, objective: str, context: list[str]) -> str:
        return (
            "Return ONLY strict JSON: "
            "{thought:str, action:str, action_input:object, final_answer:str}. "
            "Allowed actions: web_search, execute_command, extract_leads, save_file, save_json, none.\n"
            "Mission objective: " + objective + "\n"
            "Recent context: " + json.dumps(context[-8:])
        )

    @staticmethod
    def _parse_json_or_finalize(raw: str) -> AgentStep:
        try:
            data = json.loads(raw)
            return AgentStep(
                thought=str(data.get("thought", "")),
                action=str(data.get("action", "none")),
                action_input=data.get("action_input", {}) or {},
                final_answer=str(data.get("final_answer", "")).strip(),
            )
        except Exception:
            return AgentStep(
                thought="Planner returned non-JSON output.",
                action="none",
                action_input={},
                final_answer=raw,
            )

    def _invoke_tool(self, action: str, action_input: dict[str, Any], tools: dict[str, ToolFn]) -> object:
        fn = tools[action]
        if action == "web_search":
            return fn(
                query=str(action_input.get("query", "")),
                max_results=int(action_input.get("max_results", 8)),
                use_cache=bool(action_input.get("use_cache", True)),
            )
        if action == "execute_command":
            return fn(
                command=str(action_input.get("command", "")),
                simulate=bool(action_input.get("simulate", True)),
                timeout=int(action_input.get("timeout", 30)),
            )
        if action == "extract_leads":
            return fn(text=str(action_input.get("text", "")))
        if action == "save_file":
            return str(fn(filename=str(action_input.get("filename", f"{self.name.lower()}_artifact.md")), content=str(action_input.get("content", ""))))
        if action == "save_json":
            return str(fn(filename=str(action_input.get("filename", f"{self.name.lower()}_artifact.json")), payload=action_input.get("payload", {})))
        raise ValueError(f"Unsupported action: {action}")

    def run_task(self, objective: str, shared_context: str = "") -> dict[str, Any]:
        tools = self._tools()
        context = [f"shared_context={shared_context}"] if shared_context else []
        final_answer = ""

        for step in range(1, self.max_steps + 1):
            raw = self._chat(self._planner_prompt(objective, context))
            parsed = self._parse_json_or_finalize(raw)
            self.thought_log.append(f"[{step}] thought={parsed.thought}")
            self.thought_log.append(f"[{step}] action={parsed.action} input={parsed.action_input}")

            if parsed.action == "none":
                final_answer = parsed.final_answer or final_answer
                break

            if parsed.action not in tools:
                self.thought_log.append(f"[{step}] invalid_action={parsed.action}")
                context.append(f"invalid_action={parsed.action}")
                continue

            try:
                obs = self._invoke_tool(parsed.action, parsed.action_input, tools)
                context.append(f"{parsed.action} -> {obs}")
                self.thought_log.append(f"[{step}] observation={obs}")
            except Exception as exc:
                context.append(f"{parsed.action} failed: {exc}")
                self.thought_log.append(f"[{step}] error={exc}")

        if not final_answer:
            final_answer = self._chat(
                "Create a final high-value answer from this context. Include actionable sections.\n"
                f"Objective: {objective}\n"
                f"Context: {context}"
            )

        critique = self._chat(
            "Critique and improve the following answer. Return improved final answer only.\n"
            f"{final_answer}"
        )

        return {
            "agent": self.name,
            "role": self.role,
            "model": self.model,
            "result": critique,
            "raw_result": final_answer,
            "thought_log": self.thought_log.copy(),
            "context": context,
        }


DEFAULT_PERSONAS: dict[str, dict[str, str]] = {
    "Seer": {
        "role": "Deep Research Strategist",
        "prompt": (
            "You are The Seer, world-class intelligence researcher. Produce highly factual, source-driven, "
            "deeply structured analysis with uncertainty labeling."
        ),
    },
    "Hunter": {
        "role": "Lead Discovery + Qualification Specialist",
        "prompt": (
            "You are The Hunter, elite revenue intelligence operator. Discover prospects, extract contact hypotheses, "
            "and rank opportunities by fit and urgency."
        ),
    },
    "Scribe": {
        "role": "Persuasion and Content Conversion Specialist",
        "prompt": (
            "You are The Scribe, high-conversion content engineer. Transform findings into multi-channel, "
            "tone-adjusted deliverables with CTA testing variants."
        ),
    },
}
