# tests/test_offline_integration.py
from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot_controller import BotController
from policy_selector import ConstantPolicySelector
from policies.greedy import policy as greedy_policy

# -------------------------
# Logging (visible in pytest with log_cli or -s)
# -------------------------

_LOG_LEVEL = os.environ.get("PYTEST_LOG_LEVEL", "DEBUG").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.DEBUG),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,  # ensure our handler is installed even if pytest configured logging earlier
)
logger = logging.getLogger("tests.offline_integration")

# Tip: run with: pytest -q -s -o log_cli=true --log-cli-level=DEBUG
# Or set env: PYTEST_LOG_LEVEL=INFO


# -------------------------
# Types / constants
# -------------------------

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
State = Dict[str, Any]


# -------------------------
# Runtime type checking helpers
# -------------------------

def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def require_dict(x: Any, name: str) -> Dict[str, Any]:
    require(isinstance(x, dict), f"{name} must be dict, got {type(x).__name__}")
    return x


def require_list(x: Any, name: str) -> List[Any]:
    require(isinstance(x, list), f"{name} must be list, got {type(x).__name__}")
    return x


def require_str(x: Any, name: str) -> str:
    require(isinstance(x, str), f"{name} must be str, got {type(x).__name__}")
    return x


def require_int(x: Any, name: str) -> int:
    require(isinstance(x, int), f"{name} must be int, got {type(x).__name__}")
    return x


def require_pos(x: Any, name: str) -> Pos:
    require(isinstance(x, tuple) and len(x) == 2, f"{name} must be Pos tuple(len=2), got {x!r}")
    require(isinstance(x[0], int) and isinstance(x[1], int), f"{name} must be (int,int), got {x!r}")
    return x  # type: ignore[return-value]


def require_action_dict(a: Any, name: str = "action") -> Action:
    require(isinstance(a, dict), f"{name} must be dict, got {type(a).__name__}")
    require("bot" in a and "action" in a, f"{name} must include keys 'bot' and 'action', got keys={list(a.keys())}")
    require(isinstance(a["action"], str), f"{name}['action'] must be str, got {type(a['action']).__name__}")
    require(a["action"] in ALLOWED_ACTIONS, f"{name}['action'] must be allowed, got {a['action']!r}")
    if a["action"] == "pick_up":
        require(isinstance(a.get("item_id"), str), f"{name} pick_up must include item_id: str")
    require(set(a.keys()).issubset({"bot", "action", "item_id"}), f"{name} has extra keys: {set(a.keys())}")
    return a


def validate_controller_members(controller: Any) -> None:
    require(isinstance(controller, BotController), f"controller must be BotController, got {type(controller).__name__}")
    # These are the new member vars from your refactor
    require(isinstance(controller.initialized, bool), "controller.initialized must be bool")
    require(isinstance(controller.width, int), "controller.width must be int")
    require(isinstance(controller.height, int), "controller.height must be int")
    require(isinstance(controller.walls, set), "controller.walls must be set")
    require(isinstance(controller.dropoff, tuple), "controller.dropoff must be tuple")
    require(isinstance(controller.bots, list), "controller.bots must be list")
    require(isinstance(controller.bots_by_id, dict), "controller.bots_by_id must be dict")


# -------------------------
# State normalization + validation
# -------------------------

def _pos_to_xy_dict(p: Any) -> Any:
    """Convert [x,y]/(x,y) into {'x': x, 'y': y}. Leave dicts unchanged."""
    if isinstance(p, dict):
        if "position" in p and isinstance(p["position"], (list, tuple, dict)):
            return _pos_to_xy_dict(p["position"])
        return p
    if isinstance(p, (list, tuple)) and len(p) >= 2:
        return {"x": int(p[0]), "y": int(p[1])}
    return p


def normalize_state_for_controller(state: State) -> State:
    """
    Normalizes older/offline shapes to what BotController expects:
      - grid -> board
      - bot/item positions as [x,y] -> {'x','y'}
      - keeps everything else the same
    """
    require_dict(state, "state")
    s = deepcopy(state)

    # grid -> board
    if "board" not in s and isinstance(s.get("grid"), dict):
        g = require_dict(s["grid"], "state['grid']")
        s["board"] = {
            "width": g.get("width", 1),
            "height": g.get("height", 1),
            "walls": g.get("walls", []),
        }

    # board sanity
    board = require_dict(s.get("board", {}), "state['board']")
    require("width" in board and "height" in board, "state['board'] must have width and height")
    require(isinstance(board["width"], (int, float)), "state['board']['width'] must be numeric")
    require(isinstance(board["height"], (int, float)), "state['board']['height'] must be numeric")
    if "walls" in board:
        require(isinstance(board["walls"], list), "state['board']['walls'] must be a list")

    # normalize bots positions
    bots = s.get("bots", [])
    if isinstance(bots, list):
        for i, b in enumerate(bots):
            require(isinstance(b, dict), f"state['bots'][{i}] must be dict")
            require("id" in b, f"state['bots'][{i}] missing 'id'")
            if "position" in b:
                b["position"] = _pos_to_xy_dict(b["position"])

    # normalize items positions
    items = s.get("items", [])
    if isinstance(items, list):
        for i, it in enumerate(items):
            require(isinstance(it, dict), f"state['items'][{i}] must be dict")
            if "position" in it:
                it["position"] = _pos_to_xy_dict(it["position"])

    return s


