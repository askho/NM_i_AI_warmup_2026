from __future__ import annotations

from collections import deque
from typing import Iterable, Optional

Pos = tuple[int, int]


def neighbors4(p: Pos) -> Iterable[Pos]:
    # Returns the 4 orthogonal neighbors of p (up, down, left, right).
    x, y = p
    yield (x + 1, y)
    yield (x - 1, y)
    yield (x, y + 1)
    yield (x, y - 1)

def is_free_cell(
    p: Pos,
    *,
    width: int,
    height: int,
    walls: set[Pos],
    blocked: set[Pos],
) -> bool:
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
    blocked: set[Pos] | None = None,
) -> Optional[list[Pos]]:
    """
    Returns a shortest path as a list of positions [start, ..., goal],
    or None if unreachable.

    Note: `blocked` is for dynamic obstacles like other bots. Typically
    you pass all bot positions EXCEPT the bot you're planning for.
    """
    if blocked is None:
        blocked = set()

    if start == goal:
        return [start]

    # It's common to allow standing on start even if it's "blocked"
    blocked_minus_start = blocked - {start}

    q: deque[Pos] = deque([start])
    parent: dict[Pos, Pos] = {}
    visited: set[Pos] = {start}

    while q:
        cur = q.popleft()

        for nxt in neighbors4(cur):
            if nxt in visited:
                continue
            if not is_free_cell(nxt, width=width, height=height, walls=walls, blocked=blocked_minus_start):
                continue

            visited.add(nxt)
            parent[nxt] = cur

            if nxt == goal:
                # Reconstruct path
                path: list[Pos] = [goal]
                while path[-1] != start:
                    path.append(parent[path[-1]])
                path.reverse()
                return path

            q.append(nxt)

    return None