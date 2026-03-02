from collections import Counter

from planning.assignments import ItemCandidate, assign_items_to_bots
from policies.optimized_multi_bot import OptimizedMultiBotPolicy


class DummyController:
    def __init__(self):
        self.width = 8
        self.height = 8
        self.walls = set()
        self.dropoff = (0, 0)

    def is_free_static(self, pos):
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height and pos not in self.walls


def test_assignment_spreads_items_across_bots():
    bots = [
        {"id": "a", "position": [0, 0], "inventory": []},
        {"id": "b", "position": [5, 5], "inventory": []},
    ]
    items = [
        ItemCandidate("i1", "milk", (1, 1), ((1, 0),)),
        ItemCandidate("i2", "milk", (6, 6), ((6, 5),)),
    ]
    out = assign_items_to_bots(
        bots,
        items,
        Counter({"milk": 2}),
        lambda bot, cand: abs(bot["position"][0] - cand.stands[0][0]) + abs(bot["position"][1] - cand.stands[0][1]),
    )
    assert len(out["a"]) == 1
    assert len(out["b"]) == 1


def test_policy_outputs_action_per_bot():
    state = {
        "type": "game_state",
        "round": 1,
        "bots": [
            {"id": 0, "position": {"x": 0, "y": 1}, "inventory": []},
            {"id": 1, "position": {"x": 4, "y": 1}, "inventory": []},
        ],
        "items": [
            {"id": "item-a", "type": "apple", "position": {"x": 1, "y": 3}},
            {"id": "item-b", "type": "apple", "position": {"x": 5, "y": 3}},
        ],
        "orders": [{"id": "o1", "status": "active", "items_required": ["apple", "apple"], "items_delivered": []}],
    }
    policy = OptimizedMultiBotPolicy()
    controller = DummyController()
    actions = policy(state, controller)
    assert len(actions) == 2
    assert {a["bot"] for a in actions} == {0, 1}
