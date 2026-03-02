# bot_controller.py
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Tuple

Action = Dict[str, Any]
State = Dict[str, Any]
Pos = Tuple[int, int]

Policy = Callable[[State, "BotController"], List[Action]]

_ALLOWED_ACTIONS = {
    "move_up",
    "move_down",
    "move_left",
    "move_right",
    "pick_up",
    "drop_off",
    "wait",
}
_MOVE_DELTAS: Dict[str, Tuple[int, int]] = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
}


class BotController:
    def __init__(self, policy: Optional[Policy] = None) -> None:
        self._policy: Optional[Policy] = policy

        # ---- Static (set once) ----
        self.initialized: bool = False
        self.width: int = 1
        self.height: int = 1
        self.walls: set[Pos] = set()
        self.dropoff: Pos = (0, 0)

        # ---- Dynamic (updated each round) ----
        self.round: int = 0
        self.max_rounds: int = 0
        self.bots: List[Dict[str, Any]] = []
        self.bots_by_id: Dict[str, Dict[str, Any]] = {}

    def set_policy(self, policy: Policy) -> None:
        self._policy = policy

    # ----------------------------
    # Initialization + state sync
    # ----------------------------

    def initialize(self, state: State) -> None:
        if self.initialized:
            return

        self.width, self.height = self._board_size(state)
        self.walls = self._extract_walls(state)
        self.dropoff = self._extract_dropoff(state)

        self.initialized = True

    def _sync_dynamic(self, state: State) -> None:
        self.round = int(state.get("round", 0) or 0)
        self.max_rounds = int(state.get("max_rounds", 0) or 0)

        bots = state.get("bots", [])
        self.bots = bots if isinstance(bots, list) else []

        self.bots_by_id = {}
        for bot in self.bots:
            if not isinstance(bot, dict):
                continue
            bot_id_raw = bot.get("id")
            self.bots_by_id[str(bot_id_raw)] = bot

    # ------------
    # Main entry
    # ------------

    def act(self, state: State) -> List[Action]:
        if not self.initialized:
            self.initialize(state)
        self._sync_dynamic(state)

        # If no policy -> wait for all bots
        if self._policy is None:
            return [{"bot": b.get("id"), "action": "wait"} for b in self.bots if isinstance(b, dict)]

        policy_input = deepcopy(state)
        raw_actions = self._policy(policy_input, self)
        
        # Keep first action per bot only (keyed by str(bot_id))
        by_bot: Dict[str, Action] = {}
        if isinstance(raw_actions, list):
            for a in raw_actions:
                if not isinstance(a, dict):
                    continue
                key = str(a.get("bot", ""))
                if key in self.bots_by_id and key not in by_bot:
                    by_bot[key] = a

        sanitized: List[Action] = []
        occupied_destinations: set[Pos] = set()

        for bot in self.bots:
            if not isinstance(bot, dict):
                continue

            bot_id_raw = bot.get("id")
            bot_key = str(bot_id_raw)

            candidate = by_bot.get(bot_key)
            action = self._sanitize_for_bot(candidate, bot, bot_id_raw)

            destination = self._destination(bot, action)

            # Same-destination conflict resolution
            if destination in occupied_destinations and action["action"] != "wait":
                action = {"bot": bot_id_raw, "action": "wait"}
                destination = self._destination(bot, action)

            occupied_destinations.add(destination)
            sanitized.append(action)

        return sanitized

    # ----------------------------
    # Sanitization + collision
    # ----------------------------

    def _sanitize_for_bot(self, action: Optional[Action], bot: Dict[str, Any], bot_id_raw: Any) -> Action:
        if not isinstance(action, dict):
            return {"bot": bot_id_raw, "action": "wait"}

        action_name = action.get("action")
        if action_name not in _ALLOWED_ACTIONS:
            return {"bot": bot_id_raw, "action": "wait"}

        if action_name == "pick_up":
            item_id = action.get("item_id")
            if not isinstance(item_id, str):
                return {"bot": bot_id_raw, "action": "wait"}
            return {"bot": bot_id_raw, "action": "pick_up", "item_id": item_id}

        if action_name == "drop_off":
            return {"bot": bot_id_raw, "action": "drop_off"}

        if action_name in _MOVE_DELTAS:
            x, y = self._position(bot)
            dx, dy = _MOVE_DELTAS[action_name]
            nx, ny = x + dx, y + dy

            if not self.in_bounds((nx, ny)):
                return {"bot": bot_id_raw, "action": "wait"}
            if not self.is_free_static((nx, ny)):
                return {"bot": bot_id_raw, "action": "wait"}

            return {"bot": bot_id_raw, "action": action_name}

        return {"bot": bot_id_raw, "action": "wait"}

    @staticmethod
    def _position(bot: Dict[str, Any]) -> Pos:
        """
        Accepts:
          - {"position": {"x":..,"y":..}}
          - {"position": [x,y]}
          - {"x":..,"y":..}  (rare)
          - [x,y] / (x,y)    (rare)
        """
        p = bot.get("position", bot)

        if isinstance(p, dict):
            if "position" in p:
                p = p["position"]
            if isinstance(p, dict):
                return int(p.get("x", 0) or 0), int(p.get("y", 0) or 0)

        if isinstance(p, (list, tuple)) and len(p) >= 2:
            return int(p[0]), int(p[1])

        return (0, 0)

    def _destination(self, bot: Dict[str, Any], action: Action) -> Pos:
        x, y = self._position(bot)
        move = action.get("action")
        if move in _MOVE_DELTAS:
            dx, dy = _MOVE_DELTAS[move]
            return x + dx, y + dy
        return x, y

    # ----------------------------
    # Board parsing helpers
    # ----------------------------

    @staticmethod
    def _board_dict(state: State) -> Dict[str, Any]:
        # Support both server shapes: state["grid"] and state["board"]
        b = state.get("board")
        if isinstance(b, dict):
            return b
        g = state.get("grid")
        if isinstance(g, dict):
            return g
        return {}

    @classmethod
    def _board_size(cls, state: State) -> Tuple[int, int]:
        board = cls._board_dict(state)
        width = int(board.get("width", 1) or 1)
        height = int(board.get("height", 1) or 1)
        return max(width, 1), max(height, 1)

    @staticmethod
    def _coerce_pos(obj: Any) -> Optional[Pos]:
        if isinstance(obj, dict):
            if "position" in obj:
                return BotController._coerce_pos(obj.get("position"))
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

    def _extract_walls(self, state: State) -> set[Pos]:
        board = self._board_dict(state)

        raw = board.get("walls")
        if raw is None:
            raw = state.get("walls", [])
        if raw is None:
            raw = []

        walls: set[Pos] = set()
        if isinstance(raw, list):
            for w in raw:
                p = self._coerce_pos(w)
                if p is not None:
                    walls.add(p)
        return walls

    def _extract_dropoff(self, state: State) -> Pos:
        board = self._board_dict(state)
        candidates = [
            state.get("dropoff"),
            state.get("drop_off"),
            state.get("dropOff"),
            board.get("dropoff"),
            board.get("drop_off"),
            board.get("dropOff"),
        ]
        for c in candidates:
            p = self._coerce_pos(c)
            if p is not None:
                return p
        return (0, 0)

    # ----------------------------
    # Helpers exposed to policies
    # ----------------------------

    def in_bounds(self, pos: Pos) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_free_static(self, pos: Pos) -> bool:
        return self.in_bounds(pos) and (pos not in self.walls)
    
    def build_item_positions_by_type(self, state):
        """
        Returns: { "cheese": [[3,2],[3,4]], "butter": [[5,2],[5,4]], ... }
        """
        out = {}
        for item in state.get("items", []):
            t = item.get("type")
            if t is None:
                continue
            out.setdefault(t, []).append(item.get("position"))
        return out

    def blocked_positions(self, state):
        """
        Returns a set of blocked (x,y) tuples for THIS ROUND.
        Includes:
          - static walls
          - all item positions (shelves)
          - all bot positions
        """
        blocked = set()

        # static walls (already parsed in initialize)
        blocked |= set(self.walls)

        # items
        for item in state.get("items", []):
            pos = item.get("position")
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                blocked.add((int(pos[0]), int(pos[1])))

        # bots (prefer controller-synced bots if available)
        bots = self.bots if self.bots else state.get("bots", [])
        for bot in bots:
            if not isinstance(bot, dict):
                continue
            x, y = self._position(bot)
            blocked.add((x, y))

        return blocked

    def allocate_items_for_bot(self, bot, active_items, preview_items):
        """
        Pick up to 3-len(inventory) items for ONE bot.

        Rules:
          1) Fill remaining inventory slots with available ACTIVE items first.
             (If more active items than slots, pick the ones closest to the bot by BFS.)
          2) If slots remain after taking all active items, take PREVIEW items that are
             closest to the dropoff by BFS (item-adjacent -> dropoff-adjacent).

        Returns: list of item dicts (0-3 items).
        """

        MAX_INV = 3
        inv = bot.get("inventory", []) or []
        slots = MAX_INV - len(inv)
        if slots <= 0:
            return []

        def neighbors4(p):
            x, y = p
            return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

        def as_pos(p):
            return (int(p[0]), int(p[1]))

        def shelf_pos(item):
            return as_pos(item.get("position", (0, 0)))

        # Treat shelves as blocked cells (you stand next to them)
        shelf_blocks = set()
        for it in (active_items or []):
            shelf_blocks.add(shelf_pos(it))
        for it in (preview_items or []):
            shelf_blocks.add(shelf_pos(it))

        obstacles = set(self.walls) | shelf_blocks

        def stand_cells_next_to(cell):
            out = []
            for n in neighbors4(cell):
                if self.in_bounds(n) and n not in obstacles:
                    out.append(n)
            return out

        def bfs_dist(start, goals):
            """BFS distance from start to ANY goal (goals is a set). Returns int or None."""
            if not goals:
                return None
            if start in goals:
                return 0

            from collections import deque
            q = deque([(start, 0)])
            seen = {start}

            while q:
                cur, d = q.popleft()
                for nxt in neighbors4(cur):
                    if nxt in seen:
                        continue
                    if not self.in_bounds(nxt):
                        continue
                    if nxt in obstacles:
                        continue
                    if nxt in goals:
                        return d + 1
                    seen.add(nxt)
                    q.append((nxt, d + 1))
            return None

        bot_xy = self._position(bot)

        chosen = []
        chosen_ids = set()

        # --- 1) ACTIVE first (pick closest to bot if too many) ---
        active_scored = []
        for it in (active_items or []):
            it_id = it.get("id")
            if it_id in chosen_ids:
                continue
            shelf = shelf_pos(it)
            goals = set(stand_cells_next_to(shelf))
            d = bfs_dist(bot_xy, goals)
            active_scored.append((10**9 if d is None else d, it))

        active_scored.sort(key=lambda x: x[0])

        for _, it in active_scored:
            if slots <= 0:
                break
            it_id = it.get("id")
            if it_id in chosen_ids:
                continue
            chosen.append(it)
            chosen_ids.add(it_id)
            slots -= 1

        # If we still have slots, that means we exhausted ACTIVE items (or none reachable)
        # --- 2) PREVIEW closest to dropoff ---
        if slots > 0:
            drop_goals = set(stand_cells_next_to(self.dropoff))

            preview_scored = []
            for it in (preview_items or []):
                it_id = it.get("id")
                if it_id in chosen_ids:
                    continue

                shelf = shelf_pos(it)
                starts = stand_cells_next_to(shelf)
                if not starts:
                    continue

                best = None
                for s in starts:
                    d = bfs_dist(s, drop_goals)
                    if d is None:
                        continue
                    if best is None or d < best:
                        best = d

                preview_scored.append((10**9 if best is None else best, it))

            preview_scored.sort(key=lambda x: x[0])

            for _, it in preview_scored:
                if slots <= 0:
                    break
                it_id = it.get("id")
                if it_id in chosen_ids:
                    continue
                chosen.append(it)
                chosen_ids.add(it_id)
                slots -= 1

        return chosen   

 