from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from itertools import permutations, product
from typing import Any, Deque, Dict, Iterable, List, Optional, Sequence, Tuple

from planning.assignments import ItemCandidate, assign_items_to_bots, choose_best_stand
from planning.pathfinding import bfs_path, neighbors4

Pos = Tuple[int, int]
Action = Dict[str, Any]


@dataclass
class Target:
    item_id: str
    item_type: str
    shelf_pos: Pos
    stand_pos: Pos


@dataclass
class BotIntent:
    mode: str = "IDLE"
    targets: List[Target] = None
    action_queue: Deque[Action] = None

    def __post_init__(self) -> None:
        if self.targets is None:
            self.targets = []
        if self.action_queue is None:
            self.action_queue = deque()


class OptimizedMultiBotPolicy:
    def __init__(self, horizon: int = 8, replan_every: int = 1) -> None:
        self.horizon = horizon
        self.replan_every = max(1, replan_every)
        self._last_replan_round = -1
        self._intents: Dict[str, BotIntent] = {}

    def __call__(self, state: Dict[str, Any], controller) -> List[Action]:
        if state.get("type") != "game_state":
            return []

        bots = [b for b in state.get("bots", []) if isinstance(b, dict) and "id" in b]
        active = _select_active_order(state.get("orders", []) or [])
        need = _remaining_need(active)
        if not bots:
            return []
        if not need:
            return [{"bot": b["id"], "action": "wait"} for b in bots]

        round_no = int(state.get("round", 0) or 0)
        if round_no - self._last_replan_round >= self.replan_every:
            self._replan(state, controller, bots, need)
            self._last_replan_round = round_no

        reservations = _build_reservations(self._intents, bots, controller, self.horizon)

        actions: List[Action] = []
        for bot in bots:
            bot_id = str(bot["id"])
            bot_pos = _to_pos(bot.get("position")) or (0, 0)
            inv = [str(x) for x in (bot.get("inventory", []) or [])]
            intent = self._intents.setdefault(bot_id, BotIntent())

            if bot_pos == controller.dropoff and any(need.get(t, 0) > 0 for t in inv):
                actions.append({"bot": bot["id"], "action": "drop_off"})
                continue

            pick = _pick_if_possible(bot, state.get("items", []) or [], intent.targets, need)
            if pick is not None:
                actions.append(pick)
                continue

            next_pos = reservations.get(bot_id, {}).get(1)
            if next_pos is None or next_pos == bot_pos:
                actions.append({"bot": bot["id"], "action": "wait"})
            else:
                actions.append({"bot": bot["id"], "action": _move_action(bot_pos, next_pos)})
        return actions

    def _replan(self, state: Dict[str, Any], controller, bots: List[dict], need: Counter) -> None:
        candidates = _build_candidates(state.get("items", []) or [], need, controller)

        def cost(bot: dict, cand: ItemCandidate) -> int:
            bot_pos = _to_pos(bot.get("position")) or (0, 0)
            stand = choose_best_stand(bot_pos, cand, lambda a, b: _distance(controller, a, b))
            return 10**6 if stand is None else (_distance(controller, bot_pos, stand) or 10**6)

        assigned = assign_items_to_bots(bots, candidates, need, cost)

        for bot in bots:
            bot_id = str(bot["id"])
            bot_pos = _to_pos(bot.get("position")) or (0, 0)
            inv = bot.get("inventory", []) or []
            intent = self._intents.setdefault(bot_id, BotIntent())

            if len(inv) >= 3:
                intent.mode = "DROPOFF"
                intent.targets = []
                continue

            items = assigned.get(bot_id, [])
            if not items:
                intent.mode = "IDLE"
                intent.targets = []
                continue

            trip = _best_bot_trip(bot_pos, items, controller)
            targets = [Target(c.item_id, c.item_type, c.shelf_pos, stand) for c, stand in trip]
            intent.mode = "PICK"
            intent.targets = targets


