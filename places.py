"""
Google Places API — Nearby Search, 20 km körzetben.
"""
from __future__ import annotations

import os
import httpx

RADIUS_M = 20_000  # 20 km — mindig fix

_BASE = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
_OK   = {"OK", "ZERO_RESULTS"}

CATEGORIES: dict[str, dict] = {
    "combustibil": {"type": "gas_station",  "keyword": None,            "emoji": "⛽", "label": "Combustibil"},
    "mancare":     {"type": "restaurant",   "keyword": None,            "emoji": "🍽", "label": "Restaurant / Mâncare"},
    "fastfood":    {"type": "restaurant",   "keyword": "fast food gyorsétterem", "emoji": "🍔", "label": "Fast Food"},
    "parcare_tir": {"type": "parking",      "keyword": "tir camion",    "emoji": "🅿️", "label": "Parcare TIR"},
    "mol":         {"type": "gas_station",  "keyword": "MOL",           "emoji": "🔴", "label": "Benzinărie MOL"},
    "service":     {"type": "car_repair",   "keyword": None,            "emoji": "🔧", "label": "Service auto"},
    "hotel":       {"type": "lodging",      "keyword": None,            "emoji": "🛏", "label": "Hotel / Cazare"},
    "cafenea":     {"type": "cafe",         "keyword": None,            "emoji": "☕", "label": "Cafenea"},
    "supermarket": {"type": "supermarket",  "keyword": None,            "emoji": "🛒", "label": "Supermarket"},
    "vulcanizare": {"type": "car_repair",   "keyword": "vulcanizare gumi tyres", "emoji": "🔩", "label": "Vulcanizare"},
    "atm":         {"type": "atm",          "keyword": None,            "emoji": "💶", "label": "ATM / Bancă"},
    "spital":      {"type": "hospital",     "keyword": None,            "emoji": "🏥", "label": "Spital / Urgențe"},
    "wc":          {"type": "gas_station",  "keyword": "toaleta wc",    "emoji": "🚻", "label": "WC"},
    "pekseg":      {"type": "bakery",       "keyword": None,            "emoji": "🥐", "label": "Pékség / Bakery"},
}


def _places_get(params: dict) -> list:
    """Places API hívás — hibát dob ha status nem OK/ZERO_RESULTS."""
    resp = httpx.get(_BASE, params=params, timeout=15)
    resp.raise_for_status()
    data   = resp.json()
    status = data.get("status", "OK")
    if status not in _OK:
        msg = data.get("error_message", "")
        raise RuntimeError(
            f"Google Places API: {status}" + (f" — {msg}" if msg else "")
        )
    return data.get("results", [])


def _to_result(place: dict, lat: float, lng: float) -> dict:
    loc  = place["geometry"]["location"]
    plat, plng = loc["lat"], loc["lng"]
    return {
        "name":         place.get("name", "?"),
        "address":      place.get("vicinity", ""),
        "rating":       place.get("rating"),
        "maps_url":     f"https://maps.google.com/?q={plat},{plng}",
        "distance_km":  _haversine(lat, lng, plat, plng),
        "lat":          plat,
        "lng":          plng,
    }


def search(lat: float, lng: float, category: str, lang: str = "hu") -> list[dict]:
    cat = CATEGORIES.get(category)
    if not cat:
        return []
    if category == "mol":
        return _search_mol(lat, lng, lang)

    params: dict = {
        "location": f"{lat},{lng}",
        "radius":   RADIUS_M,
        "type":     cat["type"],
        "language": lang,
        "key":      os.environ["GOOGLE_PLACES_API_KEY"],
    }
    if cat["keyword"]:
        params["keyword"] = cat["keyword"]

    results = [_to_result(p, lat, lng) for p in _places_get(params)]
    results.sort(key=lambda x: x["distance_km"])
    return results[:5]


def _search_mol(lat: float, lng: float, lang: str) -> list[dict]:
    key = os.environ["GOOGLE_PLACES_API_KEY"]

    def _fetch(keyword):
        params: dict = {
            "location": f"{lat},{lng}",
            "radius":   RADIUS_M,
            "type":     "gas_station",
            "language": lang,
            "key":      key,
        }
        if keyword:
            params["keyword"] = keyword
        raw = [_to_result(p, lat, lng) for p in _places_get(params)]
        raw.sort(key=lambda x: x["distance_km"])
        return [r for r in raw if "mol" in r["name"].lower()]

    results = _fetch("MOL") or _fetch(None)
    return results[:5]


_BRANDS = {"mcdonald", "kfc", "burger king", "subway", "pizza hut", "domino"}


def search_fastfood(lat: float, lng: float, lang: str = "hu") -> dict:
    key = os.environ["GOOGLE_PLACES_API_KEY"]

    def _fetch(kw):
        return _places_get({
            "location": f"{lat},{lng}", "radius": RADIUS_M,
            "type": "restaurant", "keyword": kw, "language": lang, "key": key,
        })

    seen, combined = set(), []
    for place in _fetch("McDonald's KFC Burger King") + _fetch("gyorsétterem fast food"):
        name = place.get("name", "")
        if name in seen:
            continue
        seen.add(name)
        combined.append(_to_result(place, lat, lng))

    combined.sort(key=lambda x: x["distance_km"])
    brands     = [p for p in combined if any(b in p["name"].lower() for b in _BRANDS)]
    brand_names = {p["name"] for p in brands}
    others     = [p for p in combined if p["name"] not in brand_names]
    return {"brands": brands[:4], "others": others[:4]}


def _search_raw(lat: float, lng: float, category: str, lang: str, n: int = 10) -> list[dict]:
    """Mint search(), de több találatot ad vissza lat/lng-vel (klaszterezéshez)."""
    cat = CATEGORIES.get(category)
    if not cat:
        return []
    params: dict = {
        "location": f"{lat},{lng}",
        "radius":   RADIUS_M,
        "type":     cat["type"],
        "language": lang,
        "key":      os.environ["GOOGLE_PLACES_API_KEY"],
    }
    if cat["keyword"]:
        params["keyword"] = cat["keyword"]
    results = [_to_result(p, lat, lng) for p in _places_get(params)]
    results.sort(key=lambda x: x["distance_km"])
    return results[:n]


def _nearest_within(anchor: dict, candidates: list[dict], radius_km: float) -> dict | None:
    best, best_d = None, float("inf")
    for c in candidates:
        d = _haversine(anchor["lat"], anchor["lng"], c["lat"], c["lng"])
        if d <= radius_km and d < best_d:
            best_d, best = d, {**c, "dist_to_anchor": d}
    return best


def search_best_stop(
    lat: float, lng: float, lang: str = "hu", cluster_km: float = 2.0
) -> list[dict]:
    fuels = _search_raw(lat, lng, "combustibil", lang, n=10)
    foods = _search_raw(lat, lng, "mancare",      lang, n=10)
    parks = _search_raw(lat, lng, "parcare_tir",  lang, n=10)

    clusters = []
    for fuel in fuels:
        food    = _nearest_within(fuel, foods, cluster_km)
        parking = _nearest_within(fuel, parks, cluster_km)
        score   = fuel["distance_km"]
        score  += (food["dist_to_anchor"]    * 0.2) if food    else 8.0
        score  += (parking["dist_to_anchor"] * 0.2) if parking else 8.0
        clusters.append({"fuel": fuel, "food": food, "parking": parking, "score": score})

    clusters.sort(key=lambda x: x["score"])
    return clusters[:3]


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2)**2
    return round(R * 2 * atan2(sqrt(a), sqrt(1 - a)), 1)
