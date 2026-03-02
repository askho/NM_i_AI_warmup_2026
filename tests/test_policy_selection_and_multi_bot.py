from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot_controller import BotController
from policies.BFS_one_bot import policy as BFSOneBotPolicy
from policies.multi_bot_optimizer import policy as MultiBotOptimizerPolicy
from policy_selector import BotCountPolicySelector


def _base_state(bot_count: int):
    bots = []
    for i in range(bot_count):
        bots.append({"id": i, "position": {"x": i, "y": 0}, "inventory": []})
    return {
        "type": "game_state",
        "round": 1,
        "board": {"width": 7, "height": 5, "walls": []},
        "drop_off": [6, 4],
        "bots": bots,
        "items": [
            {"id": "milk_1", "type": "milk", "position": [2, 1]},
            {"id": "milk_2", "type": "milk", "position": [4, 1]},
        ],
        "orders": [
            {
                "id": "order_2",
                "status": "active",
                "items_required": ["milk", "milk"],
                "items_delivered": [],
                "complete": False,
            }
        ],
    }


def test_selector_uses_one_bot_policy_when_single_bot():
    selector = BotCountPolicySelector(BFSOneBotPolicy, MultiBotOptimizerPolicy)
    selected = selector.select(difficulty="easy", state=_base_state(1))
    assert selected is BFSOneBotPolicy


def test_selector_uses_multi_bot_policy_when_multiple_bots():
    selector = BotCountPolicySelector(BFSOneBotPolicy, MultiBotOptimizerPolicy)
    selected = selector.select(difficulty="easy", state=_base_state(2))
    assert selected is MultiBotOptimizerPolicy


def test_multi_bot_policy_emits_action_per_bot():
    controller = BotController(policy=MultiBotOptimizerPolicy)
    actions = controller.act(_base_state(3))

    assert len(actions) == 3
    assert {a["bot"] for a in actions} == {0, 1, 2}
