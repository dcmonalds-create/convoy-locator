"""
ConvoyLocator — bot Telegram pentru soferi/insotitori de transport agabaritic.

Flux principal:
  1. /start → selectie limba
  2. Trimite locatie (GPS sau manual) → butoane categorii
  3. Tap categorie → top 5 locatii cu link Google Maps

Favorite:
  - Buton "⭐ Favorite" in tastatura → meniu inline
  - Selecteaza un favorit → seteaza locatia direct
  - Adauga: nume → locatie (GPS sau text)
  - Sterge: tap pe favorit → confirmare
"""
from __future__ import annotations

import logging
import os
import re

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv("envi.env")

import favorites
import journal
import location_parser
import places

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("convoy-locator")

DEFAULT_LANG = "hu"

# ── Texte UI per limba ────────────────────────────────────────────────────────

STRINGS = {
    "hu": {
        "welcome": (
            "👋 *ConvoyLocator*\n\n"
            "Küldd el a helyzeted és megtalálom, ami kell 20 km-es körzetben.\n\n"
            "📍 GPS gomb — pontos helyzet\n"
            "📌 Kézi — koordináta vagy Google Maps link\n"
            "⭐ Kedvencek — mentett helyszínek"
        ),
        "location_btn":    "📍 Helyzet küldése",
        "manual_btn":      "📌 Helyszín beírása",
        "fav_btn":         "⭐ Kedvencek",
        "best_stop_btn":   "🛑 Best Stop",
        "checklist_btn":   "✅ Checklist",
        "checklist_text":  (
            "✅ *KISÉRÉSI ELLENŐRZŐLISTA*\n\n"
            "🏠 *Indulás előtt — Otthon:*\n"
            "1\\. 📄 Engedély elolvasása — utasítások, megszorítások\n"
            "2\\. 🗺 Útvonal elkészítése\n"
            "3\\. 📝 Ordin de Deplasare kitöltése\n"
            "4\\. 📋 Kísérőlevél kitöltése\n"
            "5\\. ⏱ Menetidő: Bors → találkozási pont ellenőrzése\n\n"
            "🚛 *Indulás előtt — Kamiontól:*\n"
            "6\\. 🔦 Kamion átnézés: villogók, rakomány lekötése, méretek\n"
            "7\\. 📱 Elkészített útvonal beállítása GPS\\-en\n"
            "8\\. 💧 500 ml kis palack — jelen van?\n\n"
            "─────────────────\n"
            "📝 *Írd le az útvonal fontos megjegyzéseit:*\n"
            "_\\(hidak, tiltott szakaszok, különleges utasítások…\\)_"
        ),
        "checklist_notes_ok": "📋 Megjegyzések rögzítve:\n\n_{notes}_",
        "manual_prompt":   "📌 Illeszd be a koordinátákat vagy a Google Maps linket:\n\nPélda: `47.0785, 21.9189`\nvagy: `https://maps.app.goo.gl/xxxxx`",
        "location_ok":     "📍 Helyzet megkapva! Mit keresel 20 km-es körzetben?",
        "manual_ok":       "📌 Helyszín beállítva! Mit keresel 20 km-es körzetben?",
        "manual_fail":     "❌ Nem sikerült beolvasni a helyszínt.\nPróbáld koordinátával: `47.0785, 21.9189`",
        "no_location":     "📍 Először küldd el a helyzeted az alsó gombbal.",
        "no_results":      "Nincs találat 20 km-en belül.\nPróbálj más kategóriát vagy frissítsd a helyzeted.",
        "nearest":         "— legközelebbi:",
        "open_maps":       "Megnyitás Google Maps-ben",
        "search_error":    "Keresési hiba: ",
        "ff_brands":       "🏆 Láncok (McD · KFC · BK):",
        "ff_others":       "🍔 Egyéb gyorséttermek:",
        "lang_changed":    "✅ Nyelv: Magyar",
        "lang_select":     "Válassz nyelvet / Alege limba / Select language:",
        "fav_title":       "⭐ *Kedvenc helyszínek*",
        "fav_empty":       "Még nincsenek mentett helyszínek.\nNyomd meg ➕ hogy adj hozzá egyet.",
        "fav_add_btn":     "➕ Új kedvenc",
        "fav_del_btn":     "🗑 Törlés",
        "fav_back_btn":    "← Vissza",
        "fav_ask_name":    "📝 Adj nevet a helyszínnek:\n_(pl. Otthon, Cég, Nádlac határ)_",
        "fav_ask_loc":     "📍 Most küldd el a helyszín helyzetét\n(GPS gomb vagy koordináta/link):",
        "fav_saved":       "✅ Kedvenc mentve: *{name}*",
        "fav_limit":       "❌ Maximum 10 kedvenc menthető. Törölj egyet először.",
        "fav_deleted":     "🗑 Törölve: *{name}*",
        "fav_set":         "📍 *{name}*",
        "fav_nav_btn":     "🧭 Navigálás — Google Maps",
        "fav_search_btn":  "🔍 Keresés 20 km-en belül",
        "fav_del_prompt":  "🗑 Melyik kedvencet törlöd?",
        "journal_btn":        "📋 Szállítási napló",
        "journal_menu_title": "📋 *Szállítási napló*",
        "journal_add_btn":    "➕ Új szállítás",
        "journal_list_btn":   "📄 Utolsó 5 bejegyzés",
        "journal_report_btn": "📊 Havi jelentés",
        "journal_ask_route":  "🛣 Útvonal (honnan → hova):",
        "journal_ask_ast":    "📄 AST szám (vagy - ha nincs):",
        "journal_ask_km":     "🔢 Megtett kilométerek (az AST-ból, pl. 748):",
        "journal_ask_dims":   "📐 Méretek és tömeg (pl. 28x2.8x4.3m, 110t):",
        "journal_ask_notes":  "📝 Megjegyzések (vagy - ha nincs):",
        "journal_saved":      "✅ Mentve! #{id} | {date}\n🛣 {route}",
        "journal_empty":      "Még nincsenek bejegyzések.",
        "journal_ask_month":  "📊 Melyik hónap? Írj: `HH.ÉÉÉÉ` (pl. `04.2026`)",
        "journal_no_data":    "Nincs adat erre a hónapra.",
        "journal_del_btn":    "🗑 Törlés",
        "journal_del_prompt": "Melyik bejegyzést törlöd? (írj #számot, pl. `#3`)",
        "journal_del_ok":     "🗑 Törölve: #{id}",
        "journal_del_fail":   "❌ Nem található: #{id}",
        "journal_edit_btn":   "✏️ Szerkesztés",
        "journal_edit_prompt":"Melyik bejegyzést szerkeszted? (írj #számot, pl. `#3`)",
        "journal_edit_show":  "✏️ *#{id}* | {date}\n🛣 {route}\n📄 {ast}\n🔢 {km} km\n📐 {dims}\n📝 {notes}\n\nMelyik mezőt módosítod?",
        "journal_edit_fail":  "❌ Nem található: #{id}",
        "journal_edit_ask":   "✏️ Új érték ({field}):",
        "journal_edit_ok":    "✅ Frissítve: #{id}",
        "journal_field_route":"🛣 Útvonal",
        "journal_field_ast":  "📄 AST szám",
        "journal_field_km":   "🔢 Km",
        "journal_field_dims": "📐 Méretek",
        "journal_field_notes":"📝 Megjegyzés",
        "categories": {
            "fastfood":    "🍔 Gyorsétterem",
            "mancare":     "🍽 Étel",
            "wc":          "🚻 WC",
            "combustibil": "⛽ Üzemanyag",
            "parcare_tir": "🅿️ TIR Parkoló",
            "service":     "🔧 Szerviz",
            "hotel":       "🛏 Szállás",
            "mol":         "🔴 MOL",
            "supermarket": "🛒 Szupermarket",
            "spital":      "🏥 Kórház",
            "vulcanizare": "🔩 Gumiszerelő",
            "atm":         "💶 ATM / Bank",
            "cafenea":     "☕ Kávézó",
            "pekseg":      "🥐 Pékség",
        },
    },
    "ro": {
        "welcome": (
            "👋 *ConvoyLocator*\n\n"
            "Trimite-mi locatia ta si iti gasesc ce ai nevoie in 20 km.\n\n"
            "📍 Buton GPS — locatie curenta\n"
            "📌 Manual — coordonate sau link Google Maps\n"
            "⭐ Favorite — locatii salvate"
        ),
        "location_btn":    "📍 Trimite locatia mea",
        "manual_btn":      "📌 Introduc locatia manual",
        "fav_btn":         "⭐ Favorite",
        "best_stop_btn":   "🛑 Best Stop",
        "checklist_btn":   "✅ Checklist",
        "checklist_text":  (
            "✅ *LISTĂ DE VERIFICARE ESCORTĂ*\n\n"
            "🏠 *Înainte de plecare — Acasă:*\n"
            "1\\. 📄 Citește permisul — instrucțiuni, restricții\n"
            "2\\. 🗺 Pregătire traseu\n"
            "3\\. 📝 Completează Ordinul de Deplasare\n"
            "4\\. 📋 Completează scrisoarea de escortă\n"
            "5\\. ⏱ Timp de drum: Bors → punct de întâlnire\n\n"
            "🚛 *Înainte de plecare — La camion:*\n"
            "6\\. 🔦 Inspecție camion: girofar, ancorare, dimensiuni\n"
            "7\\. 📱 Setează traseul pregătit pe GPS\n"
            "8\\. 💧 Sticlă 500 ml — este prezentă?\n\n"
            "─────────────────\n"
            "📝 *Notează observațiile importante despre traseu:*\n"
            "_\\(poduri, sectoare interzise, instrucțiuni speciale…\\)_"
        ),
        "checklist_notes_ok": "📋 Notițe salvate:\n\n_{notes}_",
        "manual_prompt":   "📌 Lipeste coordonatele sau linkul Google Maps:\n\nExemplu: `47.0785, 21.9189`\nsau: `https://maps.app.goo.gl/xxxxx`",
        "location_ok":     "📍 Locatie primita! Ce cauti in jur de 20 km?",
        "manual_ok":       "📌 Locatie setata! Ce cauti in jur de 20 km?",
        "manual_fail":     "❌ Nu am putut citi locatia.\nIncearca cu coordonate: `47.0785, 21.9189`",
        "no_location":     "📍 Trimite mai intai locatia ta folosind butonul de jos.",
        "no_results":      "Nu am gasit nimic in 20 km.\nIncearca alta categorie sau actualizeaza locatia.",
        "nearest":         "— cele mai apropiate:",
        "open_maps":       "Deschide in Google Maps",
        "search_error":    "Eroare la cautare: ",
        "ff_brands":       "🏆 Lanțuri (McD · KFC · BK):",
        "ff_others":       "🍔 Alte fast food-uri:",
        "lang_changed":    "✅ Limbă: Română",
        "lang_select":     "Válassz nyelvet / Alege limba / Select language:",
        "fav_title":       "⭐ *Locatii favorite*",
        "fav_empty":       "Nu ai locatii salvate inca.\nApasa ➕ pentru a adauga una.",
        "fav_add_btn":     "➕ Adauga favorit",
        "fav_del_btn":     "🗑 Sterge",
        "fav_back_btn":    "← Inapoi",
        "fav_ask_name":    "📝 Scrie un nume pentru aceasta locatie:\n_(ex: Acasa, Firma, Granita Nadlac)_",
        "fav_ask_loc":     "📍 Acum trimite locatia\n(buton GPS sau coordonate/link):",
        "fav_saved":       "✅ Favorit salvat: *{name}*",
        "fav_limit":       "❌ Maxim 10 favorite. Sterge unul mai intai.",
        "fav_deleted":     "🗑 Sters: *{name}*",
        "fav_set":         "📍 *{name}*",
        "fav_nav_btn":     "🧭 Navigare — Google Maps",
        "fav_search_btn":  "🔍 Cauta in jur de 20 km",
        "fav_del_prompt":  "🗑 Ce favorit stergi?",
        "journal_btn":        "📋 Jurnal transporturi",
        "journal_menu_title": "📋 *Jurnal transporturi*",
        "journal_add_btn":    "➕ Transport nou",
        "journal_list_btn":   "📄 Ultimele 5 intrari",
        "journal_report_btn": "📊 Raport lunar",
        "journal_ask_route":  "🛣 Traseu (de unde → unde):",
        "journal_ask_ast":    "📄 Nr. AST (sau - daca nu ai):",
        "journal_ask_km":     "🔢 Km parcursi (din AST, ex: 748):",
        "journal_ask_dims":   "📐 Dimensiuni si masa (ex: 28x2.8x4.3m, 110t):",
        "journal_ask_notes":  "📝 Observatii (sau - daca nu ai):",
        "journal_saved":      "✅ Salvat! #{id} | {date}\n🛣 {route}",
        "journal_empty":      "Nu exista inregistrari inca.",
        "journal_ask_month":  "📊 Ce luna? Scrie: `LL.AAAA` (ex: `04.2026`)",
        "journal_no_data":    "Nu exista date pentru aceasta luna.",
        "journal_del_btn":    "🗑 Sterge intrare",
        "journal_del_prompt": "Ce intrare stergi? (scrie #numar, ex: `#3`)",
        "journal_del_ok":     "🗑 Sters: #{id}",
        "journal_del_fail":   "❌ Nu gasit: #{id}",
        "journal_edit_btn":   "✏️ Editare",
        "journal_edit_prompt":"Ce intrare editezi? (scrie #numar, ex: `#3`)",
        "journal_edit_show":  "✏️ *#{id}* | {date}\n🛣 {route}\n📄 {ast}\n🔢 {km} km\n📐 {dims}\n📝 {notes}\n\nCe camp modifici?",
        "journal_edit_fail":  "❌ Nu gasit: #{id}",
        "journal_edit_ask":   "✏️ Valoare noua ({field}):",
        "journal_edit_ok":    "✅ Actualizat: #{id}",
        "journal_field_route":"🛣 Traseu",
        "journal_field_ast":  "📄 Nr. AST",
        "journal_field_km":   "🔢 Km",
        "journal_field_dims": "📐 Dimensiuni",
        "journal_field_notes":"📝 Observatii",
        "categories": {
            "fastfood":    "🍔 Fast Food",
            "mancare":     "🍽 Mancare",
            "wc":          "🚻 WC",
            "combustibil": "⛽ Combustibil",
            "parcare_tir": "🅿️ Parcare TIR",
            "service":     "🔧 Service",
            "hotel":       "🛏 Hotel",
            "mol":         "🔴 MOL",
            "supermarket": "🛒 Supermarket",
            "spital":      "🏥 Spital / Urgente",
            "vulcanizare": "🔩 Vulcanizare",
            "atm":         "💶 ATM / Banca",
            "cafenea":     "☕ Cafenea",
            "pekseg":      "🥐 Patiserie",
        },
    },
    "en": {
        "welcome": (
            "👋 *ConvoyLocator*\n\n"
            "Send me your location and I'll find what you need within 20 km.\n\n"
            "📍 GPS button — current location\n"
            "📌 Manual — coordinates or Google Maps link\n"
            "⭐ Favourites — saved locations"
        ),
        "location_btn":    "📍 Share my location",
        "manual_btn":      "📌 Enter location manually",
        "fav_btn":         "⭐ Favourites",
        "best_stop_btn":   "🛑 Best Stop",
        "checklist_btn":   "✅ Checklist",
        "checklist_text":  (
            "✅ *ESCORT CHECKLIST*\n\n"
            "🏠 *Before departure — Home:*\n"
            "1\\. 📄 Read the permit — instructions, restrictions\n"
            "2\\. 🗺 Prepare the route\n"
            "3\\. 📝 Fill in the Ordin de Deplasare\n"
            "4\\. 📋 Fill in the escort letter\n"
            "5\\. ⏱ Travel time: Bors → meeting point\n\n"
            "🚛 *Before departure — At the truck:*\n"
            "6\\. 🔦 Inspect truck: beacons, cargo securing, dimensions\n"
            "7\\. 📱 Set up prepared route on GPS\n"
            "8\\. 💧 500 ml bottle — present?\n\n"
            "─────────────────\n"
            "📝 *Enter important route notes:*\n"
            "_\\(bridges, restricted sections, special instructions…\\)_"
        ),
        "checklist_notes_ok": "📋 Notes saved:\n\n_{notes}_",
        "manual_prompt":   "📌 Paste coordinates or a Google Maps link:\n\nExample: `47.0785, 21.9189`\nor: `https://maps.app.goo.gl/xxxxx`",
        "location_ok":     "📍 Location received! What are you looking for within 20 km?",
        "manual_ok":       "📌 Location set! What are you looking for within 20 km?",
        "manual_fail":     "❌ Could not read the location.\nTry coordinates: `47.0785, 21.9189`",
        "no_location":     "📍 Please share your location first using the button below.",
        "no_results":      "Nothing found within 20 km.\nTry another category or update your location.",
        "nearest":         "— nearest:",
        "open_maps":       "Open in Google Maps",
        "search_error":    "Search error: ",
        "ff_brands":       "🏆 Chains (McD · KFC · BK):",
        "ff_others":       "🍔 Other fast food:",
        "lang_changed":    "✅ Language: English",
        "lang_select":     "Válassz nyelvet / Alege limba / Select language:",
        "fav_title":       "⭐ *Favourite locations*",
        "fav_empty":       "No saved locations yet.\nTap ➕ to add one.",
        "fav_add_btn":     "➕ Add favourite",
        "fav_del_btn":     "🗑 Delete",
        "fav_back_btn":    "← Back",
        "fav_ask_name":    "📝 Enter a name for this location:\n_(e.g. Home, Company, Nadlac border)_",
        "fav_ask_loc":     "📍 Now send the location\n(GPS button or coordinates/link):",
        "fav_saved":       "✅ Favourite saved: *{name}*",
        "fav_limit":       "❌ Maximum 10 favourites. Delete one first.",
        "fav_deleted":     "🗑 Deleted: *{name}*",
        "fav_set":         "📍 *{name}*",
        "fav_nav_btn":     "🧭 Navigate — Google Maps",
        "fav_search_btn":  "🔍 Search within 20 km",
        "fav_del_prompt":  "🗑 Which favourite do you want to delete?",
        "journal_btn":        "📋 Transport journal",
        "journal_menu_title": "📋 *Transport journal*",
        "journal_add_btn":    "➕ New transport",
        "journal_list_btn":   "📄 Last 5 entries",
        "journal_report_btn": "📊 Monthly report",
        "journal_ask_route":  "🛣 Route (from → to):",
        "journal_ask_ast":    "📄 AST number (or - if none):",
        "journal_ask_km":     "🔢 Km traveled (from AST, e.g. 748):",
        "journal_ask_dims":   "📐 Dimensions and mass (e.g. 28x2.8x4.3m, 110t):",
        "journal_ask_notes":  "📝 Notes (or - if none):",
        "journal_saved":      "✅ Saved! #{id} | {date}\n🛣 {route}",
        "journal_empty":      "No entries yet.",
        "journal_ask_month":  "📊 Which month? Write: `MM.YYYY` (e.g. `04.2026`)",
        "journal_no_data":    "No data for this month.",
        "journal_del_btn":    "🗑 Delete entry",
        "journal_del_prompt": "Which entry to delete? (write #number, e.g. `#3`)",
        "journal_del_ok":     "🗑 Deleted: #{id}",
        "journal_del_fail":   "❌ Not found: #{id}",
        "journal_edit_btn":   "✏️ Edit",
        "journal_edit_prompt":"Which entry do you want to edit? (write #number, e.g. `#3`)",
        "journal_edit_show":  "✏️ *#{id}* | {date}\n🛣 {route}\n📄 {ast}\n🔢 {km} km\n📐 {dims}\n📝 {notes}\n\nWhich field do you want to change?",
        "journal_edit_fail":  "❌ Not found: #{id}",
        "journal_edit_ask":   "✏️ New value ({field}):",
        "journal_edit_ok":    "✅ Updated: #{id}",
        "journal_field_route":"🛣 Route",
        "journal_field_ast":  "📄 AST number",
        "journal_field_km":   "🔢 Km",
        "journal_field_dims": "📐 Dimensions",
        "journal_field_notes":"📝 Notes",
        "categories": {
            "fastfood":    "🍔 Fast Food",
            "mancare":     "🍽 Food",
            "wc":          "🚻 WC",
            "combustibil": "⛽ Fuel",
            "parcare_tir": "🅿️ TIR Parking",
            "service":     "🔧 Service",
            "hotel":       "🛏 Hotel",
            "mol":         "🔴 MOL",
            "supermarket": "🛒 Supermarket",
            "spital":      "🏥 Hospital / Emergency",
            "vulcanizare": "🔩 Tyre Repair",
            "atm":         "💶 ATM / Bank",
            "cafenea":     "☕ Café",
            "pekseg":      "🥐 Bakery",
        },
    },
}

