from pathlib import Path
import json
from typing import Any, Dict, List, Optional, Set, Tuple

Pos = Tuple[int, int]

def save_json(json_file) -> str:
    out_path = Path.cwd() / "data.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(json_file, f, indent=2)        
    return

def build_walls_set(state: Dict[str, Any]) -> Set[Pos]:
    """Protocol -> internal representation."""
    return {(x, y) for x, y in state["grid"]["walls"]}


def get_bot_positions(state) -> Set[Pos]:
    return {(b["position"][0], b["position"][1]) for b in state["bots"]}

