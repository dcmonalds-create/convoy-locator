# Setup Google Cloud + Places API

## Pas 1 — Cont Google Cloud

1. Mergi la https://console.cloud.google.com
2. Conecteaza-te cu contul Google
3. Click **"Select a project"** → **"New Project"**
   - Nume: `convoy-locator`
   - Click **Create**

## Pas 2 — Activeaza Places API

1. In meniul din stanga: **APIs & Services** → **Library**
2. Cauta `Places API`
3. Click pe **Places API** → **Enable**

## Pas 3 — Creeaza cheia API

1. **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **API Key**
3. Copiaza cheia generata
4. (Recomandat) Click **Edit API Key** → **Restrict key** → selecteaza doar `Places API`

## Pas 4 — Adauga card de facturare (obligatoriu de Google)

1. **Billing** → **Link a billing account**
2. Adauga un card de credit/debit
3. Google ofera **$200 credit gratuit pe luna** — la volumul unui sofer individual costul real este $0

## Pas 5 — Completeaza envi.env

```
GOOGLE_PLACES_API_KEY=cheia_copiata_la_pasul_3
TELEGRAM_BOT_TOKEN=token_de_la_botfather
```

## Pas 6 — Porneste botul

```bash
cd ~/Downloads/convoy_locator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```
