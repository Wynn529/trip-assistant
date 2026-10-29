"""Save demo trips locally without credentials or personal identifiers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from travel_agent.contracts import AgentResponse


STORE = Path(__file__).resolve().parents[2] / "local_data"


def save_trip(response: AgentResponse) -> Path:
    STORE.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}.json"
    target = STORE / filename
    target.write_text(json.dumps(response.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def list_trips() -> list[Path]:
    if not STORE.exists():
        return []
    return sorted(STORE.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def load_trip(path: Path) -> dict:
    resolved = path.resolve()
    if resolved.parent != STORE.resolve() or resolved.suffix != ".json":
        raise ValueError("Invalid trip file")
    return json.loads(resolved.read_text(encoding="utf-8"))
