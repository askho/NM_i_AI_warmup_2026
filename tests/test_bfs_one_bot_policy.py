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
