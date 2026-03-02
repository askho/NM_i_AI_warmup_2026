# policies/greedy.py
from __future__ import annotations

import logging
import itertools
from collections import Counter, deque
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from planning.assignments import allocate_items
from planning.pathfinding import bfs_path, is_free_cell, neighbors4


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


def plan_item_run(state, controller, item_types, walls, blocked, bot):
    """
    Single-bot planner (recomputed every round).

    Inputs:
      - item_types: list with 1–3 requested item types (may include duplicates)
      - walls: iterable of (x,y)
      - blocked: iterable of (x,y) (often includes items + bots)
      - bot: this bot dict

    Returns:
      (ordered_item_positions, path_to_first_stand_cell)

    Meaning:
      - ordered_item_positions: shelf positions (x,y) in the best visiting order
      - path_to_first_stand_cell: BFS path from current bot position to a *stand cell*
        (Manhattan-distance 1) from the first shelf in the plan.

    Notes:
      - Ignores other bots as obstacles (even if `blocked` includes them).
      - Treats shelf cells as blocked; you navigate to an adjacent stand cell.
      - Includes a final leg in the cost: end on a stand cell adjacent to dropoff.
      - If duplicates exist in item_types, we only visit that type once (can pick multiple from same shelf).
    """

    def as_pos(p):
        q = _to_pos(p)
        if q is None:
            return (0, 0)
        return q

    def bot_pos(b):
        p = b.get("position", b)
        if isinstance(p, dict):
            return (int(p.get("x", 0) or 0), int(p.get("y", 0) or 0))
        return (int(p[0]), int(p[1]))

    def path_len(path):
        return max(0, len(path) - 1)

    def bfs(start, goal, obstacles):
        if start == goal:
            return [start]
        q = deque([start])
        prev = {start: None}
        while q:
            cur = q.popleft()
            for nxt in neighbors4(cur):
                if nxt in prev:
                    continue
                if not controller.in_bounds(nxt):
                    continue
                if nxt in obstacles:
                    continue
                prev[nxt] = cur
                if nxt == goal:
                    # reconstruct
                    out = [nxt]
                    while out[-1] is not None:
                        out.append(prev[out[-1]])
                    out.pop()          # remove None
                    out.reverse()
                    return out
                q.append(nxt)
        return []

    # ---- dedupe types (preserve order) ----
    types = []
    for t in item_types:
        if t not in types:
            types.append(t)

    # ---- obstacles: walls + blocked, but remove ALL bot positions (ignore other bots) ----
    obstacles = set(as_pos(p) for p in walls) | set(as_pos(p) for p in blocked)

    for b in state.get("bots", []):
        if isinstance(b, dict) and b is not bot:
            obstacles.discard(bot_pos(b))

    start = bot_pos(bot)
    obstacles.discard(start)

    # ---- group shelves by type ----
    shelves_by_type = {}
    for item in state.get("items", []):
        t = item.get("type")
        p = item.get("position")
        if t is None or p is None:
            continue
        shelves_by_type.setdefault(t, []).append(as_pos(p))

    # ---- for each type: list of options (shelf_pos, stand_pos) ----
    options_by_type = {}
    for t in types:
        opts = []
        for shelf in shelves_by_type.get(t, []):
            # stand cells are free adjacent cells to the shelf
            for stand in neighbors4(shelf):
                if not controller.in_bounds(stand):
                    continue
                if stand in obstacles:
                    continue
                opts.append((shelf, stand))
        options_by_type[t] = opts
        if not opts:
            return [], []

    # ---- dropoff stand cells (used only for scoring) ----
    drop = controller.dropoff
    drop_stands = [p for p in neighbors4(drop) if controller.in_bounds(p) and p not in obstacles]
    if not drop_stands:
        return [], []

    best_total = None
    best_perm = None
    best_choice = None
    best_first_path = None

    # types ≤ 3 → brute force is fine
    for perm in itertools.permutations(types, len(types)):
        per_type_opts = [options_by_type[t] for t in perm]

        for choice in itertools.product(*per_type_opts):
            cur = start
            total = 0
            first_path = None

            ok = True
            for i, (shelf, stand) in enumerate(choice):
                pth = bfs(cur, stand, obstacles)
                if not pth:
                    ok = False
                    break
                if i == 0:
                    first_path = pth
                total += path_len(pth)
                cur = stand

            if not ok:
                continue

            # add cost to end adjacent to dropoff
            best_drop_cost = None
            for dstand in drop_stands:
                dpth = bfs(cur, dstand, obstacles)
                if not dpth:
                    continue
                c = path_len(dpth)
                if best_drop_cost is None or c < best_drop_cost:
                    best_drop_cost = c

            if best_drop_cost is None:
                continue

            total += best_drop_cost

            if best_total is None or total < best_total:
                best_total = total
                best_perm = perm
                best_choice = choice
                best_first_path = first_path

    if best_choice is None:
        return [], []

    ordered_shelves = [shelf for (shelf, _stand) in best_choice]
    return ordered_shelves, (best_first_path or [])

