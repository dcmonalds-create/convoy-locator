# ConvoyLocator — Railway Deploy

## 1. Railway projekt létrehozása

```bash
# Telepítsd a Railway CLI-t
npm install -g @railway/cli

# Bejelentkezés
railway login

# Projekt létrehozása és deploy
cd convoy_locator
railway init
railway up
```

## 2. Környezeti változók (Railway Dashboard → Variables)

| Változó | Érték |
|---------|-------|
| `TELEGRAM_BOT_TOKEN` | A bot tokened |
| `GOOGLE_PLACES_API_KEY` | Google Places API kulcs |
| `WEBHOOK_URL` | Railway-generált URL (pl. `https://convoy-locator.up.railway.app`) |
| `WEBAPP_URL` | Megegyezik a WEBHOOK_URL-lel (a Mini App URL-je) |

## 3. Railway URL meghatározása

Deploy után a Railway ad egy URL-t. Másold be a `WEBHOOK_URL` és `WEBAPP_URL` változókba.

Pl: `https://convoylocator-production.up.railway.app`

## 4. Ellenőrzés

- `GET /health` — `{"status":"ok"}`  
- `GET /` — a Mini App nyílik meg  
- Telegram botban `/start` → megjelenik a **🚛 ConvoyLocator App** gomb  

## Helyi fejlesztés (polling mód)

```bash
# .env nincs — az envi.env fájlt használja
python bot.py        # polling mód (WEBHOOK_URL nélkül)

# API szerver külön terminálon:
uvicorn api:app --reload --port 8000
# Mini App: http://localhost:8000/
```

## Fájlstruktúra

```
convoy_locator/
├── api.py          ← FastAPI (webhook + REST + static)
├── bot.py          ← Telegram bot (polling, helyi dev)
├── places.py       ← Google Places wrapper
├── journal.py      ← Szállítási napló
├── favorites.py    ← Kedvencek
├── webapp/
│   └── index.html  ← Telegram Mini App UI
├── Procfile        ← Railway process
├── railway.toml    ← Railway konfig
└── requirements.txt
```
