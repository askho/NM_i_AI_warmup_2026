from __future__ import annotations

from typing import Any, Callable, Dict, Protocol


class PolicySelector(Protocol):
    def select(self, difficulty: str, state: Dict[str, Any]) -> Callable[[Dict[str, Any]], list[dict[str, Any]]]:
        ...


class ConstantPolicySelector:
    def __init__(self, policy: Callable[[Dict[str, Any]], list[dict[str, Any]]]) -> None:
        self._policy = policy

    def select(self, difficulty: str, state: Dict[str, Any]) -> Callable[[Dict[str, Any]], list[dict[str, Any]]]:
        return self._policy
