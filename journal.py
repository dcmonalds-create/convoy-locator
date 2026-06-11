"""
Jurnal digital transporturi per utilizator.
Fisier: cache/journal_{chat_id}.json
Format: lista de intrari ordonate dupa data.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_CACHE_DIR = Path(__file__).parent / "cache"
_CACHE_DIR.mkdir(exist_ok=True)


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
    chat_id: int,
    route: str,
    ast: str,
    km: str,
    dims: str,
    notes: str,
) -> dict:
    entries = load(chat_id)
    entry = {
        "id": (entries[-1]["id"] + 1) if entries else 1,
        "date": datetime.now(timezone.utc).strftime("%d.%m.%Y"),
        "route": route,
        "ast": ast,
        "km": km,
        "dims": dims,
        "notes": notes,
    }
    entries.append(entry)
    _save(chat_id, entries)
    return entry


def update_entry(chat_id: int, entry_id: int, field: str, value: str) -> bool:
    """Frissít egy mezőt egy bejegyzésben. field: route/ast/km/dims/notes"""
    entries = load(chat_id)
    for e in entries:
        if e["id"] == entry_id:
            e[field] = value
            _save(chat_id, entries)
            return True
    return False


def get_entry(chat_id: int, entry_id: int) -> dict | None:
    for e in load(chat_id):
        if e["id"] == entry_id:
            return e
    return None


def delete_entry(chat_id: int, entry_id: int) -> bool:
    entries = load(chat_id)
    new = [e for e in entries if e["id"] != entry_id]
    if len(new) == len(entries):
        return False
    _save(chat_id, new)
    return True


def last_entries(chat_id: int, n: int = 5) -> list[dict]:
    return load(chat_id)[-n:]


def monthly_report(chat_id: int, month: int, year: int) -> str:
    """Genereaza raport text pentru luna/anul dat."""
    entries = [
        e for e in load(chat_id)
        if e["date"].endswith(f"{month:02d}.{year}")
    ]
    if not entries:
        return None

    lines = [f"📋 Raport {month:02d}.{year} — {len(entries)} transport(uri)\n"]
    lines.append("─" * 32)
    for e in entries:
        km_line = f"🔢 {e['km']} km\n" if e.get('km') and e['km'] != "-" else ""
        lines.append(
            f"\n#{e['id']} | {e['date']}\n"
            f"🛣  {e['route']}\n"
            f"📄 AST: {e['ast']}\n"
            f"{km_line}"
            f"📐 {e['dims']}\n"
            + (f"📝 {e['notes']}\n" if e['notes'] else "")
        )
        lines.append("─" * 32)
    return "\n".join(lines)
