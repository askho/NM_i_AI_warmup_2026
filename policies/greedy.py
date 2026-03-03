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
      - Movement is dumb (controller.move_toward if present; fallback otherwise)
      - Conflicts handled by BotController.act()
    """
    if state.get("type") != "game_state":
        return []

    bots = state.get("bots", [])
    items = state.get("items", [])
    orders = state.get("orders", [])

    if not isinstance(bots, list) or not isinstance(items, list) or not isinstance(orders, list):
        return []

    active = _get_active_order(orders)
    if active is None:
        return [{"bot": b["id"], "action": "wait"} for b in bots if isinstance(b, dict) and "id" in b]

    required, delivered = _get_required_delivered(active)
    needed_now = required - delivered

    # Use controller dropoff (member variable) instead of state/world
    drop_off: Pos = getattr(controller, "dropoff", (0, 0))

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

    reserved_item_ids: Set[str] = set()
    actions: List[Action] = []

    blocked_static: Set[Pos] = set(getattr(controller, "walls", set()))
    max_inventory = int(getattr(controller, "max_inventory", 3))

    for b in bots:
        if not isinstance(b, dict):
            continue

        bot_id = b.get("id")
        pos_raw = b.get("position")
        inv_raw = b.get("inventory", [])

        if bot_id is None:
            continue

        pos = _to_pos(pos_raw)
        if pos is None:
            continue

        inv: List[str] = [str(x) for x in inv_raw] if isinstance(inv_raw, list) else []

        # 1) If at dropoff and have something that can be delivered -> drop_off
        if pos == drop_off and _has_deliverable(inv, needed_now):
            actions.append({"bot": bot_id, "action": "drop_off"})
            continue

        # 2) If carrying anything deliverable -> head to dropoff
        if _has_deliverable(inv, needed_now):
            actions.append(_move_toward(controller, bot_id, pos, drop_off, blocked_static))
            continue

        # 3) If inventory full and nothing deliverable, just wait (avoid thrashing)
        if len(inv) >= max_inventory:
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
            reserved_item_ids.add(item_id)
            if remaining_for_pick[item_type] > 0:
                remaining_for_pick[item_type] -= 1
                if remaining_for_pick[item_type] == 0:
                    del remaining_for_pick[item_type]
            continue

        # Else move toward the approach position (adjacent walkable cell)
        actions.append(_move_toward(controller, bot_id, pos, approach_pos, blocked_static))

        # Reserve immediately so other bots don't choose the same shelf this round
        reserved_item_ids.add(item_id)
        if remaining_for_pick[item_type] > 0:
            remaining_for_pick[item_type] -= 1
            if remaining_for_pick[item_type] == 0:
                del remaining_for_pick[item_type]

    logger.debug(
        "Greedy | round=%s active=%s needed_now=%s remaining_for_pick=%s",
        state.get("round"),
        active.get("id") if isinstance(active, dict) else None,
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


def _to_pos(obj: Any) -> Optional[Pos]:
    # Accept {x,y}, {"position":{x,y}}, [x,y], (x,y)
    if isinstance(obj, dict):
        if "position" in obj:
            return _to_pos(obj.get("position"))
        if "x" in obj and "y" in obj:
            try:
                return int(obj.get("x", 0) or 0), int(obj.get("y", 0) or 0)
            except (TypeError, ValueError):
                return None
    if isinstance(obj, (list, tuple)) and len(obj) >= 2:
        try:
            return int(obj[0]), int(obj[1])
        except (TypeError, ValueError):
            return None
    return None


def _manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _neighbors4(p: Pos) -> List[Pos]:
    x, y = p
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def _has_deliverable(inventory: List[str], needed_now: Counter) -> bool:
    for t in inventory:
        if needed_now[t] > 0:
            return True
    return False


def _move_toward(controller, bot_id: Any, pos: Pos, target: Pos, blocked_positions: Set[Pos]) -> Action:
    """
    Prefer controller.move_toward(...) if it exists; otherwise do a tiny dumb step here.
    blocked_positions should be static walls (and/or any other static blocks).
    """
    fn = getattr(controller, "move_toward", None)
    if callable(fn):
        # Be tolerant to signature differences.
        try:
            return fn(bot_id=bot_id, pos=pos, target=target, blocked_positions=blocked_positions)
        except TypeError:
            try:
                return fn(bot_id, pos, target, blocked_positions)
            except TypeError:
                try:
                    return fn(bot_id=bot_id, pos=pos, target=target)
                except TypeError:
                    pass  # fall back below

    tx, ty = target
    x, y = pos
    dx = tx - x
    dy = ty - y

    # Choose axis by which distance is larger
    candidates: List[Tuple[str, Pos]] = []
    if abs(dx) > abs(dy):
        if dx != 0:
            candidates.append(("move_right" if dx > 0 else "move_left", (x + (1 if dx > 0 else -1), y)))
        if dy != 0:
            candidates.append(("move_down" if dy > 0 else "move_up", (x, y + (1 if dy > 0 else -1))))
    else:
        if dy != 0:
            candidates.append(("move_down" if dy > 0 else "move_up", (x, y + (1 if dy > 0 else -1))))
        if dx != 0:
            candidates.append(("move_right" if dx > 0 else "move_left", (x + (1 if dx > 0 else -1), y)))

    is_free = getattr(controller, "is_free_static", None)
    in_bounds = getattr(controller, "in_bounds", None)

    for action_name, nxt in candidates:
        if nxt in blocked_positions:
            continue
        if callable(in_bounds) and not in_bounds(nxt):
            continue
        if callable(is_free) and not is_free(nxt):
            continue
        return {"bot": bot_id, "action": action_name}

    return {"bot": bot_id, "action": "wait"}


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
    is_free = getattr(controller, "is_free_static", None)

    for it in items:
        if not isinstance(it, dict):
            continue

        item_id = it.get("id")
        item_type = it.get("type")
        pos_raw = it.get("position")

        if not (isinstance(item_id, str) and isinstance(item_type, str)):
            continue
        if item_id in reserved_item_ids:
            continue
        if remaining_for_pick[item_type] <= 0:
            continue

        item_pos = _to_pos(pos_raw)
        if item_pos is None:
            continue

        # Need an adjacent walkable cell to stand on (pickup is adjacent to shelf)
        approach_candidates = []
        for p in _neighbors4(item_pos):
            if callable(is_free):
                if is_free(p):
                    approach_candidates.append(p)
            else:
                # If controller doesn't expose is_free_static, at least keep bounds check if possible
                in_bounds = getattr(controller, "in_bounds", None)
                if callable(in_bounds) and in_bounds(p):
                    approach_candidates.append(p)

        if not approach_candidates:
            continue

        approach_pos = min(approach_candidates, key=lambda p: _manhattan(bot_pos, p))
        dist = _manhattan(bot_pos, approach_pos)

        key = (dist, item_id)
        if best is None or key < (best[0], best[1]):
            best = (dist, item_id, item_pos, approach_pos, item_type)

    if best is None:
        return None #

    _, item_id, item_pos, approach_pos, item_type = best
    return (item_id, item_pos, approach_pos, item_type)

# Backward-compatible export used by tests
from policies.BFS_one_bot import plan_item_run  # noqa: E402
