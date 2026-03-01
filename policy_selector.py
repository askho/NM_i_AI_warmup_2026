from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Protocol, Union

Action = Dict[str, Any]

# A "policy" can be:
# - a function: policy(state) -> List[Action]
# - an object with: policy.act(state) -> List[Action]
PolicyLike = Union[
    Callable[[Dict[str, Any]], List[Action]],
    Any,  # object with .act(...)
]


class PolicySelector(Protocol):
    def select(self, *, difficulty: str, state: Dict[str, Any]) -> PolicyLike:
        ...


@dataclass(frozen=True)
class ConstantPolicySelector:
    """Always returns the same policy instance (no matter difficulty/state)."""
    policy: PolicyLike

    def select(self, *, difficulty: str, state: Dict[str, Any]) -> PolicyLike:
        return self.policy