def validate_state_minimum(state: State) -> None:
    """Checks that the state shape we pass between selector -> controller -> policy is sane."""
    require_dict(state, "state")
    require(state.get("type") == "game_state", f"state['type'] must be 'game_state', got {state.get('type')!r}")

    board = require_dict(state.get("board", {}), "state['board']")
    require(isinstance(board.get("width"), (int, float)), "board.width must be numeric")
    require(isinstance(board.get("height"), (int, float)), "board.height must be numeric")
    require(isinstance(board.get("walls", []), list), "board.walls must be list")

    bots = require_list(state.get("bots", []), "state['bots']")
    for i, b in enumerate(bots):
        require(isinstance(b, dict), f"bots[{i}] must be dict")
        require("id" in b, f"bots[{i}] missing id")
        pos = b.get("position")
        require(isinstance(pos, dict), f"bots[{i}].position must be dict {{x,y}} after normalization")
        require(isinstance(pos.get("x"), (int, float)), f"bots[{i}].position.x must be numeric")
        require(isinstance(pos.get("y"), (int, float)), f"bots[{i}].position.y must be numeric")


# -------------------------
# State helpers
# -------------------------

def load_state_from_data_json() -> Optional[State]:
    path = ROOT / "data.json"
    if not path.exists():
        logger.warning("No data.json found at %s; falling back to minimal state.", path)
        return None
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    require(isinstance(data, dict), f"data.json must contain a dict at top-level, got {type(data).__name__}")
    logger.info("Loaded data.json (%s bytes) keys=%s", path.stat().st_size, sorted(data.keys()))
    return data  # type: ignore[return-value]


