from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from planning.assignments import ItemCandidate, assign_items_to_bots, choose_best_stand
from planning.pathfinding import bfs_path, neighbors4

Pos = Tuple[int, int]
Action = Dict[str, Any]


@dataclass
class BotIntent:
    mode: str = "IDLE"  # IDLE | PICK | DROPOFF
    item_id: Optional[str] = None
    item_type: Optional[str] = None
    shelf_pos: Optional[Pos] = None
    stand_pos: Optional[Pos] = None
    path: List[Pos] = field(default_factory=list)


class OptimizedMultiBotPolicy:
    """Robust multi-bot policy focused on throughput and low-stall behavior.

    Strategy per round:
      1) Bots carrying active-order items prioritize dropoff.
      2) Remaining bots get globally assigned nearest needed items.
      3) Movement is planned with short BFS and one-step reservation to reduce clashes.
    """

    def __init__(self, horizon: int = 8, replan_every: int = 1) -> None:
        self.horizon = horizon
        self.replan_every = max(1, replan_every)
        self._last_replan_round = -1
        self._intents: Dict[str, BotIntent] = {}

    def __call__(self, state: Dict[str, Any], controller) -> List[Action]:
        if state.get("type") != "game_state":
            return []

        bots = [b for b in state.get("bots", []) if isinstance(b, dict) and "id" in b]
        if not bots:
            return []

        active = _select_active_order(state.get("orders", []) or [])
        need = _remaining_need(active)
        if not need:
            return [{"bot": b["id"], "action": "wait"} for b in bots]

        round_no = int(state.get("round", 0) or 0)
        if round_no - self._last_replan_round >= self.replan_every:
            self._replan(state, controller, bots, need)
            self._last_replan_round = round_no

        actions: List[Action] = []
        reserved_next: Set[Pos] = set()

        for bot in bots:
            bot_id = str(bot["id"])
            bot_pos = _to_pos(bot.get("position")) or (0, 0)
            inv = [str(x) for x in (bot.get("inventory", []) or [])]
            intent = self._intents.setdefault(bot_id, BotIntent())

            if bot_pos == controller.dropoff and any(need.get(t, 0) > 0 for t in inv):
                actions.append({"bot": bot["id"], "action": "drop_off"})
                continue

            pick = _pick_if_possible(bot, state.get("items", []) or [], intent, need)
            if pick is not None:
                actions.append(pick)
                continue

            goal = _intent_goal(intent, controller.dropoff)
            blocked_now = {
                _to_pos(other.get("position")) or (0, 0)
                for other in bots
                if str(other.get("id")) != bot_id
            }
            path = bfs_path(
                bot_pos,
                goal,
                width=controller.width,
                height=controller.height,
                walls=set(controller.walls),
                blocked=blocked_now,
            )
            step = path[1] if path and len(path) > 1 else bot_pos

            if step == bot_pos or step in reserved_next:
                actions.append({"bot": bot["id"], "action": "wait"})
                reserved_next.add(bot_pos)
            else:
                actions.append({"bot": bot["id"], "action": _move_action(bot_pos, step)})
                reserved_next.add(step)

        return actions

    def _replan(self, state: Dict[str, Any], controller, bots: List[dict], need: Counter) -> None:
        items = state.get("items", []) or []

        carry_need = _carry_contribution_to_active_need(need, bots)
        pick_need = need - carry_need
        pick_need = Counter({k: v for k, v in pick_need.items() if v > 0})

        candidates = _build_candidates(items, pick_need, controller)

        def cost(bot: dict, cand: ItemCandidate) -> int:
            bot_pos = _to_pos(bot.get("position")) or (0, 0)
            stand = choose_best_stand(bot_pos, cand, lambda a, b: _distance(controller, a, b))
            if stand is None:
                return 10**6
            dist = _distance(controller, bot_pos, stand)
            return 10**6 if dist is None else dist

        assigned = assign_items_to_bots(bots, candidates, pick_need, cost)

        for bot in bots:
            bot_id = str(bot["id"])
            bot_pos = _to_pos(bot.get("position")) or (0, 0)
            inv = [str(x) for x in (bot.get("inventory", []) or [])]

            if any(need.get(t, 0) > 0 for t in inv) or len(inv) >= 3:
                self._intents[bot_id] = BotIntent(mode="DROPOFF")
                continue

            my_items = assigned.get(bot_id, [])
            if not my_items:
                self._intents[bot_id] = BotIntent(mode="IDLE")
                continue

            chosen = my_items[0]
            stand = choose_best_stand(bot_pos, chosen, lambda a, b: _distance(controller, a, b))
            if stand is None:
                self._intents[bot_id] = BotIntent(mode="IDLE")
                continue

            self._intents[bot_id] = BotIntent(
                mode="PICK",
                item_id=chosen.item_id,
                item_type=chosen.item_type,
                shelf_pos=chosen.shelf_pos,
                stand_pos=stand,
            )


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


def _carry_contribution_to_active_need(need: Counter, bots: Sequence[dict]) -> Counter:
    carried = Counter()
    remaining = Counter(need)
    for bot in bots:
        if not isinstance(bot, dict):
            continue
        for inv_item in (bot.get("inventory", []) or []):
            t = str(inv_item)
            if remaining.get(t, 0) > 0:
                remaining[t] -= 1
                carried[t] += 1
    return carried


def _pick_if_possible(bot: dict, items: Sequence[dict], intent: BotIntent, need: Counter) -> Optional[Action]:
    if intent.mode != "PICK" or not intent.item_id or not intent.item_type:
        return None
    bot_pos = _to_pos(bot.get("position")) or (0, 0)
    inv = bot.get("inventory", []) or []
    if len(inv) >= 3:
        return None

    for item in items:
        if item.get("id") != intent.item_id:
            continue
        shelf = _to_pos(item.get("position"))
        if shelf and abs(bot_pos[0] - shelf[0]) + abs(bot_pos[1] - shelf[1]) == 1 and need.get(intent.item_type, 0) > 0:
            return {"bot": bot.get("id"), "action": "pick_up", "item_id": intent.item_id}
    return None


def _intent_goal(intent: BotIntent, dropoff: Pos) -> Pos:
    if intent.mode == "DROPOFF":
        return dropoff
    if intent.mode == "PICK" and intent.stand_pos is not None:
        return intent.stand_pos
    return dropoff


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
