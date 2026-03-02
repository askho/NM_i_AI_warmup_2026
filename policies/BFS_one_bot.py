from __future__ import annotations

import itertools
import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from planning.pathfinding import bfs_path, neighbors4

logger = logging.getLogger("policy.BFS_one_bot")

Pos = Tuple[int, int]
Action = Dict[str, Any]


def _to_pos(p: Any) -> Optional[Pos]:
    if isinstance(p, dict):
        if "position" in p:
            return _to_pos(p.get("position"))
        if "x" in p and "y" in p:
            try:
                return int(p.get("x", 0) or 0), int(p.get("y", 0) or 0)
            except (TypeError, ValueError):
                return None
    if isinstance(p, (list, tuple)) and len(p) >= 2:
        try:
            return int(p[0]), int(p[1])
        except (TypeError, ValueError):
            return None
    return None


def _order_sequence(order: Dict[str, Any], fallback_index: int = -1) -> int:
    raw_id = str(order.get("id", ""))
    suffix = raw_id.rsplit("_", 1)[-1]
    try:
        return int(suffix)
    except (TypeError, ValueError):
        return fallback_index


def _select_active_order(orders: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    indexed = [
        (i, o)
        for i, o in enumerate(orders or [])
        if isinstance(o, dict) and o.get("status") == "active"
    ]
    if not indexed:
        return None
    non_complete = [(i, o) for i, o in indexed if not bool(o.get("complete", False))]
    candidates = non_complete or indexed
    _, best = max(candidates, key=lambda io: _order_sequence(io[1], io[0]))
    return best


def _remaining_need_counts(order: Optional[Dict[str, Any]]) -> Counter:
    need = Counter()
    if not order:
        return need
    req = order.get("items_required", []) or order.get("items", []) or []
    delivered = order.get("items_delivered", []) or []
    need.update(str(t) for t in req)
    need.subtract(str(t) for t in delivered)
    return Counter({k: v for k, v in need.items() if v > 0})


def _move_action(from_pos: Pos, to_pos: Pos) -> str:
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]
    if dx == 1 and dy == 0:
        return "move_right"
    if dx == -1 and dy == 0:
        return "move_left"
    if dx == 0 and dy == 1:
        return "move_down"
    if dx == 0 and dy == -1:
        return "move_up"
    return "wait"


def _bfs_to_nearest(start: Pos, goals: set[Pos], controller, obstacles: set[Pos]) -> List[Pos]:
    if start in goals:
        return [start]
    best: List[Pos] = []
    for g in goals:
        p = bfs_path(start, g, width=controller.width, height=controller.height, walls=set(getattr(controller, "walls", set())), blocked=set(obstacles))
        if p and (not best or len(p) < len(best)):
            best = p
    return best


def plan_item_run(state, controller, item_types, walls, blocked, bot):
    types: List[str] = []
    for t in item_types:
        if t and t not in types:
            types.append(str(t))
    if not types:
        return [], []

    bot_pos = _to_pos(bot.get("position")) or (0, 0)
    obstacles = {p for p in (_to_pos(x) for x in (list(walls) + list(blocked))) if p is not None}
    obstacles.discard(bot_pos)

    shelves_by_type: Dict[str, List[Pos]] = {}
    for item in state.get("items", []):
        if not isinstance(item, dict):
            continue
        itype = item.get("type")
        ipos = _to_pos(item.get("position"))
        if itype is None or ipos is None:
            continue
        shelves_by_type.setdefault(str(itype), []).append(ipos)

    options: Dict[str, List[Tuple[Pos, Pos]]] = {}
    for t in types:
        opts: List[Tuple[Pos, Pos]] = []
        for shelf in shelves_by_type.get(t, []):
            for stand in neighbors4(shelf):
                if controller.in_bounds(stand) and stand not in obstacles:
                    opts.append((shelf, stand))
        if not opts:
            return [], []
        options[t] = opts

    drop_stands = {p for p in neighbors4(controller.dropoff) if controller.in_bounds(p) and p not in obstacles}
    if not drop_stands:
        return [], []

    best_total = None
    best_choice = None
    best_first = []

    for perm in itertools.permutations(types, len(types)):
        for choice in itertools.product(*(options[t] for t in perm)):
            cur = bot_pos
            total_steps = 0
            first_path: List[Pos] = []
            ok = True
            for idx, (_shelf, stand) in enumerate(choice):
                p = bfs_path(cur, stand, width=controller.width, height=controller.height, walls=set(getattr(controller, "walls", set())), blocked=set(obstacles))
                if not p:
                    ok = False
                    break
                if idx == 0:
                    first_path = p
                total_steps += len(p) - 1
                cur = stand
            if not ok:
                continue

            to_drop = _bfs_to_nearest(cur, drop_stands, controller, obstacles)
            if not to_drop:
                continue
            total_steps += len(to_drop) - 1

            if best_total is None or total_steps < best_total:
                best_total = total_steps
                best_choice = choice
                best_first = first_path

    if not best_choice:
        return [], []
    return [shelf for shelf, _ in best_choice], best_first


