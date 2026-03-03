from collections import Counter

from planning.assignments import ItemCandidate, assign_items_to_bots
from policies.optimized_multi_bot import OptimizedMultiBotPolicy, _carry_contribution_to_active_need


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


def test_policy_prefers_zero_distance_candidate_for_pickup():
    state = {
        "type": "game_state",
        "round": 1,
        "bots": [
            {"id": 0, "position": {"x": 1, "y": 0}, "inventory": []},
            {"id": 1, "position": {"x": 7, "y": 7}, "inventory": []},
        ],
        "items": [
            {"id": "item-a", "type": "apple", "position": {"x": 1, "y": 1}},
        ],
        "orders": [{"id": "o1", "status": "active", "items_required": ["apple"], "items_delivered": []}],
    }
    policy = OptimizedMultiBotPolicy()
    controller = DummyController()
    actions = policy(state, controller)
    by_bot = {a["bot"]: a for a in actions}
    assert by_bot[0]["action"] == "pick_up"
    assert by_bot[0]["item_id"] == "item-a"


def test_carry_contribution_excludes_already_held_items_from_pick_need():
    bots = [
        {"id": "a", "inventory": ["apple"]},
        {"id": "b", "inventory": ["banana", "apple"]},
    ]
    need = Counter({"apple": 2, "banana": 1, "pear": 1})
    assert _carry_contribution_to_active_need(need, bots) == Counter({"apple": 2, "banana": 1})


def test_policy_prioritizes_dropoff_when_carrying_deliverable_item():
    state = {
        "type": "game_state",
        "round": 1,
        "bots": [
            {"id": 0, "position": {"x": 2, "y": 2}, "inventory": ["apple"]},
        ],
        "items": [
            {"id": "item-a", "type": "apple", "position": {"x": 2, "y": 3}},
        ],
        "orders": [{"id": "o1", "status": "active", "items_required": ["apple"], "items_delivered": []}],
    }
    policy = OptimizedMultiBotPolicy()
    controller = DummyController()
    actions = policy(state, controller)
    assert actions[0]["action"] in {"move_left", "move_up"}


def test_policy_drops_off_when_standing_on_dropoff_with_deliverable_inventory():
    state = {
        "type": "game_state",
        "round": 2,
        "bots": [
            {"id": 0, "position": {"x": 0, "y": 0}, "inventory": ["apple"]},
        ],
        "items": [],
        "orders": [{"id": "o1", "status": "active", "items_required": ["apple"], "items_delivered": []}],
    }
    policy = OptimizedMultiBotPolicy()
    controller = DummyController()
    actions = policy(state, controller)
    assert actions == [{"bot": 0, "action": "drop_off"}]