PLACES_LANG = {"hu": "hu", "ro": "ro", "en": "en"}


def _t(ctx: ContextTypes.DEFAULT_TYPE, key: str) -> str:
    lang = ctx.user_data.get("lang", DEFAULT_LANG)
    return STRINGS[lang][key]


def _lang(ctx: ContextTypes.DEFAULT_TYPE) -> str:
    return ctx.user_data.get("lang", DEFAULT_LANG)


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _location_keyboard(ctx: ContextTypes.DEFAULT_TYPE) -> ReplyKeyboardMarkup:
    rows = []
    webapp_url = os.getenv("WEBAPP_URL", "").rstrip("/")
    if webapp_url:
        rows.append([KeyboardButton("🚛 ConvoyLocator App", web_app=WebAppInfo(url=webapp_url))])
    rows += [
        [KeyboardButton(_t(ctx, "location_btn"), request_location=True)],
        [KeyboardButton(_t(ctx, "best_stop_btn"))],
        [KeyboardButton(_t(ctx, "manual_btn")),
         KeyboardButton(_t(ctx, "fav_btn")),
         KeyboardButton(_t(ctx, "checklist_btn"))],
        [KeyboardButton(_t(ctx, "journal_btn"))],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)


def _journal_menu_keyboard(ctx: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(ctx, "journal_add_btn"),    callback_data="jrn_add")],
        [InlineKeyboardButton(_t(ctx, "journal_list_btn"),   callback_data="jrn_list"),
         InlineKeyboardButton(_t(ctx, "journal_report_btn"), callback_data="jrn_report")],
        [InlineKeyboardButton(_t(ctx, "journal_edit_btn"),   callback_data="jrn_edit"),
         InlineKeyboardButton(_t(ctx, "journal_del_btn"),    callback_data="jrn_del")],
    ])


