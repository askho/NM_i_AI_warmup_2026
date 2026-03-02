from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from planning.pathfinding import bfs_path, neighbors4

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


def _inventory_types(inv: List[Any]) -> List[str]:
    out: List[str] = []
    for it in inv or []:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict) and it.get("type"):
            out.append(str(it.get("type")))
    return out


def _path_to_any(start: Pos, goals: set[Pos], controller, blocked: set[Pos]) -> List[Pos]:
    if not goals:
        return []
    best: List[Pos] = []
    for g in goals:
        p = bfs_path(
            start,
            g,
            width=controller.width,
            height=controller.height,
            walls=set(getattr(controller, "walls", set())),
            blocked=set(blocked),
        )
        if p and (not best or len(p) < len(best)):
            best = p
    return best


def _distance_to_item(bot_pos: Pos, item: Dict[str, Any], controller, blocked: set[Pos]) -> Tuple[int, List[Pos]]:
    shelf = _to_pos(item.get("position"))
    if shelf is None:
        return 10**9, []
    stands = {p for p in neighbors4(shelf) if controller.in_bounds(p) and p not in blocked}
    path = _path_to_any(bot_pos, stands, controller, blocked)
    if not path:
        return 10**9, []
    return len(path) - 1, path


def _can_drop_now(bot: Dict[str, Any], need: Counter, dropoff: Pos) -> bool:
    if _to_pos(bot.get("position")) != dropoff:
        return False
    inv_types = _inventory_types(bot.get("inventory", []) or [])
    return any(need.get(t, 0) > 0 for t in inv_types)


def policy(state: Dict[str, Any], controller) -> List[Action]:
    if state.get("type") != "game_state":
        return []

    bots = [b for b in (state.get("bots", []) or []) if isinstance(b, dict)]
    if not bots:
        return []

    active_order = _select_active_order(state.get("orders", []) or [])
    need = _remaining_need_counts(active_order)
    if not need:
        return [{"bot": b.get("id"), "action": "wait"} for b in bots]

    blocked_base = controller.blocked_positions(state)
    candidates = [
        it
        for it in (state.get("items", []) or [])
        if isinstance(it, dict) and need.get(str(it.get("type")), 0) > 0
    ]

    assignments: Dict[str, Dict[str, Any]] = {}
    unassigned_bots = {str(b.get("id")): b for b in bots}
    free_items = list(candidates)

    # Greedy global assignment: repeatedly take best bot-item pair by shortest path.
    while unassigned_bots and free_items:
        best_pair = None
        for bot_key, bot in unassigned_bots.items():
            bot_pos = _to_pos(bot.get("position")) or (0, 0)
            blocked = set(blocked_base)
            blocked.discard(bot_pos)
            for item in free_items:
                d, p = _distance_to_item(bot_pos, item, controller, blocked)
                if d >= 10**9:
                    continue
                score = (d, str(item.get("id", "")), bot_key)
                if best_pair is None or score < best_pair[0]:
                    best_pair = (score, bot_key, item, p)
        if best_pair is None:
            break
        _, bot_key, item, path = best_pair
        assignments[bot_key] = {"item": item, "path": path}
        free_items = [it for it in free_items if it.get("id") != item.get("id")]
        unassigned_bots.pop(bot_key, None)

    actions: List[Action] = []
    reserved_next: set[Pos] = set()

    for bot in sorted(bots, key=lambda b: str(b.get("id"))):
        bot_id = bot.get("id")
        bot_key = str(bot_id)
        bot_pos = _to_pos(bot.get("position")) or (0, 0)
        inv = bot.get("inventory", []) or []

        if _can_drop_now(bot, need, controller.dropoff):
            actions.append({"bot": bot_id, "action": "drop_off"})
            reserved_next.add(bot_pos)
            continue

        # If full inventory, route toward dropoff.
        if len(inv) >= 3:
            drop_path = bfs_path(
                bot_pos,
                controller.dropoff,
                width=controller.width,
                height=controller.height,
                walls=set(getattr(controller, "walls", set())),
                blocked=set(blocked_base - {bot_pos}),
            )
            if drop_path and len(drop_path) >= 2 and drop_path[1] not in reserved_next:
                nxt = drop_path[1]
                actions.append({"bot": bot_id, "action": _move_action(bot_pos, nxt)})
                reserved_next.add(nxt)
            else:
                actions.append({"bot": bot_id, "action": "wait"})
                reserved_next.add(bot_pos)
            continue

        # Pick up assigned item if adjacent.
        assignment = assignments.get(bot_key)
        target = assignment.get("item") if assignment else None
        if isinstance(target, dict):
            item_pos = _to_pos(target.get("position"))
            if item_pos and abs(bot_pos[0] - item_pos[0]) + abs(bot_pos[1] - item_pos[1]) == 1:
                actions.append({"bot": bot_id, "action": "pick_up", "item_id": target.get("id")})
                reserved_next.add(bot_pos)
                continue

        # Move toward assigned target stand.
        path = assignment.get("path") if assignment else None
        if path and len(path) >= 2 and path[1] not in reserved_next:
            nxt = path[1]
            actions.append({"bot": bot_id, "action": _move_action(bot_pos, nxt)})
            reserved_next.add(nxt)
            continue

        actions.append({"bot": bot_id, "action": "wait"})
        reserved_next.add(bot_pos)

    return actions
