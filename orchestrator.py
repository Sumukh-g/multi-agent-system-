"""God Brain orchestrator: parallel execution, synthesis, and persistence."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable

from agents import DEFAULT_PERSONAS, GodAgent
from key_manager import KeyRotator
from memory_store import MemoryStore
from tools import save_file, save_json


@dataclass
class MissionConfig:
    objective: str
    enabled_agents: list[str]
    agent_models: dict[str, str]
    agent_prompts: dict[str, str]
    max_steps: int
    parallel_execution: bool = True
    max_workers: int = 3


class GodOrchestrator:
    def __init__(self, key_rotator: KeyRotator, memory_store: MemoryStore, logger: Callable[[str, str], None]) -> None:
        self.key_rotator = key_rotator
        self.memory_store = memory_store
        self.logger = logger

    def _mk_agent(self, name: str, cfg: MissionConfig) -> GodAgent:
        return GodAgent(
            name=name,
            role=DEFAULT_PERSONAS[name]["role"],
            model=cfg.agent_models[name],
            key_manager=self.key_rotator,
            system_prompt=cfg.agent_prompts[name],
            max_steps=cfg.max_steps,
        )

    def _run_one(self, name: str, cfg: MissionConfig, shared_context: str) -> dict[str, Any]:
        self.logger(f"[{name}] boot model={cfg.agent_models[name]}", "thought")
        return self._mk_agent(name, cfg).run_task(cfg.objective, shared_context=shared_context)

    def _synthesize_report(self, outputs: list[dict[str, Any]], objective: str) -> str:
        sections = []
        for out in outputs:
            sections.append(
                f"## {out['agent']} - {out['role']}\n"
                f"Model: `{out['model']}`\n\n"
                f"{out['result']}\n"
            )
        base = "\n\n".join(sections)
        return f"# GODBOT MASTER REPORT\n\nObjective: {objective}\n\n{base}"

    def run_mission(self, cfg: MissionConfig) -> dict[str, Any]:
        self.logger(f"Mission accepted: {cfg.objective}", "thought")
        outputs: list[dict[str, Any]] = []
        shared_context = ""

        if cfg.parallel_execution and len(cfg.enabled_agents) > 1:
            self.logger("Execution mode: PARALLEL", "thought")
            with ThreadPoolExecutor(max_workers=min(cfg.max_workers, len(cfg.enabled_agents))) as pool:
                futures = {
                    pool.submit(self._run_one, name, cfg, shared_context): name
                    for name in cfg.enabled_agents
                }
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        out = future.result()
                        outputs.append(out)
                        for line in out["thought_log"][-30:]:
                            self.logger(f"[{name}] {line}", "thought")
                    except Exception as exc:
                        self.logger(f"[{name}] failed: {exc}", "error")
        else:
            self.logger("Execution mode: SEQUENTIAL", "thought")
            for name in cfg.enabled_agents:
                try:
                    out = self._run_one(name, cfg, shared_context)
                    outputs.append(out)
                    shared_context += f"\n{name}: {out['result']}"
                    for line in out["thought_log"][-30:]:
                        self.logger(f"[{name}] {line}", "thought")
                except Exception as exc:
                    self.logger(f"[{name}] failed: {exc}", "error")

        report = self._synthesize_report(outputs, cfg.objective) if outputs else "No successful outputs."
        status = "success" if outputs else "failed"
        mission_id = self.memory_store.save_mission(cfg.objective, status, report)

        for out in outputs:
            self.memory_store.save_agent_run(
                mission_id=mission_id,
                agent_name=str(out["agent"]),
                model=str(out["model"]),
                output=str(out["result"]),
                thought_log=list(out["thought_log"]),
            )

        report_path = save_file(f"mission_{mission_id}_report.md", report)
        bundle_path = save_json(
            f"mission_{mission_id}_bundle.json",
            {
                "mission_id": mission_id,
                "objective": cfg.objective,
                "status": status,
                "outputs": outputs,
                "key_states": self.key_rotator.get_key_states(),
            },
        )

        return {
            "mission_id": mission_id,
            "status": status,
            "final_report": report,
            "report_artifact": str(report_path),
            "bundle_artifact": str(bundle_path),
            "outputs": outputs,
            "key_states": self.key_rotator.get_key_states(),
        }