def _journal_edit_field_keyboard(ctx: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """Inline gombok: melyik mezőt szerkessze."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(ctx, "journal_field_route"), callback_data="jrn_ef_route"),
         InlineKeyboardButton(_t(ctx, "journal_field_ast"),   callback_data="jrn_ef_ast")],
        [InlineKeyboardButton(_t(ctx, "journal_field_km"),    callback_data="jrn_ef_km"),
         InlineKeyboardButton(_t(ctx, "journal_field_dims"),  callback_data="jrn_ef_dims")],
        [InlineKeyboardButton(_t(ctx, "journal_field_notes"), callback_data="jrn_ef_notes")],
    ])


def _cat_rows(cats: dict) -> list:
    return [
        [InlineKeyboardButton(cats["fastfood"],    callback_data="cat_fastfood"),
         InlineKeyboardButton(cats["mancare"],     callback_data="cat_mancare")],
        [InlineKeyboardButton(cats["wc"],          callback_data="cat_wc"),
         InlineKeyboardButton(cats["combustibil"], callback_data="cat_combustibil")],
        [InlineKeyboardButton(cats["parcare_tir"], callback_data="cat_parcare_tir"),
         InlineKeyboardButton(cats["service"],     callback_data="cat_service")],
        [InlineKeyboardButton(cats["hotel"],       callback_data="cat_hotel"),
         InlineKeyboardButton(cats["mol"],         callback_data="cat_mol")],
        [InlineKeyboardButton(cats["supermarket"], callback_data="cat_supermarket"),
         InlineKeyboardButton(cats["spital"],      callback_data="cat_spital")],
        [InlineKeyboardButton(cats["vulcanizare"], callback_data="cat_vulcanizare"),
         InlineKeyboardButton(cats["atm"],         callback_data="cat_atm")],
        [InlineKeyboardButton(cats["cafenea"],     callback_data="cat_cafenea"),
         InlineKeyboardButton(cats["pekseg"],      callback_data="cat_pekseg")],
    ]


def _category_keyboard(ctx: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(_cat_rows(_t(ctx, "categories")))


def _result_keyboard(ctx: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """Category grid with repeat button on top."""
    cats = _t(ctx, "categories")
    last_cat = ctx.user_data.get("last_cat")
    rows = []
    if last_cat and last_cat in cats:
        rows.append([InlineKeyboardButton(
            f"🔁 {cats[last_cat]}", callback_data="repeat_cat"
        )])
    rows += _cat_rows(cats)
    return InlineKeyboardMarkup(rows)


def _lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇭🇺 Magyar", callback_data="lang_hu"),
        InlineKeyboardButton("🇷🇴 Română", callback_data="lang_ro"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
    ]])


def _fav_menu_keyboard(chat_id: int, ctx: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """Meniu favorite: un buton per locatie + Add + Delete."""
    favs = favorites.load(chat_id)
    rows = []
    for name in favs:
        rows.append([InlineKeyboardButton(f"📍 {name}", callback_data=f"fav_sel_{name}")])
    rows.append([
        InlineKeyboardButton(_t(ctx, "fav_add_btn"), callback_data="fav_add"),
        InlineKeyboardButton(_t(ctx, "fav_del_btn"), callback_data="fav_del"),
    ])
    return InlineKeyboardMarkup(rows)


def _fav_delete_keyboard(chat_id: int, ctx: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """Lista favorite ca butoane de stergere."""
    favs = favorites.load(chat_id)
    rows = []
    for name in favs:
        rows.append([InlineKeyboardButton(f"🗑 {name}", callback_data=f"fav_delconfirm_{name}")])
    rows.append([InlineKeyboardButton(_t(ctx, "fav_back_btn"), callback_data="fav_menu")])
    return InlineKeyboardMarkup(rows)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_m(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/m — aktuális útvonal megjegyzések megjelenítése."""
    notes = ctx.user_data.get("route_notes")
    if not notes:
        await update.message.reply_text(
            "📝 Nincs megjegyzés.\n"
            "Használd a ✅ Checklist gombot és a végén add meg."
        )
        return
    await update.message.reply_text(
        f"📝 *Útvonal megjegyzések:*\n\n{notes}",
        parse_mode="Markdown",
    )


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        STRINGS["hu"]["lang_select"],
        reply_markup=_lang_keyboard(),
    )


