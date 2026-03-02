# tests/test_plan_item_run.py
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from policies.greedy import plan_item_run
from planning.pathfinding import neighbors4


class DummyController:
    def __init__(self, width, height, dropoff):
        self.width = width
        self.height = height
        self.dropoff = dropoff

    def in_bounds(self, pos):
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height


def test_plan_item_run_orders_and_path():
    controller = DummyController(width=8, height=6, dropoff=(6, 1))

    state = {
        "items": [
            {"id": "item_0", "type": "butter", "position": [3, 1]},
            {"id": "item_1", "type": "milk", "position": [5, 1]},
        ],
        "bots": [
            {"id": 0, "position": [1, 1]},
            {"id": 1, "position": [2, 1]},  # should be ignored as an obstacle
        ],
    }
    bot = state["bots"][0]

    walls = set()
    blocked = {(3, 1), (5, 1), (1, 1), (2, 1)}  # shelves + bots (including the other bot)

    ordered_shelves, first_path = plan_item_run(
        state=state,
        controller=controller,
        item_types=["butter", "milk", "milk"],  # duplicates should not create extra visits
        walls=walls,
        blocked=blocked,
        bot=bot,
    )

    # Deterministic here since we give exactly one shelf per type and dropoff favors butter->milk
    assert ordered_shelves == [(3, 1), (5, 1)]

    # Path sanity: starts at bot, ends adjacent to first shelf, never steps onto shelf cells
    assert first_path, "Expected a non-empty BFS path to the first stand cell"
    assert first_path[0] == (1, 1)
    assert first_path[-1] in neighbors4((3, 1))
    assert first_path[-1] != (3, 1)

    forbidden = {(3, 1), (5, 1)} | set(walls)
    for step in first_path:
        assert step not in forbidden


def test_plan_item_run_unreachable_returns_empty():
    controller = DummyController(width=6, height=5, dropoff=(5, 2))

    state = {
        "items": [{"id": "item_0", "type": "butter", "position": [3, 2]}],
        "bots": [{"id": 0, "position": [1, 2]}],
    }
    bot = state["bots"][0]

    # Wall barrier blocks any route to a stand cell next to (3,2)
    walls = {(2, 0), (2, 1), (2, 2), (2, 3), (2, 4)}
    blocked = {(3, 2), (1, 2)}  # shelf + bot

    ordered_shelves, first_path = plan_item_run(
        state=state,
        controller=controller,
        item_types=["butter"],
        walls=walls,
        blocked=blocked,
        bot=bot,
    )

    assert ordered_shelves == []
    assert first_path == []