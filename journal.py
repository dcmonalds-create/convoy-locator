"""
Szállítási napló — PostgreSQL backend.
Adatok a Railway Postgres service-ben (postgres-volume) tárolódnak,
soha nem törlődnek deploy-kor.
"""
from __future__ import annotations

import datetime
import logging
import os

import psycopg2

log = logging.getLogger("convoy-journal")

_DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)

if not _DATABASE_URL:
    log.error("DATABASE_URL not set — journal will not work!")


def _conn():
    return psycopg2.connect(_DATABASE_URL)


def _init_db() -> None:
    conn = _conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS journal_entries (
                        chat_id     BIGINT  NOT NULL,
                        entry_id    INTEGER NOT NULL,
                        date        TEXT    NOT NULL DEFAULT '',
                        szallito    TEXT    NOT NULL DEFAULT '-',
                        rendszam    TEXT    NOT NULL DEFAULT '-',
                        sofor_neve  TEXT    NOT NULL DEFAULT '-',
                        kisert_rsz  TEXT    NOT NULL DEFAULT '-',
                        datum_ind   TEXT    NOT NULL DEFAULT '-',
                        datum_erk   TEXT    NOT NULL DEFAULT '-',
                        index_ind   TEXT    NOT NULL DEFAULT '-',
                        index_erk   TEXT    NOT NULL DEFAULT '-',
                        megtett_km  TEXT    NOT NULL DEFAULT '-',
                        route       TEXT    NOT NULL DEFAULT '-',
                        gmaps_route TEXT    NOT NULL DEFAULT '',
                        notes       TEXT    NOT NULL DEFAULT '',
                        PRIMARY KEY (chat_id, entry_id)
                    )
                """)
        log.info("journal DB table ready")
    except Exception as exc:
        log.error("Failed to init journal DB table: %s", exc)
    finally:
        conn.close()


try:
    _init_db()
except Exception as _e:
    log.error("journal DB init error: %s", _e)


_ALLOWED_FIELDS = {
    "szallito", "rendszam", "sofor_neve", "kisert_rsz",
    "datum_ind", "datum_erk", "index_ind", "index_erk",
    "megtett_km", "route", "gmaps_route", "notes",
}

_SELECT_COLS = """
    entry_id, date, szallito, rendszam, sofor_neve, kisert_rsz,
    datum_ind, datum_erk, index_ind, index_erk, megtett_km,
    route, gmaps_route, notes
"""


def _row_to_dict(row: tuple) -> dict:
    return {
        "id":          row[0],
        "date":        row[1],
        "szallito":    row[2],
        "rendszam":    row[3],
        "sofor_neve":  row[4],
        "kisert_rsz":  row[5],
        "datum_ind":   row[6],
        "datum_erk":   row[7],
        "index_ind":   row[8],
        "index_erk":   row[9],
        "megtett_km":  row[10],
        "route":       row[11],
        "gmaps_route": row[12],
        "notes":       row[13],
    }


def load(chat_id: int) -> list[dict]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM journal_entries "
                "WHERE chat_id = %s ORDER BY entry_id",
                (chat_id,),
            )
            return [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _save(chat_id: int, entries: list[dict]) -> None:
    """Felülírja a chat napló teljes tartalmát (bulk restore / delete ops)."""
    conn = _conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM journal_entries WHERE chat_id = %s", (chat_id,)
                )
                for e in entries:
                    cur.execute(
                        """
                        INSERT INTO journal_entries
                          (chat_id, entry_id, date, szallito, rendszam, sofor_neve, kisert_rsz,
                           datum_ind, datum_erk, index_ind, index_erk, megtett_km,
                           route, gmaps_route, notes)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            chat_id,
                            e.get("id", 0),
                            e.get("date", ""),
                            e.get("szallito", "-"),
                            e.get("rendszam", "-"),
                            e.get("sofor_neve", "-"),
                            e.get("kisert_rsz", "-"),
                            e.get("datum_ind", "-"),
                            e.get("datum_erk", "-"),
                            e.get("index_ind", "-"),
                            e.get("index_erk", "-"),
                            e.get("megtett_km", "-"),
                            e.get("route", "-"),
                            e.get("gmaps_route", ""),
                            e.get("notes", ""),
                        ),
                    )
    finally:
        conn.close()


def add_entry(
    chat_id:     int,
    szallito:    str = "-",
    rendszam:    str = "-",
    sofor_neve:  str = "-",
    kisert_rsz:  str = "-",
    datum_ind:   str = "-",
    datum_erk:   str = "-",
    index_ind:   str = "-",
    index_erk:   str = "-",
    megtett_km:  str = "-",
    route:       str = "-",
    gmaps_route: str = "",
    notes:       str = "",
) -> dict:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = _conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(MAX(entry_id), 0) + 1 "
                    "FROM journal_entries WHERE chat_id = %s",
                    (chat_id,),
                )
                next_id: int = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO journal_entries
                      (chat_id, entry_id, date, szallito, rendszam, sofor_neve, kisert_rsz,
                       datum_ind, datum_erk, index_ind, index_erk, megtett_km,
                       route, gmaps_route, notes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        chat_id, next_id, now,
                        szallito, rendszam, sofor_neve, kisert_rsz,
                        datum_ind, datum_erk, index_ind, index_erk,
                        megtett_km, route, gmaps_route, notes,
                    ),
                )
    finally:
        conn.close()
    return {
        "id": next_id, "date": now,
        "szallito": szallito, "rendszam": rendszam, "sofor_neve": sofor_neve,
        "kisert_rsz": kisert_rsz, "datum_ind": datum_ind, "datum_erk": datum_erk,
        "index_ind": index_ind, "index_erk": index_erk, "megtett_km": megtett_km,
        "route": route, "gmaps_route": gmaps_route, "notes": notes,
    }


def update_entry(chat_id: int, entry_id: int, field: str, value: str) -> bool:
    if field not in _ALLOWED_FIELDS:
        return False
    conn = _conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE journal_entries SET {field} = %s "
                    "WHERE chat_id = %s AND entry_id = %s",
                    (value, chat_id, entry_id),
                )
                return cur.rowcount > 0
    finally:
        conn.close()


def delete_entry(chat_id: int, entry_id: int) -> bool:
    conn = _conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM journal_entries WHERE chat_id = %s AND entry_id = %s",
                    (chat_id, entry_id),
                )
                return cur.rowcount > 0
    finally:
        conn.close()


def get_entry(chat_id: int, entry_id: int) -> dict | None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM journal_entries "
                "WHERE chat_id = %s AND entry_id = %s",
                (chat_id, entry_id),
            )
            row = cur.fetchone()
            return _row_to_dict(row) if row else None
    finally:
        conn.close()


def last_entries(chat_id: int, n: int = 5) -> list[dict]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM journal_entries "
                "WHERE chat_id = %s ORDER BY entry_id DESC LIMIT %s",
                (chat_id, n),
            )
            return list(reversed([_row_to_dict(r) for r in cur.fetchall()]))
    finally:
        conn.close()


def monthly_report(chat_id: int, month: int, year: int) -> str:
    prefix = f"{year}-{month:02d}"
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM journal_entries "
                "WHERE chat_id = %s AND date LIKE %s ORDER BY entry_id",
                (chat_id, f"{prefix}%"),
            )
            entries = [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

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
