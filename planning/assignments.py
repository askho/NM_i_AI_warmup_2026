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
    """Balanced min-cost assignment over bot pickup slots.

    Uses a multi-wave assignment pass so medium/hard maps don't over-concentrate
    work on a single nearest bot while others idle.
    """
    bot_list = [b for b in bots if isinstance(b, dict) and "id" in b]
    cand_list = [c for c in candidates if need.get(c.item_type, 0) > 0]

    assigned: Dict[str, List[ItemCandidate]] = {str(b["id"]): [] for b in bot_list}
    if not bot_list or not cand_list:
        return assigned

    available_by_type = Counter(need)
    used_items: set[str] = set()

    slot_caps: Dict[str, int] = {}
    for bot in bot_list:
        bot_id = str(bot["id"])
        free = max(0, max_inventory - _inventory_size(bot))
        slot_caps[bot_id] = min(max_slots_per_bot, free)

    # Pre-score edges once and reuse in each wave.
    edge_cost: Dict[tuple[str, str], int] = {}
    for bot in bot_list:
        bot_id = str(bot["id"])
        for cand in cand_list:
            edge_cost[(bot_id, cand.item_id)] = distance_cost(bot, cand)

    # Wave 1: each bot gets at most one item before anyone gets a second.
    max_waves = max(slot_caps.values(), default=0)
    for wave in range(max_waves):
        for bot in bot_list:
            bot_id = str(bot["id"])
            if len(assigned[bot_id]) > wave:
                continue
            if len(assigned[bot_id]) >= slot_caps.get(bot_id, 0):
                continue

            best: Optional[Tuple[int, ItemCandidate]] = None
            for cand in cand_list:
                if cand.item_id in used_items:
                    continue
                if available_by_type[cand.item_type] <= 0:
                    continue
                score = edge_cost.get((bot_id, cand.item_id), 10**6)
                if best is None or score < best[0] or (score == best[0] and cand.item_id < best[1].item_id):
                    best = (score, cand)

            if best is None:
                continue

            chosen = best[1]
            assigned[bot_id].append(chosen)
            used_items.add(chosen.item_id)
            available_by_type[chosen.item_type] -= 1

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