def _build_candidates(items: Sequence[dict], need: Counter, controller) -> List[ItemCandidate]:
    out: List[ItemCandidate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type", ""))
        if need.get(item_type, 0) <= 0:
            continue
        item_id = item.get("id")
        shelf = _to_pos(item.get("position"))
        if not isinstance(item_id, str) or shelf is None:
            continue
        stands = tuple(p for p in neighbors4(shelf) if controller.is_free_static(p))
        if stands:
            out.append(ItemCandidate(item_id=item_id, item_type=item_type, shelf_pos=shelf, stands=stands))
    return out


def _best_bot_trip(bot_pos: Pos, assigned_items: List[ItemCandidate], controller) -> List[Tuple[ItemCandidate, Pos]]:
    best: Optional[Tuple[int, List[Tuple[ItemCandidate, Pos]]]] = None
    max_items = min(2, len(assigned_items))
    shortlist = assigned_items[:max_items]
    for perm in permutations(shortlist, len(shortlist)):
        for stands in product(*[cand.stands for cand in perm]):
            total = 0
            cur = bot_pos
            valid = True
            for stand in stands:
                d = _distance(controller, cur, stand)
                if d is None:
                    valid = False
                    break
                total += d + 1
                cur = stand
            d_drop = _distance(controller, cur, controller.dropoff)
            if d_drop is None:
                valid = False
            else:
                total += d_drop + 1
            if not valid:
                continue
            plan = list(zip(perm, stands))
            if best is None or total < best[0]:
                best = (total, plan)
    return best[1] if best is not None else []


def _build_reservations(intents: Dict[str, BotIntent], bots: List[dict], controller, horizon: int) -> Dict[str, Dict[int, Pos]]:
    reservations: Dict[int, set[Pos]] = {t: set() for t in range(horizon + 1)}
    edge_res: Dict[int, set[Tuple[Pos, Pos]]] = {t: set() for t in range(1, horizon + 1)}
    out: Dict[str, Dict[int, Pos]] = {}

    priorities = sorted(
        bots,
        key=lambda b: (
            -len(b.get("inventory", []) or []),
            str(b.get("id")),
        ),
    )

    for bot in priorities:
        bot_id = str(bot["id"])
        pos = _to_pos(bot.get("position")) or (0, 0)
        intent = intents.get(bot_id, BotIntent())
        if intent.mode == "DROPOFF" or not intent.targets:
            goal = controller.dropoff
        else:
            goal = intent.targets[0].stand_pos

        path = _time_bfs(pos, goal, controller, reservations, edge_res, horizon)
        schedule: Dict[int, Pos] = {}
        for t, cell in enumerate(path[: horizon + 1]):
            schedule[t] = cell
            reservations[t].add(cell)
            if t > 0:
                edge_res[t].add((path[t - 1], cell))
        out[bot_id] = schedule
    return out


def _time_bfs(start: Pos, goal: Pos, controller, reservations, edge_res, horizon: int) -> List[Pos]:
    q = deque([(start, 0)])
    parent: Dict[Tuple[Pos, int], Tuple[Pos, int]] = {}
    seen = {(start, 0)}

    while q:
        pos, t = q.popleft()
        if pos == goal:
            return _reconstruct_time_path((pos, t), parent)
        if t >= horizon:
            continue
        for nxt in [pos, *neighbors4(pos)]:
            nt = t + 1
            if nxt != pos and not controller.is_free_static(nxt):
                continue
            if nxt in reservations.get(nt, set()):
                continue
            if (nxt, pos) in edge_res.get(nt, set()):
                continue
            node = (nxt, nt)
            if node in seen:
                continue
            seen.add(node)
            parent[node] = (pos, t)
            q.append(node)
    return [start]


def _reconstruct_time_path(node: Tuple[Pos, int], parent: Dict[Tuple[Pos, int], Tuple[Pos, int]]) -> List[Pos]:
    path = [node[0]]
    while node in parent:
        node = parent[node]
        path.append(node[0])
    path.reverse()
    return path


def _pick_if_possible(bot: dict, items: Sequence[dict], targets: Sequence[Target], need: Counter) -> Optional[Action]:
    if not targets:
        return None
    bot_pos = _to_pos(bot.get("position")) or (0, 0)
    inv = bot.get("inventory", []) or []
    if len(inv) >= 3:
        return None
    target = targets[0]
    for item in items:
        if item.get("id") != target.item_id:
            continue
        shelf = _to_pos(item.get("position"))
        if shelf and abs(bot_pos[0] - shelf[0]) + abs(bot_pos[1] - shelf[1]) == 1 and need.get(target.item_type, 0) > 0:
            return {"bot": bot.get("id"), "action": "pick_up", "item_id": target.item_id}
    return None


def _distance(controller, start: Pos, goal: Pos) -> Optional[int]:
    p = bfs_path(start, goal, width=controller.width, height=controller.height, walls=set(controller.walls), blocked=set())
    return None if not p else len(p) - 1


def _to_pos(obj: Any) -> Optional[Pos]:
    if isinstance(obj, dict):
        if "position" in obj:
            return _to_pos(obj.get("position"))
        if "x" in obj and "y" in obj:
            return int(obj["x"]), int(obj["y"])
    if isinstance(obj, (list, tuple)) and len(obj) >= 2:
        return int(obj[0]), int(obj[1])
    return None


def _move_action(a: Pos, b: Pos) -> str:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return {
        (1, 0): "move_right",
        (-1, 0): "move_left",
        (0, 1): "move_down",
        (0, -1): "move_up",
    }.get((dx, dy), "wait")


def _select_active_order(orders: Sequence[dict]) -> Optional[dict]:
    active = [o for o in orders if isinstance(o, dict) and o.get("status") == "active"]
    return active[0] if active else None


def _remaining_need(order: Optional[dict]) -> Counter:
    if not order:
        return Counter()
    req = Counter(str(x) for x in (order.get("items_required") or order.get("items") or []))
    delivered = Counter(str(x) for x in (order.get("items_delivered") or []))
    rem = req - delivered
    return Counter({k: v for k, v in rem.items() if v > 0})
