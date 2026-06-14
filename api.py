"""
ConvoyLocator — FastAPI production server.
Handles: Telegram webhook + REST API + Mini App static files.

Set in environment:
  TELEGRAM_BOT_TOKEN  — bot token
  GOOGLE_PLACES_API_KEY
  WEBHOOK_URL         — public Railway URL (e.g. https://app.railway.app)
                        When set, registers webhook automatically on startup.
  PORT                — port to listen on (Railway sets this automatically)
"""
from __future__ import annotations

import datetime
import io
import json
import logging
import os
import pathlib
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv("envi.env")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from telegram import MenuButtonWebApp, Update, WebAppInfo
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import journal as journal_mod
import places
from bot import (
    cmd_limba,
    cmd_m,
    cmd_start,
    on_category,
    on_fav_add_start,
    on_fav_del_confirm,
    on_fav_del_show,
    on_fav_menu,
    on_fav_select,
    on_fav_show_cats,
    on_journal_add,
    on_journal_del,
    on_journal_edit,
    on_journal_edit_field,
    on_journal_list,
    on_journal_menu,
    on_journal_report,
    on_lang_select,
    on_location,
    on_repeat,
    on_text,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("convoy-api")

# ── PTB Application ────────────────────────────────────────────────────────────

def _register_handlers(ptb: Application) -> None:
    ptb.add_handler(CommandHandler("start", cmd_start))
    ptb.add_handler(CommandHandler("limba", cmd_limba))
    ptb.add_handler(CommandHandler("m", cmd_m))
    ptb.add_handler(MessageHandler(filters.LOCATION, on_location))
    ptb.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    ptb.add_handler(CallbackQueryHandler(on_lang_select,       pattern="^lang_"))
    ptb.add_handler(CallbackQueryHandler(on_category,          pattern="^cat_"))
    ptb.add_handler(CallbackQueryHandler(on_repeat,            pattern="^repeat_cat$"))
    ptb.add_handler(CallbackQueryHandler(on_fav_menu,          pattern="^fav_menu$"))
    ptb.add_handler(CallbackQueryHandler(on_fav_add_start,     pattern="^fav_add$"))
    ptb.add_handler(CallbackQueryHandler(on_fav_del_show,      pattern="^fav_del$"))
    ptb.add_handler(CallbackQueryHandler(on_fav_select,        pattern="^fav_sel_"))
    ptb.add_handler(CallbackQueryHandler(on_fav_show_cats,     pattern="^fav_show_cats$"))
    ptb.add_handler(CallbackQueryHandler(on_fav_del_confirm,   pattern="^fav_delconfirm_"))
    ptb.add_handler(CallbackQueryHandler(on_journal_menu,      pattern="^jrn_menu$"))
    ptb.add_handler(CallbackQueryHandler(on_journal_add,       pattern="^jrn_add$"))
    ptb.add_handler(CallbackQueryHandler(on_journal_list,      pattern="^jrn_list$"))
    ptb.add_handler(CallbackQueryHandler(on_journal_report,    pattern="^jrn_report$"))
    ptb.add_handler(CallbackQueryHandler(on_journal_del,       pattern="^jrn_del$"))
    ptb.add_handler(CallbackQueryHandler(on_journal_edit,      pattern="^jrn_edit$"))
    ptb.add_handler(CallbackQueryHandler(on_journal_edit_field, pattern="^jrn_ef_"))


ptb_app: Application | None = None


def _check_storage() -> None:
    """Startup-on ellenőrzi, hogy a Postgres kapcsolat működik."""
    import psycopg2
    db_url = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
    if not db_url:
        log.critical("DATABASE_URL not set — journal data will NOT be persisted!")
        return
    try:
        conn = psycopg2.connect(db_url)
        conn.close()
        log.info("PostgreSQL connection OK — journal data is persistent")
    except Exception as exc:
        log.critical("PostgreSQL connection FAILED: %s", exc)


@asynccontextmanager
async def lifespan(fast_app: FastAPI):
    _check_storage()
    global ptb_app
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
        yield
        return

    ptb_app = Application.builder().token(token).build()
    _register_handlers(ptb_app)
    await ptb_app.initialize()
    await ptb_app.start()

    webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
    if webhook_url:
        await ptb_app.bot.set_webhook(url=f"{webhook_url}/webhook")
        log.info("Webhook registered: %s/webhook", webhook_url)
    else:
        log.warning("WEBHOOK_URL not set — only REST API active (no Telegram updates)")

    # Menü gomb (beviteli mező melletti "Open App") friss path-ra állítása minden
    # deploy-kor → iOS Telegram WebView kénytelen friss verziót letölteni.
    import time as _time
    webapp_url = os.getenv("WEBAPP_URL", "").rstrip("/")
    if webapp_url:
        try:
            await ptb_app.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="ConvoyLocator",
                    web_app=WebAppInfo(url=f"{webapp_url}/app/{int(_time.time())}"),
                )
            )
            log.info("Menu button set to fresh /app path")
        except Exception:
            log.exception("Failed to set chat menu button")

    yield

    await ptb_app.stop()
    await ptb_app.shutdown()


