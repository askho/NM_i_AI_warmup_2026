import json
from collections import deque
from pathlib import Path
from typing import Iterable, Optional

Pos = tuple[int, int]


def neighbors4(p: Pos) -> Iterable[Pos]:
    x, y = p
    yield (x + 1, y)
    yield (x - 1, y)
    yield (x, y + 1)
    yield (x, y - 1)


def is_free_cell(p: Pos, *, width: int, height: int, walls: set[Pos], blocked: set[Pos]) -> bool:
    x, y = p
    if x < 0 or x >= width or y < 0 or y >= height:
        return False
    if p in walls:
        return False
    if p in blocked:
        return False
    return True


def bfs_path(
    start: Pos,
    goal: Pos,
    *,
    width: int,
    height: int,
    walls: set[Pos],
    blocked: set[Pos],
) -> Optional[list[Pos]]:
    if start == goal:
        return [start]

    # Allow starting cell even if "blocked" (common when blocked includes bots)
    blocked = blocked - {start}

    q: deque[Pos] = deque([start])
    parent: dict[Pos, Pos] = {}
    visited: set[Pos] = {start}

    while q:
        cur = q.popleft()
        for nxt in neighbors4(cur):
            if nxt in visited:
                continue
            if not is_free_cell(nxt, width=width, height=height, walls=walls, blocked=blocked):
                continue

            visited.add(nxt)
            parent[nxt] = cur

            if nxt == goal:
                # reconstruct
                path: list[Pos] = [goal]
                while path[-1] != start:
                    path.append(parent[path[-1]])
                path.reverse()
                return path

            q.append(nxt)

    return None


def main() -> None:
    state_path = Path("data.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))

    width = int(state["grid"]["width"])
    height = int(state["grid"]["height"])
    walls: set[Pos] = {(x, y) for x, y in state["grid"]["walls"]}
    bots = state["bots"]
    bot_positions: set[Pos] = {(b["position"][0], b["position"][1]) for b in bots}
    drop_off: Pos = (state["drop_off"][0], state["drop_off"][1])

    # Pick one bot and test path to drop-off
    b0 = bots[0]
    start0: Pos = (b0["position"][0], b0["position"][1])

    print(f"Grid: {width}x{height}")
    print(f"Walls: {len(walls)}")
    print(f"Bot positions: {bot_positions}")
    print(f"Drop-off: {drop_off}")
    print()

    path0 = bfs_path(start0, drop_off, width=width, height=height, walls=walls, blocked=bot_positions)
    if path0 is None:
        print("BFS bot0 -> drop_off: NO PATH")
    else:
        print(f"BFS bot0 -> drop_off: path length = {len(path0)-1}")
        print(f"First 8 steps: {path0[:8]}")

    # Test: bot0 to first item position (standing on shelf-adjacent is what you need to pick up,
    # but here we just test reachability to the shelf cell itself)
    if state["items"]:
        item_pos: Pos = (state["items"][0]["position"][0], state["items"][0]["position"][1])
        path_item = bfs_path(start0, item_pos, width=width, height=height, walls=walls, blocked=bot_positions)
        if path_item is None:
            print("\nBFS bot0 -> first item: NO PATH")
        else:
            print(f"\nBFS bot0 -> first item: path length = {len(path_item)-1}")
            print(f"First 8 steps: {path_item[:8]}")


if __name__ == "__main__":
    main()