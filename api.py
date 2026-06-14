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
from telegram import Update
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


@asynccontextmanager
async def lifespan(fast_app: FastAPI):
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ConvoyLocator", "version": "2.0"}


# ── Static Files — Mini App (must be LAST so API routes take priority) ─────────

_webapp_dir = pathlib.Path(__file__).parent / "webapp"
if _webapp_dir.exists():
    app.mount("/", StaticFiles(directory=str(_webapp_dir), html=True), name="webapp")
