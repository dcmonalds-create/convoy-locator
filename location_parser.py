"""
Parseaza o locatie din text liber:
  - Coordonate brute:       47.0785, 21.9189
  - URL Google Maps lung:   https://www.google.com/maps/@47.07,21.91,17z
  - URL Google Maps cu q=:  https://maps.google.com/?q=47.07,21.91
  - URL scurt iOS/Android:  https://maps.app.goo.gl/xxxxx?g_st=ic

Problema EU/RO: redirect-ul scurt cade pe consent.google.com (GDPR).
Solutie: extragem URL-ul real din parametrul `continue=` si geocodam
adresa prin Google Geocoding API daca nu gasim coordonate directe.

Returneaza (lat, lng) sau None.
"""
from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_PATTERNS = [
    r"@(-?\d+\.\d+),(-?\d+\.\d+)",
    r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)",
    r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
]


def parse(text: str) -> tuple[float, float] | None:
    text = text.strip()

    # 1. Coordonate brute  "47.0785, 21.9189"
    m = re.match(r"^(-?\d{1,3}\.\d+)[,\s]+(-?\d{1,3}\.\d+)$", text)
    if m:
        return _validate(float(m.group(1)), float(m.group(2)))

    # 2. Incearca regex direct pe URL (URL-uri lungi cu @lat,lng)
    result = _try_patterns(text)
    if result:
        return result

    # 3. URL care necesita redirect
    if any(k in text for k in ("goo.gl", "maps.app", "maps.google", "google.com/maps")):
        resolved = _resolve_url(text)
        if resolved:
            result = _try_patterns(resolved)
            if result:
                return result
            # 4. Daca URL-ul are o adresa in q= (nu coordonate) → geocodare
            address = _extract_address(resolved)
            if address:
                return _geocode(address)

    return None


def _resolve_url(url: str) -> str | None:
    """
    Urmareste redirect-ul. Daca ajunge pe consent.google.com (GDPR EU),
    extrage URL-ul real din parametrul `continue=`.
    """
    try:
        r = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=10)
        final = str(r.url)

        if "consent.google.com" in final:
            params = parse_qs(urlparse(final).query)
            if "continue" in params:
                return unquote(params["continue"][0])
            return None

        return final
    except Exception:
        return None


def _try_patterns(text: str) -> tuple[float, float] | None:
    for pattern in _PATTERNS:
        m = re.search(pattern, text)
        if m:
            result = _validate(float(m.group(1)), float(m.group(2)))
            if result:
                return result
    return None


def _extract_address(url: str) -> str | None:
    """Extrage adresa din parametrul q= al unui URL Maps (cand nu sunt coordonate)."""
    m = re.search(r"[?&]q=([^&]+)", url)
    if not m:
        return None
    value = unquote(m.group(1)).replace("+", " ").strip()
    # Verifica sa nu fie deja coordonate numerice
    if re.match(r"^-?\d+\.\d+,\s*-?\d+\.\d+$", value):
        return None
    return value if len(value) > 3 else None


def _geocode(address: str) -> tuple[float, float] | None:
    """Converteste o adresa text in coordonate GPS via Google Geocoding API."""
    key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not key:
        return None
    try:
        r = httpx.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": address, "key": key},
            timeout=10,
        )
        data = r.json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return _validate(loc["lat"], loc["lng"])
    except Exception:
        pass
    return None


def _validate(lat: float, lng: float) -> tuple[float, float] | None:
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng
    return None
