from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MOCK_BACKEND_DIR = Path(__file__).resolve().parents[1] / "data" / "mock_backend"


def load_mock_json(filename: str) -> dict[str, Any]:
    path = MOCK_BACKEND_DIR / filename
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
