"""
Szállítási napló per felhasználó.
Fájl: {STORAGE_DIR}/journal_{chat_id}.json
Backup: {STORAGE_DIR}/journal_{chat_id}.json.bak

Adatbiztonság:
- Atomi írás: .tmp → os.replace() — szerver crash nem korruptálja a fájlt
- Auto backup: minden sikeres írás után .bak fájl is frissül
- Backup recovery: ha a fő fájl sérül, a .bak-ból töltjük be
"""
from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("convoy-journal")

_STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(Path(__file__).parent / "cache")))

if str(_STORAGE_DIR) != "/data":
    log.warning(
        "STORAGE_DIR is '%s' — journal data is NOT on the persistent volume! "
        "Set STORAGE_DIR=/data in Railway Variables to prevent data loss on redeploy.",
        _STORAGE_DIR,
    )

_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _path(chat_id: int) -> Path:
    return _STORAGE_DIR / f"journal_{chat_id}.json"


def _bak_path(chat_id: int) -> Path:
    return _STORAGE_DIR / f"journal_{chat_id}.json.bak"


def load(chat_id: int) -> list[dict]:
    """Betöltés főfájlból; ha sérült, a backup-ból állítja helyre."""
    main = _path(chat_id)
    bak  = _bak_path(chat_id)

    for path, label in ((main, "main"), (bak, "backup")):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("root is not a list")
            if label == "backup":
                log.warning("journal_%s: main file corrupt — recovered from .bak", chat_id)
                # Azonnal visszaírjuk a helyreállított adatot a fő fájlba
                _atomic_write(main, data)
            return data
        except Exception as exc:
            log.error("journal_%s: failed to parse %s (%s)", chat_id, label, exc)

    return []


def _atomic_write(path: Path, entries: list) -> None:
    """Atomi írás: .tmp → os.replace() — crash esetén sem korruptálódik a fájl."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _save(chat_id: int, entries: list[dict]) -> None:
    main = _path(chat_id)
    bak  = _bak_path(chat_id)

    # 1. Atomi írás a fő fájlba
    _atomic_write(main, entries)
    # 2. Backup frissítése (ha a fő írás sikerült)
    _atomic_write(bak, entries)


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
        km    = e.get("megtett_km", "-")
        notes = e.get("notes", "")
        line  = (
            f"*#{e['id']}* | {e.get('date', '?')}\n"
            f"🏢 {e.get('szallito', '-')}  🚛 {e.get('rendszam', '-')}\n"
            f"🛣 {e.get('route', '-')}"
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
