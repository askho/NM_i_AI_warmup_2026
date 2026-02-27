from pathlib import Path
import json

def save_json(json_file) -> str:
    out_path = Path.cwd() / "data.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(json_file, f, indent=2)        
    return