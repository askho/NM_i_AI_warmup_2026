from __future__ import annotations

from typing import Any, Dict, List


def policy(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Simple deterministic policy for integration tests and local runs."""
    actions: List[Dict[str, Any]] = []
    for bot in state.get("bots", []):
        actions.append({"bot": str(bot.get("id")), "action": "wait"})
    return actions
