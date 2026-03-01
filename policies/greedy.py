# policies/greedy.py
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger("policy.greedy")

Pos = Tuple[int, int]
Action = Dict[str, Any]


def policy(state: Dict[str, Any], controller) -> List[Action]:
    """
    Simple greedy policy:
      - Deliver if carrying items needed for active order
      - Else pick nearest needed item (avoid duplicates per round)
      - Movement is dumb (controller.move_toward), conflicts handled by BotController.act()
    """
    if state.get("type") != "game_state":
        return []

    bots = state.get("bots", [])
    items = state.get("items", [])
    orders = state.get("orders", [])
    drop_off_raw = state.get("drop_off", [0, 0])

    if not isinstance(bots, list) or not isinstance(items, list) or not isinstance(orders, list):
        return []

    active = _get_active_order(orders)
    if active is None:
        # nothing to do
        return [{"bot": b["id"], "action": "wait"} for b in bots if isinstance(b, dict) and isinstance(b.get("id"), int)]
    
    required, delivered = _get_required_delivered(active)
    needed_now = required - delivered

    drop_off: Pos = _to_pos(drop_off_raw)

    # Precompute how many needed items are already carried by bots (so we don't over-pick)
    carried_needed = Counter()
    for b in bots:
        if not isinstance(b, dict):
            continue
        inv = b.get("inventory", [])
        if not isinstance(inv, list):
            continue
        for t in inv:
            if isinstance(t, str) and needed_now[t] > 0:
                carried_needed[t] += 1

    remaining_for_pick = Counter(needed_now)
    for t, c in carried_needed.items():
        if remaining_for_pick[t] <= 0:
            continue
        remaining_for_pick[t] = max(0, remaining_for_pick[t] - c)
        if remaining_for_pick[t] == 0:
            del remaining_for_pick[t]

    # Reserve concrete item_ids so multiple bots don't chase the exact same shelf this round
    reserved_item_ids: Set[str] = set()

    actions: List[Action] = []

    for b in bots:
        if not isinstance(b, dict):
            continue

        bot_id = b.get("id")
        pos_raw = b.get("position")
        inv_raw = b.get("inventory", [])

        if not isinstance(bot_id, int) or not (isinstance(pos_raw, (list, tuple)) and len(pos_raw) == 2):
            continue

        pos: Pos = _to_pos(pos_raw)
        inv: List[str] = [str(x) for x in inv_raw] if isinstance(inv_raw, list) else []

        # 1) If at dropoff and have something that can be delivered -> drop_off
        if pos == drop_off and _has_deliverable(inv, needed_now):
            actions.append({"bot": bot_id, "action": "drop_off"})
            continue

        # 2) If carrying anything deliverable -> head to dropoff
        if _has_deliverable(inv, needed_now):
            a = controller.move_toward(
                bot_id=bot_id,
                pos=pos,
                target=drop_off,
                blocked_positions=set(controller.world.walls) if getattr(controller, "world", None) else set(),
            )
            actions.append(a)
            continue

        # 3) If inventory full and nothing deliverable, just wait (avoid thrashing)
        if len(inv) >= getattr(controller, "max_inventory", 3):
            actions.append({"bot": bot_id, "action": "wait"})
            continue

        # 4) Otherwise: pick nearest needed shelf item (greedy)
        choice = _choose_nearest_item_to_pick(
            bot_pos=pos,
            items=items,
            remaining_for_pick=remaining_for_pick,
            reserved_item_ids=reserved_item_ids,
            controller=controller,
        )

        if choice is None:
            actions.append({"bot": bot_id, "action": "wait"})
            continue

        item_id, item_pos, approach_pos, item_type = choice

        # If adjacent to the shelf already -> pick_up
        if _manhattan(pos, item_pos) == 1:
            actions.append({"bot": bot_id, "action": "pick_up", "item_id": item_id})
            # mark it reserved so nobody else aims for it this round
            reserved_item_ids.add(item_id)
            # also reduce remaining demand for this type
            if remaining_for_pick[item_type] > 0:
                remaining_for_pick[item_type] -= 1
                if remaining_for_pick[item_type] == 0:
                    del remaining_for_pick[item_type]
            continue

        # Else move toward the approach position (adjacent walkable cell)
        a = controller.move_toward(
            bot_id=bot_id,
            pos=pos,
            target=approach_pos,
            blocked_positions=controller.world.walls if getattr(controller, "world", None) else set(),
        )
        actions.append(a)

        # Reserve immediately so other bots don't choose the same shelf this round
        reserved_item_ids.add(item_id)
        if remaining_for_pick[item_type] > 0:
            remaining_for_pick[item_type] -= 1
            if remaining_for_pick[item_type] == 0:
                del remaining_for_pick[item_type]

    logger.debug(
        "Greedy | round=%s active=%s needed_now=%s remaining_for_pick=%s",
        state.get("round"),
        active.get("id"),
        dict(needed_now),
        dict(remaining_for_pick),
    )

    return actions