async def cmd_limba(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        STRINGS["hu"]["lang_select"],
        reply_markup=_lang_keyboard(),
    )


async def on_lang_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    lang = q.data.split("_")[1]
    ctx.user_data["lang"] = lang
    await q.edit_message_text(STRINGS[lang]["lang_changed"])
    await q.message.reply_text(
        _t(ctx, "welcome"),
        parse_mode="Markdown",
        reply_markup=_location_keyboard(ctx),
    )


# ── Favorite handlers ─────────────────────────────────────────────────────────

async def on_fav_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Afiseaza meniul de favorite (apelat din callback sau din butonul reply)."""
    chat_id = update.effective_chat.id
    favs = favorites.load(chat_id)
    text = _t(ctx, "fav_title")
    if not favs:
        text += f"\n\n{_t(ctx, 'fav_empty')}"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=_fav_menu_keyboard(chat_id, ctx),
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=_fav_menu_keyboard(chat_id, ctx),
        )


async def on_fav_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Favorit selectat — buton navigatie URL direct + optiune cautare."""
    q = update.callback_query
    await q.answer()
    name = q.data[len("fav_sel_"):]
    favs = favorites.load(update.effective_chat.id)
    if name not in favs:
        await q.edit_message_text("❌ Favoritul nu mai exista.")
        return
    loc = favs[name]
    lat, lng = loc["lat"], loc["lng"]
    ctx.user_data["lat"] = lat
    ctx.user_data["lng"] = lng
    ctx.user_data["fav_state"] = None

    # URL navigatie Google Maps — deschide direct rutarea in aplicatie
    nav_url = f"https://maps.google.com/?daddr={lat},{lng}&dirflg=d"

    quick_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(ctx, "fav_nav_btn"), url=nav_url)],
        [InlineKeyboardButton(_t(ctx, "fav_search_btn"), callback_data="fav_show_cats")],
    ])
    await q.edit_message_text(
        _t(ctx, "fav_set").format(name=name),
        parse_mode="Markdown",
        reply_markup=quick_kb,
    )


