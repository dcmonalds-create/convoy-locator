"""
Stocare locatii favorite per utilizator.
Fisier: cache/favorites_{chat_id}.json
Format: {"Acasa": {"lat": 47.01, "lng": 21.93}, ...}
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_CACHE_DIR = Path(os.getenv("STORAGE_DIR", str(Path(__file__).parent / "cache")))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_MAX = 10  # maxim favorite per utilizator


def _path(chat_id: int) -> Path:
    return _CACHE_DIR / f"favorites_{chat_id}.json"


def load(chat_id: int) -> dict[str, dict]:
    p = _path(chat_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_location(chat_id: int, name: str, lat: float, lng: float) -> bool:
    """Salveaza un favorit. Returneaza False daca s-a atins limita."""
    favs = load(chat_id)
    if name not in favs and len(favs) >= _MAX:
        return False
    favs[name] = {"lat": lat, "lng": lng}
    _path(chat_id).write_text(json.dumps(favs, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def delete(chat_id: int, name: str) -> bool:
    """Sterge un favorit. Returneaza False daca nu exista."""
    favs = load(chat_id)
    if name not in favs:
        return False
    del favs[name]
    _path(chat_id).write_text(json.dumps(favs, ensure_ascii=False, indent=2), encoding="utf-8")
    return True
