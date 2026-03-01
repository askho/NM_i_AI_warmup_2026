from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Tuple

Action = Dict[str, Any]
State = Dict[str, Any]
Policy = Callable[[State], List[Action]]

_ALLOWED_ACTIONS = {
    "move_up",
    "move_down",
    "move_left",
    "move_right",
    "pick_up",
    "drop_off",
    "wait",
}
_MOVE_DELTAS: Dict[str, Tuple[int, int]] = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
}


class BotController:
    def __init__(self, policy: Optional[Policy]) -> None:
        self._policy: Optional[Policy] = policy

    def set_policy(self, policy: Policy) -> None:
        self._policy = policy

    def act(self, state: State) -> List[Action]:
        if self._policy is None:
            return []

        # Protect callers against policy-side mutations.
        policy_input = deepcopy(state)
        raw_actions = self._policy(policy_input)

        bots = state.get("bots", [])
        width, height = self._board_size(state)

        indexed: Dict[str, Dict[str, Any]] = {}
        for bot in bots:
            bot_id = str(bot.get("id"))
            indexed[bot_id] = bot

        by_bot: Dict[str, Action] = {}
        if isinstance(raw_actions, list):
            for action in raw_actions:
                if not isinstance(action, dict):
                    continue
                bot_id = str(action.get("bot", ""))
                if bot_id in indexed and bot_id not in by_bot:
                    by_bot[bot_id] = action

        sanitized: List[Action] = []
        occupied_destinations = set()
        for bot in bots:
            bot_id = str(bot.get("id"))
            candidate = by_bot.get(bot_id)
            action = self._sanitize_for_bot(candidate, bot, width, height)

            destination = self._destination(bot, action)
            if destination in occupied_destinations and action["action"] != "wait":
                action = {"bot": bot_id, "action": "wait"}
                destination = self._destination(bot, action)

            occupied_destinations.add(destination)
            sanitized.append(action)

        return sanitized

    def _sanitize_for_bot(
        self,
        action: Optional[Action],
        bot: Dict[str, Any],
        width: int,
        height: int,
    ) -> Action:
        bot_id = str(bot.get("id"))
        if not isinstance(action, dict):
            return {"bot": bot_id, "action": "wait"}

        action_name = action.get("action")
        if action_name not in _ALLOWED_ACTIONS:
            return {"bot": bot_id, "action": "wait"}

        if action_name == "pick_up":
            item_id = action.get("item_id")
            if not isinstance(item_id, str):
                return {"bot": bot_id, "action": "wait"}
            return {"bot": bot_id, "action": "pick_up", "item_id": item_id}

        if action_name in _MOVE_DELTAS:
            x, y = self._position(bot)
            dx, dy = _MOVE_DELTAS[action_name]
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                return {"bot": bot_id, "action": "wait"}

        return {"bot": bot_id, "action": action_name}

    @staticmethod
    def _position(bot: Dict[str, Any]) -> Tuple[int, int]:
        pos = bot.get("position", {})
        return int(pos.get("x", 0)), int(pos.get("y", 0))

    def _destination(self, bot: Dict[str, Any], action: Action) -> Tuple[int, int]:
        x, y = self._position(bot)
        move = action.get("action")
        if move in _MOVE_DELTAS:
            dx, dy = _MOVE_DELTAS[move]
            return x + dx, y + dy
        return x, y

    @staticmethod
    def _board_size(state: State) -> Tuple[int, int]:
        board = state.get("board", {})
        width = int(board.get("width", 1))
        height = int(board.get("height", 1))
        return max(width, 1), max(height, 1)
