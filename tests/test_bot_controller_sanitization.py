from typing import Any, Dict, List

from bot_controller import BotController

Action = Dict[str, Any]


def _base_state() -> Dict[str, Any]:
    return {
        "type": "game_state",
        "round": 1,
        "max_rounds": 300,
        "grid": {"width": 6, "height": 6, "walls": []},
        "drop_off": [0, 0],
        "bots": [
            {"id": 0, "position": [1, 1], "inventory": []},
            {"id": 1, "position": [2, 1], "inventory": []},
        ],
        "items": [{"id": "item_1", "type": "apple", "position": [4, 4]}],
        "orders": [],
    }


def test_controller_blocks_invalid_pickup_and_dropoff() -> None:
    def bad_policy(_state: Dict[str, Any], _controller: BotController) -> List[Action]:
        return [
            {"bot": 0, "action": "pick_up", "item_id": "item_1"},  # not adjacent
            {"bot": 1, "action": "drop_off"},  # not on dropoff
        ]

    state = _base_state()
    controller = BotController(bad_policy)
    actions = controller.act(state)
    got = {a["bot"]: a["action"] for a in actions}
    assert got == {0: "wait", 1: "wait"}


def test_controller_blocks_head_on_swap_collision() -> None:
    def swap_policy(_state: Dict[str, Any], _controller: BotController) -> List[Action]:
        return [
            {"bot": 0, "action": "move_right"},
            {"bot": 1, "action": "move_left"},
        ]

    state = _base_state()
    controller = BotController(swap_policy)
    actions = controller.act(state)
    got = {a["bot"]: a["action"] for a in actions}
    assert got[0] == "move_right"
    assert got[1] == "wait"