def extract_target_item_id(
    state,
    adjacent_block,
    allocated_itemtype,
    item_positions_by_type,
):
    """
    Find the concrete item_id to pick up.

    adjacent_block: the bot's current (or planned) stand cell (x,y)
    allocated_itemtype: e.g. "milk"
    item_positions_by_type: {"milk": [[5,3], ...], ...}

    Returns: item_id string, or None if nothing of that type is adjacent.
    """

    def to_pos(p):
        return (int(p[0]), int(p[1]))

    adj = set(neighbors4(adjacent_block))

    # Prefer shelves from the provided mapping (stable, already filtered/ordered by you)
    for shelf_pos in item_positions_by_type.get(allocated_itemtype, []):
        shelf = to_pos(shelf_pos)
        if shelf not in adj:
            continue

        # Find the matching item object in state to get its id
        for item in state.get("items", []):
            if item.get("type") != allocated_itemtype:
                continue
            if to_pos(item.get("position")) == shelf:
                return item.get("id")

    return None

# policies/greedy.py (put this ABOVE policy())

def decide_action_one_bot(
    state,
    controller,
    bot,
    *,
    blocked,
    walls,
    target_item=None,   # dict like {"id": "...", "type": "...", "position": [x,y]}
    path=None,          # BFS path list [(x,y), (x,y), ...] toward your current goal (stand cell)
    target_pos=None,    # optional fallback goal (x,y) if you don't pass path
):
    """
    One-bot "action chooser" to keep policy() clean.

    Priority:
      1) DROP OFF if:
         - bot carries >=1 item that the ACTIVE order still needs
         - manhattan(bot_pos, dropoff) <= 1
      2) PICK UP if:
         - target_item is provided
         - inventory has room
         - manhattan(bot_pos, target_item.position) <= 1
         - and ACTIVE order still needs that item type (if there is an active order)
      3) Otherwise MOVE one step along `path` (if provided), else step toward `target_pos`.
      4) Else WAIT.

    Uses only the function args for obstacles (walls + blocked).
    """

    def manhattan(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def bot_pos(b):
        # prefer controller helper if it exists
        if hasattr(controller, "_position"):
            return controller._position(b)
        p = b.get("position", b)
        if isinstance(p, dict):
            return (int(p.get("x", 0) or 0), int(p.get("y", 0) or 0))
        return (int(p[0]), int(p[1]))

    def as_pos(p):
        q = _to_pos(p)
        if q is None:
            return (0, 0)
        return q

    def move_action(from_pos, to_pos):
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

    bot_id = bot.get("id")
    pos = bot_pos(bot)

    obstacles = set(tuple(w) if isinstance(w, (list, tuple)) else w for w in walls) | set(
        tuple(b) if isinstance(b, (list, tuple)) else b for b in blocked
    )
    obstacles.discard(pos)  # don't block yourself

    inv = bot.get("inventory", []) or []
    inv_types = []
    for it in inv:
        if isinstance(it, dict):
            inv_types.append(it.get("type"))
        else:
            inv_types.append(it)  # sometimes stored as type string

    # ---- find ACTIVE order + what it still needs ----
    active_order = None
    for o in state.get("orders", []):
        if isinstance(o, dict) and o.get("status") == "active" and not o.get("complete", False):
            active_order = o
            break

    need = {}
    if active_order:
        req = active_order.get("items_required", []) or []
        delivered = active_order.get("items_delivered", []) or []
        for t in req:
            need[t] = need.get(t, 0) + 1
        for t in delivered:
            if t in need:
                need[t] -= 1

    def active_needs_type(t):
        if not active_order:
            return True  # if no active order found, don't block pickup/drop logic
        return need.get(t, 0) > 0

    # ---- 1) DROP OFF only when standing on dropoff and carrying needed item(s) ----
    if active_order:
        carries_needed = any(active_needs_type(t) for t in inv_types if t is not None)
        if carries_needed and pos == controller.dropoff:
            return {"bot": bot_id, "action": "drop_off"}

    # ---- 2) PICK UP if near the target shelf and it is needed (and room) ----
    if target_item and len(inv) < 3:
        item_pos = target_item.get("position")
        item_type = target_item.get("type")
        if item_pos is not None and manhattan(pos, as_pos(item_pos)) <= 1:
            if item_type is None or active_needs_type(item_type):
                return {"bot": bot_id, "action": "pick_up", "item_id": target_item.get("id")}

    # ---- 3) MOVE along path (preferred), else toward target_pos ----
    if path and len(path) >= 2:
        nxt = path[1]
        if controller.in_bounds(nxt) and nxt not in obstacles and controller.is_free_static(nxt):
            return {"bot": bot_id, "action": move_action(pos, nxt)}
        return {"bot": bot_id, "action": "wait"}

    if target_pos is not None:
        tx, ty = target_pos
        x, y = pos

        # simple "try best axis then fallback"
        candidates = []
        if abs(tx - x) >= abs(ty - y):
            candidates.append((x + (1 if tx > x else -1), y) if tx != x else None)
            candidates.append((x, y + (1 if ty > y else -1)) if ty != y else None)
        else:
            candidates.append((x, y + (1 if ty > y else -1)) if ty != y else None)
            candidates.append((x + (1 if tx > x else -1), y) if tx != x else None)

        for c in candidates:
            if c is None:
                continue
            if controller.in_bounds(c) and c not in obstacles and controller.is_free_static(c):
                return {"bot": bot_id, "action": move_action(pos, c)}

    return {"bot": bot_id, "action": "wait"}

def policy(state: Dict[str, Any], controller) -> List[Action]:
    # Basic validation
    if state.get("type") != "game_state":
        return []

    bots = state.get("bots", [])
    if not isinstance(bots, list) or not bots:
        return []

    bot = bots[0]

    # Debug defaults consumed by client logging.
    controller._debug_last_target = None
    controller._debug_last_inventory_count = len(bot.get("inventory", []) or [])

    # Static helpers from controller
    blocked = controller.blocked_positions(state)
    item_positions_by_type = controller.build_item_positions_by_type(state)
    walls = getattr(controller, "walls", set())

    # Determine ACTIVE order and split items into active vs preview
    active_order = None
    for o in state.get("orders", []) or []:
        if isinstance(o, dict) and o.get("status") == "active":
            active_order = o
            break

    def _as_list(x):
        return list(x or [])

    active_items = []
    preview_items = []
    items = state.get("items", []) or []

    if active_order is not None:
        # Items whose type is requested by the active order are "active"
        req = _as_list(active_order.get("items_required") or active_order.get("items") or [])
        req_set = set(str(t) for t in req)
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("type")) in req_set:
                active_items.append(it)
            else:
                preview_items.append(it)
    else:
        preview_items = [it for it in items if isinstance(it, dict)]

    # Ask controller to allocate up to inventory capacity for this bot
    try:
        allocated_items = controller.allocate_items_for_bot(bot, active_items, preview_items)
    except TypeError:
        # Fallback if signature differs
        allocated_items = controller.allocate_items_for_bot(bot, active_items, preview_items)

    # Convert allocated_items to a list of types for the planner
    item_types = [it.get("type") for it in (allocated_items or []) if isinstance(it, dict) and it.get("type")]

    inv_now = bot.get("inventory", []) or []
    if len(inv_now) >= 3:
        drop_path = bfs_path(
            start=_to_pos(bot.get("position")) or (0, 0),
            goal=controller.dropoff,
            width=controller.width,
            height=controller.height,
            walls=set(getattr(controller, "walls", set())),
            blocked=set(blocked),
        )
        if drop_path:
            controller._debug_last_target = controller.dropoff
            return [
                decide_action_one_bot(
                    state,
                    controller,
                    bot,
                    blocked=blocked,
                    walls=walls,
                    path=drop_path,
                    target_pos=controller.dropoff,
                )
            ]

    ordered_shelves, path_to_first = plan_item_run(
        state=state,
        controller=controller,
        item_types=item_types,
        walls=walls,
        blocked=blocked,
        bot=bot,
    )

    # Determine target_item aligned with the planned first shelf, so pickup can happen.
    target_item = None
    if ordered_shelves:
        planned_shelf = _to_pos(ordered_shelves[0])
        for it in items:
            if not isinstance(it, dict):
                continue
            ip = _to_pos(it.get("position"))
            if planned_shelf is not None and ip == planned_shelf:
                target_item = it
                break

    # Fallback: if no planned shelf (or item vanished), keep old behavior.
    if target_item is None and allocated_items:
        first_type = allocated_items[0].get("type")
        for it in items:
            if isinstance(it, dict) and it.get("type") == first_type:
                target_item = it
                break

    # Debug fields consumed by client logging.
    try:
        inv = bot.get("inventory", []) or []
        controller._debug_last_target = _to_pos(target_item.get("position")) if isinstance(target_item, dict) else None
        controller._debug_last_inventory_count = len(inv)
    except Exception:
        pass

    action = decide_action_one_bot(
        state,
        controller,
        bot,
        blocked=blocked,
        walls=walls,
        target_item=target_item,
        path=path_to_first,
    )

    return [action]