def make_minimal_state() -> State:
    return {
        "type": "game_state",
        "round": 1,
        "board": {"width": 5, "height": 5, "walls": []},
        "drop_off": [4, 4],
        "bots": [
            {"id": 0, "position": {"x": 0, "y": 1}, "inventory": []},
            {"id": 1, "position": {"x": 2, "y": 1}, "inventory": []},
            {"id": 2, "position": {"x": 4, "y": 1}, "inventory": []},
        ],
        "items": [
            {"id": "item-apple-1", "type": "apple", "position": {"x": 1, "y": 3}},
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


def bot_ids_from_state(state: State) -> List[str]:
    bots = require_list(state.get("bots", []), "state['bots']")
    ids: List[str] = []
    for b in bots:
        require(isinstance(b, dict), "bot must be dict")
        require("id" in b, "bot missing id")
        ids.append(str(b["id"]))
    return ids


def assert_actions_schema(actions: Any, expected_bot_ids: List[str]) -> None:
    require(isinstance(actions, list), f"actions must be list, got {type(actions).__name__}")
    require(len(actions) == len(expected_bot_ids), f"expected {len(expected_bot_ids)} actions, got {len(actions)}")

    expected_set = set(expected_bot_ids)
    seen: set[str] = set()

    for i, a in enumerate(actions):
        a = require_action_dict(a, name=f"actions[{i}]")
        bot_id = str(a["bot"])
        require(bot_id in expected_set, f"actions[{i}].bot={bot_id!r} not in expected ids={sorted(expected_set)}")
        require(bot_id not in seen, f"duplicate bot id in actions: {bot_id!r}")
        seen.add(bot_id)


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


def bot_pos_map(state: State) -> Dict[str, Pos]:
    out: Dict[str, Pos] = {}
    bots = require_list(state.get("bots", []), "state['bots']")
    for b in bots:
        require(isinstance(b, dict), "bot must be dict")
        bot_id = str(b.get("id"))
        pos = require_dict(b.get("position", {}), f"bot[{bot_id}].position")
        x = int(pos.get("x", 0) or 0)
        y = int(pos.get("y", 0) or 0)
        out[bot_id] = (x, y)
    return out


# -------------------------
# Tests
# -------------------------

def test_greedy_policy_integration_smoke() -> None:
    state = load_state_from_data_json() or make_minimal_state()
    state = normalize_state_for_controller(state)
    validate_state_minimum(state)

    controller = BotController()
    validate_controller_members(controller)

    selector = ConstantPolicySelector(greedy_policy)
    selected = selector.select(difficulty="easy", state=state)

    require(callable(selected), "selector.select(...) must return a callable policy")
    controller.set_policy(selected)

    logger.info("Running act() | bots=%d", len(state["bots"]))
    actions = controller.act(state)

    validate_controller_members(controller)
    logger.info(
        "Controller members | initialized=%s size=%dx%d walls=%d dropoff=%s",
        controller.initialized,
        controller.width,
        controller.height,
        len(controller.walls),
        controller.dropoff,
    )
    logger.info("Actions: %s", actions)

    assert_actions_schema(actions, expected_bot_ids=bot_ids_from_state(state))


def test_controller_does_not_mutate_input_state() -> None:
    state = normalize_state_for_controller(make_minimal_state())
    validate_state_minimum(state)
    before = deepcopy(state)

    controller = BotController(greedy_policy)
    validate_controller_members(controller)

    logger.info("Running act() for mutation check")
    _ = controller.act(state)

    require(state == before, "Controller mutated input state")


def test_controller_sanitizes_invalid_and_out_of_bounds_actions() -> None:
    state = normalize_state_for_controller(make_minimal_state())
    validate_state_minimum(state)

    def bad_policy(_state: Dict[str, Any], _controller: BotController) -> List[Action]:
        # Type checks at the boundary
        require_dict(_state, "bad_policy.state")
        require(isinstance(_controller, BotController), "bad_policy.controller must be BotController")
        return [
            {"bot": 0, "action": "move_left"},  # OOB from x=0
            {"bot": 1, "action": "teleport"},   # unknown action
            # bot 2 missing -> should become wait
        ]

    controller = BotController(bad_policy)
    validate_controller_members(controller)

    logger.info("Running act() for sanitization test")
    actions = controller.act(state)
    logger.info("Actions: %s", actions)

    assert_actions_schema(actions, expected_bot_ids=bot_ids_from_state(state))

    got = {str(a["bot"]): a["action"] for a in actions}
    require(got == {"0": "wait", "1": "wait", "2": "wait"}, f"Unexpected sanitized actions: {got}")


def test_conflict_resolution_no_duplicate_destinations() -> None:
    state = normalize_state_for_controller(make_minimal_state())
    validate_state_minimum(state)

    def colliding_policy(_state: Dict[str, Any], _controller: BotController) -> List[Action]:
        require_dict(_state, "colliding_policy.state")
        require(isinstance(_controller, BotController), "colliding_policy.controller must be BotController")
        return [
            {"bot": 0, "action": "move_right"},  # -> (1,1)
            {"bot": 1, "action": "move_left"},   # -> (1,1), conflict
            {"bot": 2, "action": "wait"},
        ]

    controller = BotController(colliding_policy)
    validate_controller_members(controller)

    logger.info("Running act() for conflict-resolution test")
    actions = controller.act(state)
    logger.info("Actions: %s", actions)

    assert_actions_schema(actions, expected_bot_ids=bot_ids_from_state(state))

    bot_pos = bot_pos_map(state)
    destinations = [
        next_cell(require_pos(bot_pos[str(a["bot"])], "bot_pos"), require_str(a["action"], "action"))
        for a in actions
        if isinstance(a.get("action"), str) and a["action"].startswith("move_")
    ]

    logger.info("Destinations: %s", destinations)
    require(len(destinations) == len(set(destinations)), f"Duplicate destinations found: {destinations}")
    require(destinations.count((1, 1)) <= 1, f"Too many bots moving into (1,1): {destinations}")

def test_conflict_resolution_blocks_move_into_waiting_bot_cell() -> None:
    state = normalize_state_for_controller(make_minimal_state())
    validate_state_minimum(state)
    state["bots"][0]["position"] = {"x": 0, "y": 1}
    state["bots"][1]["position"] = {"x": 1, "y": 1}

    def blocking_policy(_state: Dict[str, Any], _controller: BotController) -> List[Action]:
        return [
            {"bot": 0, "action": "move_right"},  # attempts to enter bot 1 cell
            {"bot": 1, "action": "wait"},
            {"bot": 2, "action": "wait"},
        ]

    controller = BotController(blocking_policy)
    actions = controller.act(state)
    got = {str(a["bot"]): a["action"] for a in actions}
    require(got["0"] == "wait", f"Bot 0 should be blocked from entering occupied wait cell, got {got}")


def test_conflict_resolution_blocks_direct_swaps() -> None:
    state = normalize_state_for_controller(make_minimal_state())
    validate_state_minimum(state)
    state["bots"][0]["position"] = {"x": 0, "y": 1}
    state["bots"][1]["position"] = {"x": 1, "y": 1}

    def swap_policy(_state: Dict[str, Any], _controller: BotController) -> List[Action]:
        return [
            {"bot": 0, "action": "move_right"},  # (0,1)->(1,1)
            {"bot": 1, "action": "move_left"},   # (1,1)->(0,1) swap
            {"bot": 2, "action": "wait"},
        ]

    controller = BotController(swap_policy)
    actions = controller.act(state)
    got = {str(a["bot"]): a["action"] for a in actions}
    require(got["0"] == "wait" and got["1"] == "wait", f"Swap should be blocked, got {got}")
