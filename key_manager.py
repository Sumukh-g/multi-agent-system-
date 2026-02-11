"""High-performance Groq key orchestration with adaptive failover and metrics."""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from groq import Groq
from groq import RateLimitError

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass
class KeyState:
    index: int
    masked_key: str
    usage_count: int = 0
    failure_count: int = 0
    success_count: int = 0
    cooldown_until: float = 0.0
    avg_latency_ms: float = 0.0
    last_error: str = ""

    @property
    def cooling_down(self) -> bool:
        return time.time() < self.cooldown_until

    @property
    def health_score(self) -> float:
        total = self.success_count + self.failure_count
        success_rate = (self.success_count / total) if total else 1.0
        penalty = 0.2 if self.cooling_down else 0.0
        latency_penalty = min(self.avg_latency_ms / 5000.0, 0.4)
        return max(0.0, success_rate - penalty - latency_penalty)


@dataclass
class KeyRotator:
    """Adaptive key manager shared by all agents.

    Strategy:
    - Start with round-robin semantics.
    - Skip keys in cooldown when possible.
    - Prioritize healthier keys under sustained load.
    """

    api_keys: Iterable[str] | None = None
    base_cooldown_seconds: int = 5
    max_cooldown_seconds: int = 30
    _keys: list[str] = field(init=False, repr=False)
    _states: list[KeyState] = field(init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _rr_queue: deque[int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        keys = [x.strip() for x in (self.api_keys or self._load_env_keys()) if x and x.strip()]
        if not keys:
            raise ValueError("No Groq API keys configured. Set GROQ_API_KEYS or pass api_keys.")
        self._keys = keys
        self._states = [KeyState(index=i, masked_key=self._mask_key(k)) for i, k in enumerate(keys)]
        self._rr_queue = deque(range(len(keys)))

    @staticmethod
    def _load_env_keys() -> list[str]:
        return os.getenv("GROQ_API_KEYS", "").split(",")

    @staticmethod
    def _mask_key(key: str) -> str:
        return f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***"

    @property
    def active_index(self) -> int:
        with self._lock:
            return self._rr_queue[0]

    @property
    def active_label(self) -> str:
        return f"Key #{self.active_index + 1}"

    def _next_candidate(self) -> int:
        now = time.time()
        with self._lock:
            healthy = [s for s in self._states if s.cooldown_until <= now]
            if healthy:
                healthy.sort(key=lambda s: (s.health_score, -s.usage_count), reverse=True)
                winner = healthy[0].index
            else:
                winner = self._rr_queue[0]

            while self._rr_queue[0] != winner:
                self._rr_queue.rotate(-1)
            chosen = self._rr_queue[0]
            self._rr_queue.rotate(-1)
            return chosen

    def get_client(self) -> tuple[int, Groq]:
        idx = self._next_candidate()
        with self._lock:
            self._states[idx].usage_count += 1
        return idx, Groq(api_key=self._keys[idx])

    def get_key_states(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "index": s.index,
                    "label": f"Key #{s.index + 1}",
                    "masked_key": s.masked_key,
                    "usage_count": s.usage_count,
                    "failure_count": s.failure_count,
                    "success_count": s.success_count,
                    "avg_latency_ms": round(s.avg_latency_ms, 2),
                    "cooling_down": s.cooling_down,
                    "health_score": round(s.health_score, 3),
                    "last_error": s.last_error,
                }
                for s in self._states
            ]

    def _mark_success(self, idx: int, latency_ms: float) -> None:
        with self._lock:
            st = self._states[idx]
            st.success_count += 1
            st.avg_latency_ms = (st.avg_latency_ms * 0.8) + (latency_ms * 0.2)
            st.last_error = ""

    def _mark_failure(self, idx: int, error: Exception) -> None:
        with self._lock:
            st = self._states[idx]
            st.failure_count += 1
            st.last_error = type(error).__name__
            expo = min(self.max_cooldown_seconds, self.base_cooldown_seconds * (2 ** min(st.failure_count, 3)))
            jitter = random.uniform(0.0, 1.0)
            st.cooldown_until = time.time() + expo + jitter

    def run_with_failover(self, operation: Callable[[Groq], T], attempts: int | None = None) -> T:
        max_attempts = attempts or (len(self._keys) * 3)
        last_error: Exception | None = None

        for _ in range(max_attempts):
            idx, client = self.get_client()
            t0 = time.perf_counter()
            try:
                output = operation(client)
                self._mark_success(idx, (time.perf_counter() - t0) * 1000)
                return output
            except RateLimitError as exc:
                self._mark_failure(idx, exc)
                last_error = exc
                LOGGER.warning("Rate limit on key index=%s", idx)
            except Exception as exc:
                self._mark_failure(idx, exc)
                last_error = exc
                LOGGER.exception("Operation failed on key index=%s", idx)

        raise RuntimeError(f"All keys exhausted or unhealthy. Last error: {last_error}")
