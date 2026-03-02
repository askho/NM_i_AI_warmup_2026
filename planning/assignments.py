from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

Pos = tuple[int, int]


@dataclass(frozen=True)
class ItemCandidate:
    item_id: str
    item_type: str
    shelf_pos: Pos
    stands: tuple[Pos, ...]


def _inventory_size(bot: dict) -> int:
    inv = bot.get("inventory", [])
    return len(inv) if isinstance(inv, list) else 0


def assign_items_to_bots(
    bots: Iterable[dict],
    candidates: Iterable[ItemCandidate],
    need: Counter,
    distance_cost: Callable[[dict, ItemCandidate], int],
    *,
    max_inventory: int = 3,
    max_slots_per_bot: int = 2,
) -> Dict[str, List[ItemCandidate]]:
    """Greedy min-cost matching over (bot slots, item candidates).

    This is an ILP-lite approximation that avoids heavy dependencies while still
    producing globally consistent, collision-aware assignments.
    """
    bot_list = [b for b in bots if isinstance(b, dict) and "id" in b]
    cand_list = [c for c in candidates if need.get(c.item_type, 0) > 0]

    assigned: Dict[str, List[ItemCandidate]] = {str(b["id"]): [] for b in bot_list}
    if not bot_list or not cand_list:
        return assigned

    available_by_type = Counter(need)

    slot_rows: List[Tuple[str, int, dict]] = []
    for bot in bot_list:
        free = max(0, max_inventory - _inventory_size(bot))
        for slot_idx in range(min(max_slots_per_bot, free)):
            slot_rows.append((str(bot["id"]), slot_idx, bot))

    scored_edges: List[Tuple[int, str, str, ItemCandidate]] = []
    for bot_id, _slot, bot in slot_rows:
        for cand in cand_list:
            score = distance_cost(bot, cand)
            scored_edges.append((score, bot_id, cand.item_id, cand))

    scored_edges.sort(key=lambda x: (x[0], x[1], x[2]))

    used_items: set[str] = set()
    used_slots: Counter = Counter()
    slot_caps = Counter(slot_bot_id for slot_bot_id, _slot, _bot in slot_rows)

    for _score, bot_id, item_id, cand in scored_edges:
        if item_id in used_items:
            continue
        if used_slots[bot_id] >= slot_caps[bot_id]:
            continue
        if available_by_type[cand.item_type] <= 0:
            continue
        assigned[bot_id].append(cand)
        used_items.add(item_id)
        used_slots[bot_id] += 1
        available_by_type[cand.item_type] -= 1

    return assigned


def choose_best_stand(bot_pos: Pos, item: ItemCandidate, distance: Callable[[Pos, Pos], Optional[int]]) -> Optional[Pos]:
    best: Optional[Pos] = None
    best_d: Optional[int] = None
    for stand in item.stands:
        d = distance(bot_pos, stand)
        if d is None:
            continue
        if best_d is None or d < best_d:
            best, best_d = stand, d
    return best