# -------------------------
# Helpers
# -------------------------

def _as_counter(x: Any) -> Counter:
    if isinstance(x, Counter):
        return x
    if isinstance(x, dict):
        return Counter({str(k): int(v) for k, v in x.items()})
    if isinstance(x, list):
        return Counter([str(t) for t in x])
    return Counter()

def _get_required_delivered(active: Dict[str, Any]) -> Tuple[Counter, Counter]:
    required = _as_counter(
        active.get("items_required")
        or active.get("required_items")
        or active.get("items")
        or []
    )
    delivered = _as_counter(
        active.get("items_delivered")
        or active.get("delivered_items")
        or active.get("delivered")
        or []
    )
    return required, delivered

def _get_active_order(orders: List[dict]) -> Optional[dict]:
    for o in orders:
        if isinstance(o, dict) and o.get("status") == "active":
            return o
    return orders[0] if orders and isinstance(orders[0], dict) else None


def _to_pos(xy: Sequence[int]) -> Pos:
    return (int(xy[0]), int(xy[1]))


def _manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _neighbors4(p: Pos) -> List[Pos]:
    x, y = p
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def _has_deliverable(inventory: List[str], needed_now: Counter) -> bool:
    # deliverable if inventory contains any type that is still needed for active order
    for t in inventory:
        if needed_now[t] > 0:
            return True
    return False


def _choose_nearest_item_to_pick(
    *,
    bot_pos: Pos,
    items: List[Any],
    remaining_for_pick: Counter,
    reserved_item_ids: Set[str],
    controller,
) -> Optional[Tuple[str, Pos, Pos, str]]:
    """
    Returns (item_id, item_pos, approach_pos, item_type) for the best candidate.
    """
    best = None  # (dist, item_id, item_pos, approach_pos, item_type)

    for it in items:
        if not isinstance(it, dict):
            continue
        item_id = it.get("id")
        item_type = it.get("type")
        pos_raw = it.get("position")

        if not (isinstance(item_id, str) and isinstance(item_type, str) and isinstance(pos_raw, (list, tuple)) and len(pos_raw) == 2):
            continue
        if item_id in reserved_item_ids:
            continue
        if remaining_for_pick[item_type] <= 0:
            continue

        item_pos: Pos = _to_pos(pos_raw)

        # Need an adjacent walkable cell to stand on (pickup is adjacent to shelf)
        approach_candidates = [p for p in _neighbors4(item_pos) if controller.is_free_static(p)]
        if not approach_candidates:
            continue

        approach_pos = min(approach_candidates, key=lambda p: _manhattan(bot_pos, p))
        dist = _manhattan(bot_pos, approach_pos)

        key = (dist, item_id)
        if best is None or key < (best[0], best[1]):
            best = (dist, item_id, item_pos, approach_pos, item_type)

    if best is None:
        return None

    _, item_id, item_pos, approach_pos, item_type = best
    return (item_id, item_pos, approach_pos, item_type)