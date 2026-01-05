import json
from pathlib import Path
from typing import Any, Dict


def load_config(path: str = "config.json") -> Dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text())
