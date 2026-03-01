from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

from bot_controller import BotController
from policies.greedy import policy as greedy_policy

ALLOWED_ACTIONS = {
    "move_up",
    "move_down",
    "move_left",
    "move_right",
    "pick_up",
    "drop_off",
    "wait",
}
MOVE_DELTAS = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
}


def make_minimal_state() -> Dict[str, Any]:
    return {
        "type": "game_state",
        "tick": 1,
        "board": {"width": 5, "height": 5},
        "bots": [
            {"id": "b0", "position": {"x": 0, "y": 0}},
            {"id": "b1", "position": {"x": 1, "y": 0}},
            {"id": "b2", "position": {"x": 4, "y": 4}},
        ],
        "items": [],
    }


def assert_actions_schema(actions: List[Dict[str, Any]], num_bots: int) -> None:
    assert isinstance(actions, list)
    assert len(actions) == num_bots

    seen = set()
    for action in actions:
        assert isinstance(action, dict)
        assert set(action.keys()).issubset({"bot", "action", "item_id"})
        assert {"bot", "action"}.issubset(action.keys())

        bot_id = action["bot"]
        assert isinstance(bot_id, str)
        assert bot_id not in seen
        seen.add(bot_id)

        action_name = action["action"]
        assert action_name in ALLOWED_ACTIONS

        if action_name == "pick_up":
            assert "item_id" in action
            assert isinstance(action["item_id"], str)


def next_cell(bot: Dict[str, Any], action: Dict[str, Any]) -> Tuple[int, int]:
    x, y = bot["position"]["x"], bot["position"]["y"]
    if action["action"] in MOVE_DELTAS:
        dx, dy = MOVE_DELTAS[action["action"]]
        return (x + dx, y + dy)
    return (x, y)


def test_greedy_policy_integration_smoke() -> None:
    state = make_minimal_state()
    controller = BotController(policy=greedy_policy)

    actions = controller.act(state)

    assert_actions_schema(actions, num_bots=len(state["bots"]))


def test_controller_does_not_mutate_input_state() -> None:
    state = make_minimal_state()
    state_before = deepcopy(state)

    def mutating_policy(policy_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        policy_state["bots"][0]["position"]["x"] = 99
        return [{"bot": "b0", "action": "wait"}]

    controller = BotController(policy=mutating_policy)
    controller.act(state)

    assert state == state_before


def test_controller_sanitizes_invalid_and_out_of_bounds_actions() -> None:
    state = make_minimal_state()

    def bad_policy(_: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {"bot": "b0", "action": "move_left"},  # out of bounds from (0, 0)
            {"bot": "b1", "action": "teleport"},  # unknown action
            # b2 missing entirely -> should default to wait
        ]

    controller = BotController(policy=bad_policy)
    actions = controller.act(state)

    assert_actions_schema(actions, num_bots=3)
    action_by_bot = {a["bot"]: a["action"] for a in actions}
    assert action_by_bot["b0"] == "wait"
    assert action_by_bot["b1"] == "wait"
    assert action_by_bot["b2"] == "wait"


def test_conflict_resolution_no_duplicate_destinations() -> None:
    state = make_minimal_state()
    # move b1 closer to force same destination target as b0
    state["bots"][1]["position"] = {"x": 2, "y": 0}

    def colliding_policy(_: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {"bot": "b0", "action": "move_right"},  # -> (1, 0)
            {"bot": "b1", "action": "move_left"},   # -> (1, 0) too
            {"bot": "b2", "action": "wait"},
        ]

    controller = BotController(policy=colliding_policy)
    actions = controller.act(state)

    assert_actions_schema(actions, num_bots=3)

    bots = {bot["id"]: bot for bot in state["bots"]}
    destinations = [next_cell(bots[a["bot"]], a) for a in actions]
    assert len(destinations) == len(set(destinations))
