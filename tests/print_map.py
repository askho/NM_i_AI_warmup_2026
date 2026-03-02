import json
from pathlib import Path
import numpy as np
from typing import Any, Dict, List, Optional, Set, Tuple

Pos = Tuple[int, int]

def import_state():
    """imports state from data.json"""


    state_path = Path.cwd() / "data.json"
    with state_path.open("r", encoding="utf-8") as f:
        state = json.load(f)
    return state

def item_id_to_num(item_id: str) -> int:
    return int(item_id[-1])


def build_item_positions_by_type(state):
    """
    Returns: { "cheese": [[3,2],[3,4]], "butter": [[5,2],[5,4]], ... }
    """
    out = {}
    for item in state.get("items"):
        type = item.get("type")

        if type not in out:
            out[type] = []

        out[type].append(item["position"])
        
    return dict(out)

def set_walls_on_map(map, walls):
    for wall in walls:
        x, y = tuple(wall)
        map[y][x] = 1


def set_items_pos_on_map(map, state):

    item_positions = build_item_positions_by_type(state)
    num = 2
    for type in item_positions:
        for pos in item_positions[type]:
            x, y = tuple(pos)
            map[y][x] = num
        num += 1

def main():
    state = import_state()
    grid = state["grid"]
    h, w = grid["height"], grid["width"]
    walls = grid["walls"]

    map = np.zeros((h, w), dtype=int)

    set_walls_on_map(map, walls)
    set_items_pos_on_map(map, state)
    print(map)


if __name__ == "__main__":
    main()