# ── FastAPI App ────────────────────────────────────────────────────────────────

app = FastAPI(title="ConvoyLocator", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_html(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in ("/", "/index.html") or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ── Telegram Webhook ──────────────────────────────────────────────────────────

@app.post("/webhook")
async def telegram_webhook(request: Request):
    if ptb_app is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return {"ok": True}


# ── REST API ──────────────────────────────────────────────────────────────────

class SearchReq(BaseModel):
    lat: float
    lng: float
    category: str
    lang: str = "hu"


class BestStopReq(BaseModel):
    lat: float
    lng: float
    lang: str = "hu"


@app.post("/api/search")
async def api_search(req: SearchReq):
    if req.category not in places.CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category: {req.category}")
    try:
        results = places.search(req.lat, req.lng, req.category, lang=req.lang)
        return {"results": results}
    except Exception as e:
        log.exception("Places search error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/best-stop")
async def api_best_stop(req: BestStopReq):
    try:
        clusters = places.search_best_stop(req.lat, req.lng, lang=req.lang)
        return {"clusters": clusters}
    except Exception as e:
        log.exception("Best stop error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/categories")
async def api_categories():
    return {
        key: {"emoji": val["emoji"], "label": val["label"]}
        for key, val in places.CATEGORIES.items()
    }


@app.get("/api/journal/{chat_id}")
async def api_journal_list(chat_id: int):
    return {"entries": journal_mod.load(chat_id)}


class JournalAddReq(BaseModel):
    szallito:    str = "-"
    rendszam:    str = "-"
    sofor_neve:  str = "-"
    kisert_rsz:  str = "-"
    datum_ind:   str = "-"
    datum_erk:   str = "-"
    index_ind:   str = "-"
    index_erk:   str = "-"
    megtett_km:  str = "-"
    route:       str = "-"
    gmaps_route: str = ""
    notes:       str = ""


@app.post("/api/journal/{chat_id}")
async def api_journal_add(chat_id: int, req: JournalAddReq):
    entry = journal_mod.add_entry(
        chat_id,
        szallito=req.szallito, rendszam=req.rendszam, sofor_neve=req.sofor_neve,
        kisert_rsz=req.kisert_rsz, datum_ind=req.datum_ind, datum_erk=req.datum_erk,
        index_ind=req.index_ind, index_erk=req.index_erk, megtett_km=req.megtett_km,
        route=req.route, gmaps_route=req.gmaps_route, notes=req.notes,
    )
    return {"entry": entry}


class JournalUpdateReq(BaseModel):
    field: str
    value: str


@app.put("/api/journal/{chat_id}/{entry_id}")
async def api_journal_update(chat_id: int, entry_id: int, req: JournalUpdateReq):
    allowed = {"szallito", "rendszam", "sofor_neve", "kisert_rsz", "datum_ind", "datum_erk", "index_ind", "index_erk", "megtett_km", "route", "gmaps_route", "notes"}
    if req.field not in allowed:
        raise HTTPException(status_code=400, detail=f"field must be one of {allowed}")
    ok = journal_mod.update_entry(chat_id, entry_id, req.field, req.value)
    if not ok:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"ok": True}


@app.delete("/api/journal/{chat_id}/{entry_id}")
async def api_journal_delete(chat_id: int, entry_id: int):
    ok = journal_mod.delete_entry(chat_id, entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"ok": True}


class JournalRestoreReq(BaseModel):
    entries: list


@app.post("/api/journal/{chat_id}/restore")
async def api_journal_restore(chat_id: int, req: JournalRestoreReq):
    """Visszaállítja a naplót egy JSON backup-ból. Meglévő adatot NEM törli —
    csak azokat a bejegyzéseket adja hozzá, amelyek ID-ja még nem létezik."""
    if not isinstance(req.entries, list):
        raise HTTPException(status_code=400, detail="entries must be a list")
    existing = journal_mod.load(chat_id)
    existing_ids = {e.get("id") for e in existing}
    added = 0
    for entry in req.entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") not in existing_ids:
            existing.append(entry)
            existing_ids.add(entry.get("id"))
            added += 1
    if added:
        journal_mod._save(chat_id, existing)
    return {"ok": True, "restored": added, "total": len(existing)}


class JournalExportReq(BaseModel):
    period:   str = "all"   # week | month | all
    month:    str = ""      # YYYY-MM, only used when period=month
    filename: str = ""


def _export_filter(entries: list, period: str, month: str) -> list:
    import datetime as _dt
    if period == "all":
        return entries
    now = _dt.date.today()
    if period == "week":
        # ISO hét: hétfőtől vasárnapig
        mon = now - _dt.timedelta(days=now.weekday())
        sun = mon + _dt.timedelta(days=6)
        def in_week(e):
            raw = e.get("datum_ind") or e.get("date", "")
            if not raw or raw == "-":
                return False
            try:
                d = _dt.date.fromisoformat(raw[:10])
                return mon <= d <= sun
            except Exception:
                return False
        return [e for e in entries if in_week(e)]
    if period == "month":
        pfx = month or now.strftime("%Y-%m")
        def in_month(e):
            raw = e.get("datum_ind") or e.get("date", "")
            return bool(raw and raw[:7] == pfx)
        return [e for e in entries if in_month(e)]
    return entries


def _build_csv(entries: list, period: str, month: str) -> str:
    cols = ["ID","Szállító","Rendszám","Sofőr neve","Kísért RSZ",
            "Indulás dátuma","Érkezés dátuma","Index km (ind.)","Index km (erk.)",
            "Megtett km","Útvonal","Google Maps útvonal","Megjegyzés"]

    def esc(v):
        return '"' + str(v or "").replace('"', '""') + '"'

    def parse_km(v):
        import re as _re
        m = _re.sub(r"[^\d]", "", str(v or ""))
        return int(m) if m else 0

    rows = []
    for e in entries:
        rows.append(",".join(esc(x) for x in [
            e.get("id",""), e.get("szallito",""), e.get("rendszam",""),
            e.get("sofor_neve",""), e.get("kisert_rsz",""),
            e.get("datum_ind",""), e.get("datum_erk",""),
            e.get("index_ind",""), e.get("index_erk",""),
            e.get("megtett_km",""), e.get("route",""),
            e.get("gmaps_route",""), e.get("notes",""),
        ]))

    total_km = sum(parse_km(e.get("megtett_km")) for e in entries)
    summary = ",".join(esc(x) for x in [
        "ÖSSZESÍTÉS", f"{len(entries)} fuvar", "", "", "", "", "", "", "",
        f"{total_km:,} km".replace(",", " ") if total_km else "-",
        "", "", "",
    ])

    label = {"week": "Ez a hét", "month": month, "all": "Összes"}.get(period, "")
    header_note = f"# {label} · {len(entries)} fuvar · {total_km} km\r\n"
    bom = "﻿"
    return bom + header_note + ",".join(f'"{c}"' for c in cols) + "\r\n" + "\r\n".join(rows) + "\r\n" + summary


@app.post("/api/journal/{chat_id}/export")
async def api_journal_export(chat_id: int, req: JournalExportReq):
    """Szűrt naplót CSV fájlként elküldi a felhasználó Telegram chatjébe."""
    if ptb_app is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    all_entries = journal_mod.load(chat_id)
    entries = _export_filter(all_entries, req.period, req.month)
    if not entries:
        raise HTTPException(status_code=404, detail="Nincs bejegyzés ebben az időszakban")

    csv_str = _build_csv(entries, req.period, req.month)
    bio = io.BytesIO(csv_str.encode("utf-8"))

    fname = req.filename or f"naplo_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    period_label = {"week": "Ez a hét", "month": req.month, "all": "Összes"}.get(req.period, "")

    import re as _re
    total_km = sum(
        int(_re.sub(r"[^\d]", "", str(e.get("megtett_km") or "")))
        for e in entries
        if _re.sub(r"[^\d]", "", str(e.get("megtett_km") or ""))
    )

    caption = (
        f"📊 Szállítási napló export\n"
        f"📅 {period_label} · {len(entries)} fuvar\n"
        f"🔢 Megtett km összesen: {total_km:,} km\n"
        f"📁 {fname}"
    ).replace(",", " ")
    try:
        await ptb_app.bot.send_document(
            chat_id=chat_id, document=bio, filename=fname, caption=caption
        )
    except Exception as e:
        log.exception("Journal export send failed")
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "count": len(entries), "total_km": total_km}


