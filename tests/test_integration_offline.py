from __future__ import annotations

from copy import deepcopy
from inspect import signature
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from policy_selector import ConstantPolicySelector
from policies.greedy import policy as greedy_policy
from world import World

ALLOWED_ACTIONS = {
    "move_up",
    "move_down",
    "move_left",
    "move_right",
    "pick_up",
    "drop_off",
    "wait",
}

Pos = Tuple[int, int]
Action = Dict[str, Any]


class OfflineControllerHarness:
    """
    Tiny controller harness used by these offline integration tests.

    The repository currently does not expose a BotController class, so this harness
    mirrors the expected BotController.act/set_policy behavior for integration checks
    across selector + policy + controller arbitration guarantees.
    """

    def __init__(self, policy=None, max_inventory: int = 3) -> None:
        self.policy = policy
        self.max_inventory = max_inventory
        self.world: World | None = None

    def set_policy(self, policy) -> None:
        self.policy = policy

    def is_free_static(self, pos: Pos) -> bool:
        return bool(self.world) and self.world.is_free_static(pos)

    def move_toward(self, bot_id: int, pos: Pos, target: Pos, blocked_positions: set[Pos] | None = None) -> Action:
        blocked_positions = blocked_positions or set()

        x, y = pos
        tx, ty = target

        candidates: List[Tuple[str, Pos]] = []
        if tx > x:
            candidates.append(("move_right", (x + 1, y)))
        elif tx < x:
            candidates.append(("move_left", (x - 1, y)))

        if ty > y:
            candidates.append(("move_down", (x, y + 1)))
        elif ty < y:
            candidates.append(("move_up", (x, y - 1)))

        for action, nxt in candidates:
            if self.world and self.world.is_free_static(nxt) and nxt not in blocked_positions:
                return {"bot": bot_id, "action": action}

        return {"bot": bot_id, "action": "wait"}

    def _call_policy(self, state: Dict[str, Any]) -> List[Action]:
        if self.policy is None:
            return []

        params = len(signature(self.policy).parameters)
        if params >= 2:
            result = self.policy(state, self)
        else:
            result = self.policy(state)
        return result if isinstance(result, list) else []

    def act(self, state: Dict[str, Any]) -> List[Action]:
        grid = state.get("grid", {})
        walls = {tuple(w) for w in grid.get("walls", [])}
        self.world = World(
            width=int(grid.get("width", 0)),
            height=int(grid.get("height", 0)),
            walls=walls,
            drop_off=tuple(state.get("drop_off", [0, 0])),
        )

        bots = state.get("bots", [])
        bot_order = [b["id"] for b in bots]
        bot_positions = {b["id"]: tuple(b["position"]) for b in bots}

        raw = self._call_policy(state)
        raw_by_bot = {a.get("bot"): a for a in raw if isinstance(a, dict) and isinstance(a.get("bot"), int)}

        actions: List[Action] = []
        reserved_destinations: set[Pos] = set()

        for bot_id in bot_order:
            candidate = raw_by_bot.get(bot_id, {"bot": bot_id, "action": "wait"})
            action = candidate.get("action")

            if action not in ALLOWED_ACTIONS:
                actions.append({"bot": bot_id, "action": "wait"})
                continue

            if action == "pick_up" and not isinstance(candidate.get("item_id"), str):
                actions.append({"bot": bot_id, "action": "wait"})
                continue

            if action.startswith("move_"):
                curr = bot_positions[bot_id]
                nxt = next_cell(curr, action)
                if not self.world.is_free_static(nxt):
                    actions.append({"bot": bot_id, "action": "wait"})
                    continue
                if nxt in reserved_destinations:
                    actions.append({"bot": bot_id, "action": "wait"})
                    continue
                reserved_destinations.add(nxt)

            sanitized = {"bot": bot_id, "action": action}
            if action == "pick_up":
                sanitized["item_id"] = candidate["item_id"]
            actions.append(sanitized)

        return actions


def make_minimal_state() -> Dict[str, Any]:
    return {
        "type": "game_state",
        "round": 1,
        "grid": {
            "width": 5,
            "height": 5,
            "walls": [],
        },
        "drop_off": [4, 4],
        "bots": [
            {"id": 0, "position": [0, 1], "inventory": []},
            {"id": 1, "position": [2, 1], "inventory": []},
            {"id": 2, "position": [4, 1], "inventory": []},
        ],
        "items": [
            {"id": "item-apple-1", "type": "apple", "position": [1, 3]},
        ],
        "orders": [
            {
                "id": "order-1",
                "status": "active",
                "items_required": ["apple"],
                "items_delivered": [],
            }
        ],
    }


def assert_actions_schema(actions: List[Action], num_bots: int) -> None:
    assert isinstance(actions, list)
    assert len(actions) == num_bots

    seen_bots = set()
    for a in actions:
        assert isinstance(a, dict)
        assert set(a.keys()).issubset({"bot", "action", "item_id"})
        assert "bot" in a and "action" in a
        assert isinstance(a["bot"], int)
        assert a["bot"] not in seen_bots
        seen_bots.add(a["bot"])

        assert a["action"] in ALLOWED_ACTIONS
        if a["action"] == "pick_up":
            assert isinstance(a.get("item_id"), str)


def next_cell(pos: Pos, action: str) -> Pos:
    x, y = pos
    if action == "move_up":
        return (x, y - 1)
    if action == "move_down":
        return (x, y + 1)
    if action == "move_left":
        return (x - 1, y)
    if action == "move_right":
        return (x + 1, y)
    return pos


def test_greedy_policy_integration_smoke() -> None:
    state = make_minimal_state()

    controller = OfflineControllerHarness()
    selector = ConstantPolicySelector(greedy_policy)

    controller.set_policy(selector.select(difficulty="easy", state=state))
    actions = controller.act(state)

    assert_actions_schema(actions, num_bots=len(state["bots"]))


def test_controller_does_not_mutate_input_state() -> None:
    state = make_minimal_state()
    before = deepcopy(state)

    controller = OfflineControllerHarness(greedy_policy)
    _ = controller.act(state)

    assert state == before


def test_controller_sanitizes_invalid_and_out_of_bounds_actions() -> None:
    state = make_minimal_state()

    def bad_policy(_state: Dict[str, Any]) -> List[Action]:
        return [
            {"bot": 0, "action": "move_left"},  # OOB from x=0
            {"bot": 1, "action": "teleport"},  # unknown action
            # bot 2 missing
        ]

    controller = OfflineControllerHarness(bad_policy)
    actions = controller.act(state)

    assert_actions_schema(actions, num_bots=3)
    assert actions == [
        {"bot": 0, "action": "wait"},
        {"bot": 1, "action": "wait"},
        {"bot": 2, "action": "wait"},
    ]


def test_conflict_resolution_no_duplicate_destinations() -> None:
    state = make_minimal_state()

    def colliding_policy(_state: Dict[str, Any]) -> List[Action]:
        return [
            {"bot": 0, "action": "move_right"},  # -> (1,1)
            {"bot": 1, "action": "move_left"},  # -> (1,1), conflict
            {"bot": 2, "action": "wait"},
        ]

    controller = OfflineControllerHarness(colliding_policy)
    actions = controller.act(state)

    assert_actions_schema(actions, num_bots=3)

    bot_pos = {b["id"]: tuple(b["position"]) for b in state["bots"]}
    destinations = [next_cell(bot_pos[a["bot"]], a["action"]) for a in actions if a["action"].startswith("move_")]

    assert len(destinations) == len(set(destinations))
    assert destinations.count((1, 1)) <= 1
