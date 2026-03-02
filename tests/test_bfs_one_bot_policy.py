from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot_controller import BotController
from policies.BFS_one_bot import policy


def _state_with_adjacent_stand():
    # bot at (0,0), planned best first shelf should be at (2,0) with stand at (1,0)
    return {
        "type": "game_state",
        "round": 1,
        "board": {"width": 6, "height": 4, "walls": []},
        "drop_off": [5, 3],
        "bots": [{"id": 0, "position": {"x": 0, "y": 0}, "inventory": []}],
        "items": [
            {"id": "a_far", "type": "A", "position": [4, 0]},
            {"id": "b_near", "type": "B", "position": [2, 0]},
        ],
        "orders": [
            {
                "id": "o1",
                "status": "active",
                "items_required": ["A", "B"],
                "items_delivered": [],
                "complete": False,
            }
        ],
    }


def test_policy_picks_up_from_planned_first_shelf_not_first_allocated_type():
    controller = BotController(policy)

    # round 1: move toward first planned shelf stand cell
    s1 = _state_with_adjacent_stand()
    a1 = controller.act(s1)
    assert a1[0]["action"] == "move_right"

    # round 2: bot now at stand (1,0), should pick up adjacent shelf at (2,0)
    s2 = _state_with_adjacent_stand()
    s2["round"] = 2
    s2["bots"][0]["position"] = {"x": 1, "y": 0}
    a2 = controller.act(s2)
    assert a2[0]["action"] == "pick_up"
    assert a2[0]["item_id"] == "b_near"


def test_policy_picks_up_when_item_positions_are_xy_dicts():
    controller = BotController(policy)
    s1 = _state_with_adjacent_stand()
    s1["items"][0]["position"] = {"x": 4, "y": 0}
    s1["items"][1]["position"] = {"x": 2, "y": 0}

    a1 = controller.act(s1)
    assert a1[0]["action"] == "move_right"

    s2 = _state_with_adjacent_stand()
    s2["round"] = 2
    s2["bots"][0]["position"] = {"x": 1, "y": 0}
    s2["items"][0]["position"] = {"x": 4, "y": 0}
    s2["items"][1]["position"] = {"x": 2, "y": 0}

    a2 = controller.act(s2)
    assert a2[0]["action"] == "pick_up"
    assert a2[0]["item_id"] == "b_near"


def test_drop_off_only_when_on_dropoff_cell():
    controller = BotController(policy)
    state = {
        "type": "game_state",
        "round": 1,
        "board": {"width": 5, "height": 5, "walls": []},
        "drop_off": [4, 4],
        "bots": [{"id": 0, "position": {"x": 3, "y": 4}, "inventory": [{"type": "A"}]}],
        "items": [{"id": "a1", "type": "A", "position": [0, 0]}],
        "orders": [
            {
                "id": "o1",
                "status": "active",
                "items_required": ["A"],
                "items_delivered": [],
                "complete": False,
            }
        ],
    }

    actions = controller.act(state)
    assert actions[0]["action"] != "drop_off"


def test_full_inventory_moves_toward_dropoff_instead_of_waiting():
    controller = BotController(policy)
    state = {
        "type": "game_state",
        "round": 1,
        "board": {"width": 6, "height": 6, "walls": []},
        "drop_off": [5, 5],
        "bots": [
            {
                "id": 0,
                "position": {"x": 1, "y": 1},
                "inventory": [{"type": "X"}, {"type": "Y"}, {"type": "Z"}],
            }
        ],
        "items": [{"id": "a1", "type": "A", "position": [2, 1]}],
        "orders": [
            {
                "id": "o1",
                "status": "active",
                "items_required": ["A"],
                "items_delivered": [],
                "complete": False,
            }
        ],
    }

    actions = controller.act(state)
    assert actions[0]["action"] in {"move_right", "move_down"}


def test_policy_uses_latest_active_order_by_increasing_order_id():
    controller = BotController(policy)
    state = {
        "type": "game_state",
        "round": 22,
        "board": {"width": 6, "height": 4, "walls": []},
        "drop_off": [5, 3],
        "bots": [{"id": 0, "position": {"x": 0, "y": 0}, "inventory": []}],
        "items": [
            {"id": "milk_1", "type": "milk", "position": [1, 0]},
            {"id": "butter_1", "type": "butter", "position": [0, 1]},
        ],
        "orders": [
            {
                "id": "order_0",
                "status": "active",
                "items_required": ["milk"],
                "items_delivered": ["milk"],
                "complete": True,
            },
            {
                "id": "order_8",
                "status": "active",
                "items_required": ["butter"],
                "items_delivered": [],
                "complete": False,
            },
        ],
    }

    actions = controller.act(state)
    assert actions[0]["action"] == "pick_up"
    assert actions[0]["item_id"] == "butter_1"


def test_policy_does_not_pick_extra_item_type_already_fully_delivered():
    controller = BotController(policy)
    state = {
        "type": "game_state",
        "round": 24,
        "board": {"width": 6, "height": 4, "walls": []},
        "drop_off": [5, 3],
        "bots": [{"id": 0, "position": {"x": 0, "y": 0}, "inventory": []}],
        "items": [
            {"id": "milk_1", "type": "milk", "position": [1, 0]},
            {"id": "milk_2", "type": "milk", "position": [2, 0]},
            {"id": "bread_1", "type": "bread", "position": [0, 1]},
        ],
        "orders": [
            {
                "id": "order_10",
                "status": "active",
                "items_required": ["milk", "bread"],
                "items_delivered": ["milk"],
                "complete": False,
            }
        ],
    }

    actions = controller.act(state)
    assert actions[0]["action"] == "pick_up"
    assert actions[0]["item_id"] == "bread_1"
