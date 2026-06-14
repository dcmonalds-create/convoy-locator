"""
Szállítási napló per felhasználó.
Fájl: {STORAGE_DIR}/journal_{chat_id}.json
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

_CACHE_DIR = Path(os.getenv("STORAGE_DIR", str(Path(__file__).parent / "cache")))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _path(chat_id: int) -> Path:
    return _CACHE_DIR / f"journal_{chat_id}.json"


def load(chat_id: int) -> list[dict]:
    p = _path(chat_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(chat_id: int, entries: list[dict]) -> None:
    _path(chat_id).write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_entry(
    chat_id:    int,
    szallito:   str = "-",
    rendszam:   str = "-",
    sofor_neve: str = "-",
    kisert_rsz: str = "-",
    datum_ind:  str = "-",
    datum_erk:  str = "-",
    index_ind:  str = "-",
    index_erk:  str = "-",
    megtett_km: str = "-",
    route:      str = "-",
    gmaps_route: str = "",
    notes:      str = "",
) -> dict:
    entries = load(chat_id)
    entry = {
        "id":          (entries[-1]["id"] + 1) if entries else 1,
        "date":        datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "szallito":    szallito,
        "rendszam":    rendszam,
        "sofor_neve":  sofor_neve,
        "kisert_rsz":  kisert_rsz,
        "datum_ind":   datum_ind,
        "datum_erk":   datum_erk,
        "index_ind":   index_ind,
        "index_erk":   index_erk,
        "megtett_km":  megtett_km,
        "route":       route,
        "gmaps_route": gmaps_route,
        "notes":       notes,
    }
    entries.append(entry)
    _save(chat_id, entries)
    return entry


_ALLOWED_FIELDS = {
    "szallito", "rendszam", "sofor_neve", "kisert_rsz",
    "datum_ind", "datum_erk", "index_ind", "index_erk",
    "megtett_km", "route", "gmaps_route", "notes"
}


def update_entry(chat_id: int, entry_id: int, field: str, value: str) -> bool:
    if field not in _ALLOWED_FIELDS:
        return False
    entries = load(chat_id)
    for e in entries:
        if e["id"] == entry_id:
            e[field] = value
            _save(chat_id, entries)
            return True
    return False


def delete_entry(chat_id: int, entry_id: int) -> bool:
    entries = load(chat_id)
    new = [e for e in entries if e["id"] != entry_id]
    if len(new) == len(entries):
        return False
    _save(chat_id, new)
    return True


def get_entry(chat_id: int, entry_id: int) -> dict | None:
    for e in load(chat_id):
        if e["id"] == entry_id:
            return e
    return None


def last_entries(chat_id: int, n: int = 5) -> list[dict]:
    return load(chat_id)[-n:]


def monthly_report(chat_id: int, month: int, year: int) -> str:
    entries = [e for e in load(chat_id) if _in_month(e, month, year)]
    if not entries:
        return ""
    lines = []
    for e in entries:
        szallito = e.get("szallito", "-")
        rendszam = e.get("rendszam", "-")
        route    = e.get("route", "-")
        notes    = e.get("notes", "")
        km       = e.get("megtett_km", "-")
        line = (
            f"*#{e['id']}* | {e.get('date', '?')}\n"
            f"🏢 {szallito}  🚛 {rendszam}\n"
            f"🛣 {route}"
        )
        if km and km != "-":
            line += f"  🔢 {km} km"
        if notes and notes not in ("-", ""):
            line += f"\n📝 {notes}"
        lines.append(line)
    return "\n\n".join(lines)


def _in_month(entry: dict, month: int, year: int) -> bool:
    try:
        dt = datetime.datetime.strptime(entry.get("date", "")[:7], "%Y-%m")
        return dt.month == month and dt.year == year
    except Exception:
        return False