async def on_fav_show_cats(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Afiseaza grila de categorii dupa ce utilizatorul alege 'Cauta in jur'."""
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(
        "🔍",
        reply_markup=_category_keyboard(ctx),
    )


async def on_fav_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Start flux adaugare favorit — cere numele."""
    q = update.callback_query
    await q.answer()
    ctx.user_data["fav_state"] = "waiting_name"
    await q.edit_message_text(
        _t(ctx, "fav_ask_name"),
        parse_mode="Markdown",
    )


async def on_fav_del_show(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Afiseaza lista de favorite pentru stergere."""
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        _t(ctx, "fav_del_prompt"),
        reply_markup=_fav_delete_keyboard(update.effective_chat.id, ctx),
    )


async def on_fav_del_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Sterge favoritul selectat."""
    q = update.callback_query
    await q.answer()
    name = q.data[len("fav_delconfirm_"):]
    favorites.delete(update.effective_chat.id, name)
    msg = _t(ctx, "fav_deleted").format(name=name)
    await q.edit_message_text(
        msg,
        parse_mode="Markdown",
        reply_markup=_fav_menu_keyboard(update.effective_chat.id, ctx),
    )


# ── Journal handlers ──────────────────────────────────────────────────────────

async def on_journal_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Afiseaza meniul jurnalului."""
    text = _t(ctx, "journal_menu_title")
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=_journal_menu_keyboard(ctx),
        )
    else:
        await update.message.reply_text(
            text, parse_mode="Markdown",
            reply_markup=_journal_menu_keyboard(ctx),
        )


async def on_journal_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    ctx.user_data["jrn_state"] = "route"
    await q.edit_message_text(_t(ctx, "journal_ask_route"))


async def on_journal_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    entries = journal.last_entries(update.effective_chat.id)
    if not entries:
        await q.edit_message_text(
            _t(ctx, "journal_empty"),
            reply_markup=_journal_menu_keyboard(ctx),
        )
        return
    lines = []
    for e in reversed(entries):
        km_part = f"  🔢 {e['km']} km" if e.get('km') and e['km'] != "-" else ""
        lines.append(
            f"*#{e['id']}* | {e['date']}\n"
            f"🛣 {e['route']}\n"
            f"📄 {e['ast']}{km_part}\n"
            f"📐 {e['dims']}\n"
            + (f"📝 {e['notes']}\n" if e['notes'] not in ("-", "") else "")
        )
    await q.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=_journal_menu_keyboard(ctx),
    )


async def on_journal_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    ctx.user_data["jrn_state"] = "report_month"
    await q.edit_message_text(
        _t(ctx, "journal_ask_month"), parse_mode="Markdown"
    )


async def on_journal_del(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    ctx.user_data["jrn_state"] = "del_id"
    await q.edit_message_text(_t(ctx, "journal_del_prompt"))


async def on_journal_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Edit gomb → kéri a bejegyzés #számát."""
    q = update.callback_query
    await q.answer()
    ctx.user_data["jrn_state"] = "edit_id"
    await q.edit_message_text(_t(ctx, "journal_edit_prompt"), parse_mode="Markdown")


async def on_journal_edit_field(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Melyik mezőt szerkesszük — inline gomb callback."""
    q = update.callback_query
    await q.answer()
    field = q.data.replace("jrn_ef_", "")   # route / ast / km / dims / notes
    ctx.user_data["jrn_edit_field"] = field
    ctx.user_data["jrn_state"] = "edit_value"
    field_label = _t(ctx, f"journal_field_{field}")
    await q.edit_message_text(
        _t(ctx, "journal_edit_ask").format(field=field_label),
        parse_mode="Markdown",
    )


# ── Text / Location handlers ──────────────────────────────────────────────────

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    if "lang" not in ctx.user_data:
        ctx.user_data["lang"] = DEFAULT_LANG

    # Buton "🛑 Best Stop"
    best_stop_labels = {STRINGS[l]["best_stop_btn"] for l in STRINGS}
    if text in best_stop_labels:
        await _do_best_stop(update, ctx)
        return

    # Buton "✅ Checklist"
    checklist_labels = {STRINGS[l]["checklist_btn"] for l in STRINGS}
    if text in checklist_labels:
        ctx.user_data["checklist_state"] = "waiting_notes"
        await update.message.reply_text(
            _t(ctx, "checklist_text"),
            parse_mode="MarkdownV2",
        )
        return

    # Checklist — megjegyzések fogadása
    if ctx.user_data.get("checklist_state") == "waiting_notes":
        ctx.user_data["checklist_state"] = None
        notes = text.strip()
        ctx.user_data["route_notes"] = notes
        await update.message.reply_text(
            _t(ctx, "checklist_notes_ok").format(notes=notes),
            parse_mode="Markdown",
        )
        return

    # Buton "⭐ Favorite"
    fav_labels = {STRINGS[l]["fav_btn"] for l in STRINGS}
    if text in fav_labels:
        await on_fav_menu(update, ctx)
        return

    # Flux adaugare favorit — pasul 1: primire nume
    if ctx.user_data.get("fav_state") == "waiting_name":
        name = text.strip()[:30]
        ctx.user_data["fav_pending_name"] = name
        ctx.user_data["fav_state"] = "waiting_location"
        await update.message.reply_text(
            _t(ctx, "fav_ask_loc"),
            parse_mode="Markdown",
            reply_markup=_location_keyboard(ctx),
        )
        return

    # Flux adaugare favorit — pasul 2: primire locatie text
    if ctx.user_data.get("fav_state") == "waiting_location":
        coords = location_parser.parse(text)
        if coords:
            await _save_fav_coords(update, ctx, coords[0], coords[1])
        else:
            await update.message.reply_text(
                _t(ctx, "manual_fail"), parse_mode="Markdown"
            )
        return

    # Buton "📋 Jurnal"
    journal_labels = {STRINGS[l]["journal_btn"] for l in STRINGS}
    if text in journal_labels:
        await on_journal_menu(update, ctx)
        return

    # Flux jurnal — pasi secventiali
    jrn = ctx.user_data.get("jrn_state")
    if jrn in ("route", "ast", "km", "dims", "notes", "report_month", "del_id", "edit_id", "edit_value"):
        await _handle_journal_input(update, ctx, text, jrn)
        return

    # Buton manual sau locatie in text
    manual_labels = {STRINGS[l]["manual_btn"] for l in STRINGS}
    if text in manual_labels:
        await update.message.reply_text(_t(ctx, "manual_prompt"), parse_mode="Markdown")
        ctx.user_data["awaiting_manual"] = True
        return

    if ctx.user_data.get("awaiting_manual") or _looks_like_location(text):
        coords = location_parser.parse(text)
        if coords:
            ctx.user_data["lat"] = coords[0]
            ctx.user_data["lng"] = coords[1]
            ctx.user_data["awaiting_manual"] = False
            await update.message.reply_text(
                _t(ctx, "manual_ok"),
                reply_markup=_category_keyboard(ctx),
            )
        else:
            await update.message.reply_text(
                _t(ctx, "manual_fail"), parse_mode="Markdown"
            )


async def _handle_journal_input(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str, state: str
) -> None:
    """Proceseaza inputul pas-cu-pas pentru adaugarea unei intrari in jurnal."""
    d = ctx.user_data

    if state == "route":
        d["jrn_route"] = text
        d["jrn_state"] = "ast"
        await update.message.reply_text(_t(ctx, "journal_ask_ast"))

    elif state == "ast":
        d["jrn_ast"] = text
        d["jrn_state"] = "km"
        await update.message.reply_text(_t(ctx, "journal_ask_km"))

    elif state == "km":
        d["jrn_km"] = text
        d["jrn_state"] = "dims"
        await update.message.reply_text(_t(ctx, "journal_ask_dims"))

    elif state == "dims":
        d["jrn_dims"] = text
        d["jrn_state"] = "notes"
        await update.message.reply_text(_t(ctx, "journal_ask_notes"))

    elif state == "notes":
        entry = journal.add_entry(
            chat_id=update.effective_chat.id,
            route=d.pop("jrn_route", ""),
            ast=d.pop("jrn_ast", "-"),
            km=d.pop("jrn_km", "-"),
            dims=d.pop("jrn_dims", "-"),
            notes=text if text != "-" else "",
        )
        d["jrn_state"] = None
        await update.message.reply_text(
            _t(ctx, "journal_saved").format(id=entry["id"], date=entry["date"], route=entry["route"]),
            parse_mode="Markdown",
            reply_markup=_journal_menu_keyboard(ctx),
        )

    elif state == "report_month":
        import re as _re
        m = _re.match(r"^(\d{1,2})\.(\d{4})$", text.strip())
        if not m:
            await update.message.reply_text(_t(ctx, "journal_ask_month"), parse_mode="Markdown")
            return
        month, year = int(m.group(1)), int(m.group(2))
        d["jrn_state"] = None
        report = journal.monthly_report(update.effective_chat.id, month, year)
        if not report:
            await update.message.reply_text(
                _t(ctx, "journal_no_data"),
                reply_markup=_journal_menu_keyboard(ctx),
            )
        else:
            # Trimite in bucati daca e lung
            LIMIT = 3800
            for i in range(0, len(report), LIMIT):
                await update.message.reply_text(report[i:i + LIMIT])
            await update.message.reply_text("─", reply_markup=_journal_menu_keyboard(ctx))

    elif state == "del_id":
        import re as _re
        m = _re.match(r"^#?(\d+)$", text.strip())
        if not m:
            await update.message.reply_text(_t(ctx, "journal_del_prompt"))
            return
        entry_id = int(m.group(1))
        d["jrn_state"] = None
        if journal.delete_entry(update.effective_chat.id, entry_id):
            await update.message.reply_text(
                _t(ctx, "journal_del_ok").format(id=entry_id),
                reply_markup=_journal_menu_keyboard(ctx),
            )
        else:
            await update.message.reply_text(
                _t(ctx, "journal_del_fail").format(id=entry_id),
                reply_markup=_journal_menu_keyboard(ctx),
            )

    elif state == "edit_id":
        import re as _re
        m = _re.match(r"^#?(\d+)$", text.strip())
        if not m:
            await update.message.reply_text(_t(ctx, "journal_edit_prompt"), parse_mode="Markdown")
            return
        entry_id = int(m.group(1))
        entry = journal.get_entry(update.effective_chat.id, entry_id)
        if not entry:
            await update.message.reply_text(
                _t(ctx, "journal_edit_fail").format(id=entry_id),
                reply_markup=_journal_menu_keyboard(ctx),
            )
            d["jrn_state"] = None
            return
        d["jrn_edit_id"] = entry_id
        d["jrn_state"] = None   # mező-választó inline gomb veszi át
        await update.message.reply_text(
            _t(ctx, "journal_edit_show").format(
                id=entry["id"], date=entry["date"],
                route=entry["route"], ast=entry["ast"],
                km=entry.get("km", "-"), dims=entry["dims"],
                notes=entry.get("notes", "-") or "-",
            ),
            parse_mode="Markdown",
            reply_markup=_journal_edit_field_keyboard(ctx),
        )

    elif state == "edit_value":
        entry_id = d.get("jrn_edit_id")
        field    = d.get("jrn_edit_field")
        d["jrn_state"] = None
        d.pop("jrn_edit_id", None)
        d.pop("jrn_edit_field", None)
        if entry_id and field and journal.update_entry(update.effective_chat.id, entry_id, field, text.strip()):
            await update.message.reply_text(
                _t(ctx, "journal_edit_ok").format(id=entry_id),
                reply_markup=_journal_menu_keyboard(ctx),
            )
        else:
            await update.message.reply_text(
                _t(ctx, "journal_edit_fail").format(id=entry_id or "?"),
                reply_markup=_journal_menu_keyboard(ctx),
            )


async def on_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    loc = update.message.location
    if "lang" not in ctx.user_data:
        ctx.user_data["lang"] = DEFAULT_LANG

    # Flux adaugare favorit — pasul 2: primire locatie GPS
    if ctx.user_data.get("fav_state") == "waiting_location":
        await _save_fav_coords(update, ctx, loc.latitude, loc.longitude)
        return

    ctx.user_data["lat"] = loc.latitude
    ctx.user_data["lng"] = loc.longitude
    await update.message.reply_text(
        _t(ctx, "location_ok"),
        reply_markup=_category_keyboard(ctx),
    )


async def _save_fav_coords(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, lat: float, lng: float
) -> None:
    name = ctx.user_data.pop("fav_pending_name", "?")
    ctx.user_data["fav_state"] = None
    ok = favorites.save_location(update.effective_chat.id, name, lat, lng)
    if ok:
        await update.message.reply_text(
            _t(ctx, "fav_saved").format(name=name),
            parse_mode="Markdown",
            reply_markup=_location_keyboard(ctx),
        )
    else:
        await update.message.reply_text(_t(ctx, "fav_limit"))


# ── Categoria handler ─────────────────────────────────────────────────────────

async def on_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    category = q.data.replace("cat_", "")
    await _do_search(q, ctx, category)


async def on_repeat(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    category = ctx.user_data.get("last_cat")
    if not category:
        return
    await _do_search(q, ctx, category)


async def _do_search(q, ctx: ContextTypes.DEFAULT_TYPE, category: str) -> None:
    lat = ctx.user_data.get("lat")
    lng = ctx.user_data.get("lng")
    if lat is None or lng is None:
        await q.message.reply_text(
            _t(ctx, "no_location"),
            reply_markup=_location_keyboard(ctx),
        )
        return

    ctx.user_data["last_cat"] = category

    if category == "fastfood":
        await _do_fastfood_search(q, ctx, lat, lng)
        return

    cat_info = places.CATEGORIES.get(category, {})
    emoji = cat_info.get("emoji", "📍")
    label = _t(ctx, "categories").get(category, category)

    await q.message.chat.send_action(ChatAction.FIND_LOCATION)

    try:
        results = places.search(lat, lng, category, lang=PLACES_LANG[_lang(ctx)])
    except Exception as e:
        log.exception("Places API error")
        await q.message.reply_text(_t(ctx, "search_error") + str(e))
        return

    if not results:
        await q.message.reply_text(
            f"{emoji} *{label}*\n{_t(ctx, 'no_results')}",
            parse_mode="Markdown",
            reply_markup=_result_keyboard(ctx),
        )
        return

    open_maps = _t(ctx, "open_maps")
    nearest   = _t(ctx, "nearest")
    lines = [f"{emoji} *{label}* {nearest}\n"]
    for i, r in enumerate(results, 1):
        rating = f"⭐ {r['rating']}" if r["rating"] else ""
        lines.append(
            f"*{i}. {r['name']}* {rating}\n"
            f"📌 {r['address']}\n"
            f"📏 {r['distance_km']} km\n"
            f"[{open_maps}]({r['maps_url']})\n"
        )

    await q.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=_result_keyboard(ctx),
    )


async def _do_fastfood_search(q, ctx: ContextTypes.DEFAULT_TYPE, lat: float, lng: float) -> None:
    await q.message.chat.send_action(ChatAction.FIND_LOCATION)
    label = _t(ctx, "categories").get("fastfood", "🍔")
    try:
        data = places.search_fastfood(lat, lng, lang=PLACES_LANG[_lang(ctx)])
    except Exception as e:
        log.exception("FastFood search error")
        await q.message.reply_text(_t(ctx, "search_error") + str(e))
        return

    brands = data["brands"]
    others = data["others"]
    open_maps = _t(ctx, "open_maps")

    if not brands and not others:
        await q.message.reply_text(
            f"🍔 *{label}*\n{_t(ctx, 'no_results')}",
            parse_mode="Markdown",
            reply_markup=_result_keyboard(ctx),
        )
        return

    lines = [f"🍔 *{label}*\n"]

    if brands:
        lines.append(f"*{_t(ctx, 'ff_brands')}*")
        for r in brands:
            rating = f"⭐ {r['rating']}" if r["rating"] else ""
            lines.append(
                f"*{r['name']}* {rating}\n"
                f"📌 {r['address']}\n"
                f"📏 {r['distance_km']} km\n"
                f"[{open_maps}]({r['maps_url']})\n"
            )

    if others:
        lines.append(f"*{_t(ctx, 'ff_others')}*")
        for r in others:
            rating = f"⭐ {r['rating']}" if r["rating"] else ""
            lines.append(
                f"*{r['name']}* {rating}\n"
                f"📌 {r['address']}\n"
                f"📏 {r['distance_km']} km\n"
                f"[{open_maps}]({r['maps_url']})\n"
            )

    await q.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=_result_keyboard(ctx),
    )


# ── Best Stop ────────────────────────────────────────────────────────────────

async def _do_best_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """🛑 Best Stop — üzemanyag + étel + parkoló legjobb kombinációja."""
    lat = ctx.user_data.get("lat")
    lng = ctx.user_data.get("lng")
    if lat is None or lng is None:
        await update.message.reply_text(
            _t(ctx, "no_location"),
            reply_markup=_location_keyboard(ctx),
        )
        return

    await update.message.chat.send_action(ChatAction.FIND_LOCATION)
    try:
        clusters = places.search_best_stop(lat, lng, lang=PLACES_LANG[_lang(ctx)])
    except Exception as e:
        log.exception("Best Stop error")
        await update.message.reply_text(_t(ctx, "search_error") + str(e))
        return

    if not clusters:
        await update.message.reply_text(_t(ctx, "no_results"))
        return

    medals = ["🥇", "🥈", "🥉"]
    open_maps = _t(ctx, "open_maps")
    lines = ["🛑 *Best Stop — Top 3*\n"]

    for i, cl in enumerate(clusters):
        fuel    = cl["fuel"]
        food    = cl["food"]
        parking = cl["parking"]
        medal   = medals[i] if i < 3 else f"{i+1}."

        lines.append(f"{'━' * 20}")
        lines.append(f"{medal} *{fuel['name']}* — {fuel['distance_km']} km")
        lines.append(f"⛽ {fuel['name']} | 📌 {fuel['address']}")

        if food:
            d = f"{food['dist_to_anchor']:.1f} km" if food['dist_to_anchor'] >= 0.1 else f"{int(food['dist_to_anchor']*1000)} m"
            lines.append(f"🍽 {food['name']} — {d}")
        else:
            lines.append("🍽 _(nincs közeli étterem)_")

        if parking:
            d = f"{parking['dist_to_anchor']:.1f} km" if parking['dist_to_anchor'] >= 0.1 else f"{int(parking['dist_to_anchor']*1000)} m"
            lines.append(f"🅿️ {parking['name']} — {d}")
        else:
            lines.append("🅿️ _(nincs közeli parkoló)_")

        lines.append(f"[{open_maps}]({fuel['maps_url']})\n")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=_result_keyboard(ctx),
    )


# ── Util ──────────────────────────────────────────────────────────────────────

def _looks_like_location(text: str) -> bool:
    t = text.strip()
    return (
        "maps" in t.lower()
        or "goo.gl" in t.lower()
        or bool(re.match(r"^-?\d+\.\d+[,\s]+-?\d+\.\d+$", t))
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN lipseste din envi.env")
    if not os.getenv("GOOGLE_PLACES_API_KEY"):
        raise SystemExit("GOOGLE_PLACES_API_KEY lipseste din envi.env")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("limba",  cmd_limba))
    app.add_handler(CommandHandler("m",      cmd_m))

    # Locatie GPS
    app.add_handler(MessageHandler(filters.LOCATION, on_location))
    # Text liber (butoane reply + input manual + flux favorite)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Callback-uri limba
    app.add_handler(CallbackQueryHandler(on_lang_select,    pattern="^lang_"))
    # Callback-uri categorii
    app.add_handler(CallbackQueryHandler(on_category,       pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(on_repeat,         pattern="^repeat_cat$"))
    # Callback-uri favorite
    app.add_handler(CallbackQueryHandler(on_fav_menu,       pattern="^fav_menu$"))
    app.add_handler(CallbackQueryHandler(on_fav_add_start,  pattern="^fav_add$"))
    app.add_handler(CallbackQueryHandler(on_fav_del_show,   pattern="^fav_del$"))
    app.add_handler(CallbackQueryHandler(on_fav_select,     pattern="^fav_sel_"))
    app.add_handler(CallbackQueryHandler(on_fav_show_cats,  pattern="^fav_show_cats$"))
    app.add_handler(CallbackQueryHandler(on_fav_del_confirm,pattern="^fav_delconfirm_"))
    # Jurnal
    app.add_handler(CallbackQueryHandler(on_journal_menu,   pattern="^jrn_menu$"))
    app.add_handler(CallbackQueryHandler(on_journal_add,    pattern="^jrn_add$"))
    app.add_handler(CallbackQueryHandler(on_journal_list,   pattern="^jrn_list$"))
    app.add_handler(CallbackQueryHandler(on_journal_report,       pattern="^jrn_report$"))
    app.add_handler(CallbackQueryHandler(on_journal_del,          pattern="^jrn_del$"))
    app.add_handler(CallbackQueryHandler(on_journal_edit,         pattern="^jrn_edit$"))
    app.add_handler(CallbackQueryHandler(on_journal_edit_field,   pattern="^jrn_ef_"))

    log.info("ConvoyLocator pornit.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
