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

    def in_bounds(self, pos: Pos) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_wall(self, pos: Pos) -> bool:
        return pos in self.walls

    def is_free_static(self, pos: Pos) -> bool:
        return self.in_bounds(pos) and not self.is_wall(pos)