# world.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Set, Tuple

Pos = Tuple[int, int]


@dataclass(frozen=True)
class World:
    width: int
    height: int
    walls: Set[Pos]
    drop_off: Pos

    def __post_init__(self) -> None:
        # Normalize walls to a set of (int,int) positions for reliable membership checks
        normalized_walls: Set[Pos] = set()
        try:
            for p in self.walls:
                if isinstance(p, (list, tuple)) and len(p) == 2:
                    normalized_walls.add((int(p[0]), int(p[1])))
        except Exception:
            normalized_walls = set()
        object.__setattr__(self, "walls", normalized_walls)

        # Normalize drop_off to an (int,int) tuple
        try:
            dx, dy = self.drop_off
            object.__setattr__(self, "drop_off", (int(dx), int(dy)))
        except Exception:
            object.__setattr__(self, "drop_off", (0, 0))

    def in_bounds(self, pos: Pos) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_wall(self, pos: Pos) -> bool:
        return pos in self.walls

    def is_free_static(self, pos: Pos) -> bool:
        return self.in_bounds(pos) and not self.is_wall(pos)