def _pick_item_if_adjacent(bot: Dict[str, Any], target_item: Optional[Dict[str, Any]], need: Counter) -> Optional[Action]:
    if not isinstance(target_item, dict):
        return None
    item_pos = _to_pos(target_item.get("position"))
    bot_pos = _to_pos(bot.get("position")) or (0, 0)
    if item_pos is None:
        return None
    if abs(bot_pos[0] - item_pos[0]) + abs(bot_pos[1] - item_pos[1]) != 1:
        return None
    if len(bot.get("inventory", []) or []) >= 3:
        return None
    t = str(target_item.get("type"))
    if need and need.get(t, 0) <= 0:
        return None
    return {"bot": bot.get("id"), "action": "pick_up", "item_id": target_item.get("id")}


def _inventory_types(inv: List[Any]) -> List[str]:
    out: List[str] = []
    for it in inv or []:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict) and it.get("type"):
            out.append(str(it.get("type")))
    return out


def policy(state: Dict[str, Any], controller) -> List[Action]:
    if state.get("type") != "game_state":
        return []

    bots = state.get("bots", [])
    if not isinstance(bots, list) or not bots:
        return []
    bot = bots[0]

    blocked = controller.blocked_positions(state)
    walls = set(getattr(controller, "walls", set()))

    active_order = _select_active_order(state.get("orders", []) or [])
    need_counts = _remaining_need_counts(active_order)

    inv = bot.get("inventory", []) or []
    inv_types = _inventory_types(inv)

    if _to_pos(bot.get("position")) == controller.dropoff and any(need_counts.get(t, 0) > 0 for t in inv_types):
        return [{"bot": bot.get("id"), "action": "drop_off"}]

    if len(inv) >= 3 or (inv and not need_counts):
        drop_path = bfs_path(
            start=_to_pos(bot.get("position")) or (0, 0),
            goal=controller.dropoff,
            width=controller.width,
            height=controller.height,
            walls=set(getattr(controller, "walls", set())),
            blocked=set(blocked),
        )
        if drop_path and len(drop_path) >= 2:
            controller._debug_last_target = controller.dropoff
            controller._debug_last_inventory_count = len(inv)
            return [{"bot": bot.get("id"), "action": _move_action(drop_path[0], drop_path[1])}]

    active_items = []
    preview_items = []
    for it in state.get("items", []) or []:
        if not isinstance(it, dict):
            continue
        t = str(it.get("type"))
        if need_counts.get(t, 0) > 0:
            active_items.append(it)
        else:
            preview_items.append(it)

    allocated = controller.allocate_items_for_bot(bot, active_items, preview_items)
    wanted_types = [it.get("type") for it in allocated if isinstance(it, dict)]

    # Never plan preview pickups while active needs still exist.
    # This avoids deadlocking a full inventory with non-deliverable items.
    if need_counts:
        wanted_types = [t for t in wanted_types if need_counts.get(str(t), 0) > 0]
    shelves, first_path = plan_item_run(state, controller, wanted_types, walls, blocked, bot)

    target_item = None
    if shelves:
        first_shelf = shelves[0]
        for it in state.get("items", []):
            if isinstance(it, dict) and _to_pos(it.get("position")) == first_shelf:
                target_item = it
                break

    if target_item is None:
        bot_pos = _to_pos(bot.get("position")) or (0, 0)
        for it in active_items:
            if not isinstance(it, dict):
                continue
            ip = _to_pos(it.get("position"))
            if ip is not None and abs(bot_pos[0] - ip[0]) + abs(bot_pos[1] - ip[1]) == 1:
                target_item = it
                break

    pick_action = _pick_item_if_adjacent(bot, target_item, need_counts)
    if pick_action:
        controller._debug_last_target = _to_pos(target_item.get("position")) if target_item else None
        controller._debug_last_inventory_count = len(inv)
        return [pick_action]

    if first_path and len(first_path) >= 2:
        controller._debug_last_target = first_path[-1]
        controller._debug_last_inventory_count = len(inv)
        return [{"bot": bot.get("id"), "action": _move_action(first_path[0], first_path[1])}]

    controller._debug_last_target = None
    controller._debug_last_inventory_count = len(inv)
    logger.info("No feasible plan for round=%s; waiting", state.get("round"))
    return [{"bot": bot.get("id"), "action": "wait"}]