@app.post("/api/journal/{chat_id}/backup")
async def api_journal_backup(chat_id: int):
    """A teljes naplót JSON fájlként elküldi a felhasználó Telegram chatjébe.
    Off-site backup: a Telegram örökre megőrzi, függetlenül a Railway volume-tól."""
    if ptb_app is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    entries = journal_mod.load(chat_id)
    if not entries:
        raise HTTPException(status_code=404, detail="No entries to backup")

    data = json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8")
    bio = io.BytesIO(data)
    fname = f"naplo_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.json"
    caption = (
        f"💾 Szállítási napló biztonsági mentés\n"
        f"📋 {len(entries)} bejegyzés · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"⚠️ Ne töröld ezt az üzenetet — ebből vissza lehet állítani a naplót."
    )
    try:
        await ptb_app.bot.send_document(
            chat_id=chat_id, document=bio, filename=fname, caption=caption
        )
    except Exception as e:
        log.exception("Journal backup send failed")
        raise HTTPException(status_code=500, detail=f"Backup küldés sikertelen: {e}")
    return {"ok": True, "count": len(entries)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ConvoyLocator", "version": "2.0"}


# ── Mini App entry on a novel PATH — defeats iOS Telegram WebView cache ─────────
# Az iOS Telegram WKWebView a fájlt az ÚTVONAL alapján cache-eli, a query (?v=)
# nem mindig elég. A bot a /app/{cache_bust} path-ra mutat egyedi időbélyeggel,
# amit az eszköz SOHA nem látott → kénytelen frissen letölteni.

from fastapi.responses import HTMLResponse  # noqa: E402

_webapp_dir = pathlib.Path(__file__).parent / "webapp"

_NO_CACHE = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/app/{cache_bust}", response_class=HTMLResponse)
async def serve_app(cache_bust: str):
    """Mindig friss index.html bármilyen /app/<bélyeg> útvonalon."""
    html = (_webapp_dir / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html, headers=_NO_CACHE)


# ── Static Files — Mini App (must be LAST so API routes take priority) ─────────

if _webapp_dir.exists():
    app.mount("/", StaticFiles(directory=str(_webapp_dir), html=True), name="webapp")
