"""
Wrapper Google Places API — Nearby Search.
Returneaza top 5 locatii dintr-o categorie, in raza de 20 km.
"""
from __future__ import annotations

import os
import httpx

RADIUS_M = 20_000  # 20 km

# Mapare categorie -> tip Google Places + keyword optional
CATEGORIES: dict[str, dict] = {
    "mancare":      {"type": "restaurant",   "keyword": None,             "emoji": "🍽",  "label": "Restaurant / Mancare"},
    "wc":           {"type": "gas_station",  "keyword": "toaleta",        "emoji": "🚻",  "label": "WC (benzinarie cu toaleta)"},
    "combustibil":  {"type": "gas_station",  "keyword": None,             "emoji": "⛽",  "label": "Combustibil"},
    "mol":          {"type": "gas_station",  "keyword": "MOL",            "emoji": "🔴",  "label": "Benzinarie MOL"},
    "supermarket":  {"type": "supermarket", "keyword": None,             "emoji": "🛒",  "label": "Supermarket"},
    "spital":       {"type": "hospital",    "keyword": None,             "emoji": "🏥",  "label": "Spital / Urgente"},
    "vulcanizare":  {"type": "car_repair",  "keyword": "vulcanizare",    "emoji": "🔩",  "label": "Vulcanizare"},
    "atm":          {"type": "atm",         "keyword": None,             "emoji": "💶",  "label": "ATM / Banca"},
    "cafenea":      {"type": "cafe",        "keyword": None,             "emoji": "☕",  "label": "Cafenea"},
    "parcare_tir":  {"type": "parking",      "keyword": "tir camion",     "emoji": "🅿️",  "label": "Parcare TIR"},
    "service":      {"type": "car_repair",   "keyword": None,             "emoji": "🔧",  "label": "Service auto"},
    "hotel":        {"type": "lodging",      "keyword": None,             "emoji": "🛏",  "label": "Hotel / Cazare"},
    "pekseg":       {"type": "bakery",       "keyword": "pékség bakery",  "emoji": "🥐",  "label": "Pékség / Bakery"},
}

_BASE = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"


def search(lat: float, lng: float, category: str, lang: str = "hu") -> list[dict]:
    """
    Returneaza lista de locatii (max 5).
    Fiecare element: {name, address, distance_km, maps_url, rating}
    """
    cat = CATEGORIES.get(category)
    if not cat:
        return []

    if category == "mol":
        return _search_mol(lat, lng, lang)

    params: dict = {
        "location": f"{lat},{lng}",
        "radius": RADIUS_M,
        "type": cat["type"],
        "language": lang,
        "key": os.environ["GOOGLE_PLACES_API_KEY"],
    }
    if cat["keyword"]:
        params["keyword"] = cat["keyword"]

    resp = httpx.get(_BASE, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for place in data.get("results", []):
        loc = place["geometry"]["location"]
        plat, plng = loc["lat"], loc["lng"]
        maps_url = f"https://maps.google.com/?q={plat},{plng}"
        results.append({
            "name": place.get("name", "?"),
            "address": place.get("vicinity", ""),
            "rating": place.get("rating"),
            "maps_url": maps_url,
            "distance_km": _haversine(lat, lng, plat, plng),
        })

    results.sort(key=lambda x: x["distance_km"])
    return results[:5]


def _search_mol(lat: float, lng: float, lang: str) -> list[dict]:
    """
    MOL-specifikus keresés: először keyword-del próbál, ha üres →
    broad gas_station keresés + névszűrés. Ez megbízhatóbban
    találja meg a közeli MOL kutakat.
    """
    key = os.environ["GOOGLE_PLACES_API_KEY"]

    def _fetch(keyword: str | None) -> list[dict]:
        params: dict = {
            "location": f"{lat},{lng}",
            "radius": RADIUS_M,
            "type": "gas_station",
            "language": lang,
            "key": key,
        }
        if keyword:
            params["keyword"] = keyword
        resp = httpx.get(_BASE, params=params, timeout=10)
        resp.raise_for_status()
        out = []
        for place in resp.json().get("results", []):
            loc = place["geometry"]["location"]
            plat, plng = loc["lat"], loc["lng"]
            out.append({
                "name":         place.get("name", "?"),
                "address":      place.get("vicinity", ""),
                "rating":       place.get("rating"),
                "maps_url":     f"https://maps.google.com/?q={plat},{plng}",
                "distance_km":  _haversine(lat, lng, plat, plng),
            })
        out.sort(key=lambda x: x["distance_km"])
        return [r for r in out if "mol" in r["name"].lower()]

    # 1. Próba: Places API keyword=MOL (gyors, de néha kihagyja)
    results = _fetch("MOL")

    # 2. Fallback: összes benzinkút lekérése + névszűrés
    if not results:
        results = _fetch(None)

    return results[:5]


_BRANDS = {"mcdonald", "kfc", "burger king", "subway", "pizza hut", "domino"}


def search_fastfood(lat: float, lng: float, lang: str = "hu") -> dict:
    """
    Returns {brands: [...], others: [...]}.
    2 API calls: brand-specific + general fast food.
    """
    key = os.environ["GOOGLE_PLACES_API_KEY"]

    def _fetch(keyword: str) -> list:
        r = httpx.get(
            _BASE,
            params={
                "location": f"{lat},{lng}",
                "radius": RADIUS_M,
                "type": "restaurant",
                "keyword": keyword,
                "language": lang,
                "key": key,
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("results", [])

    raw_brands  = _fetch("McDonald's KFC Burger King")
    raw_general = _fetch("gyorsétterem fast food")

    seen, combined = set(), []
    for place in raw_brands + raw_general:
        name = place.get("name", "")
        if name in seen:
            continue
        seen.add(name)
        loc = place["geometry"]["location"]
        plat, plng = loc["lat"], loc["lng"]
        combined.append({
            "name": name,
            "address": place.get("vicinity", ""),
            "rating": place.get("rating"),
            "maps_url": f"https://maps.google.com/?q={plat},{plng}",
            "distance_km": _haversine(lat, lng, plat, plng),
        })

    combined.sort(key=lambda x: x["distance_km"])
    brands = [p for p in combined if any(b in p["name"].lower() for b in _BRANDS)]
    brand_names = {p["name"] for p in brands}
    others = [p for p in combined if p["name"] not in brand_names]
    return {"brands": brands[:4], "others": others[:4]}


def _search_raw(lat: float, lng: float, category: str, lang: str, n: int = 10) -> list[dict]:
    """Like search() but returns lat/lng of each place for clustering."""
    cat = CATEGORIES.get(category)
    if not cat:
        return []
    params: dict = {
        "location": f"{lat},{lng}",
        "radius": RADIUS_M,
        "type": cat["type"],
        "language": lang,
        "key": os.environ["GOOGLE_PLACES_API_KEY"],
    }
    if cat["keyword"]:
        params["keyword"] = cat["keyword"]
    resp = httpx.get(_BASE, params=params, timeout=10)
    resp.raise_for_status()
    results = []
    for place in resp.json().get("results", []):
        loc = place["geometry"]["location"]
        plat, plng = loc["lat"], loc["lng"]
        results.append({
            "name":        place.get("name", "?"),
            "address":     place.get("vicinity", ""),
            "rating":      place.get("rating"),
            "maps_url":    f"https://maps.google.com/?q={plat},{plng}",
            "distance_km": _haversine(lat, lng, plat, plng),
            "lat": plat, "lng": plng,
        })
    results.sort(key=lambda x: x["distance_km"])
    return results[:n]


def _nearest_within(anchor: dict, candidates: list[dict], radius_km: float) -> dict | None:
    """Legközelebbi kandidát az anchor-tól radius_km-en belül."""
    best, best_d = None, float("inf")
    for c in candidates:
        d = _haversine(anchor["lat"], anchor["lng"], c["lat"], c["lng"])
        if d <= radius_km and d < best_d:
            best_d, best = d, {**c, "dist_to_anchor": d}
    return best


def search_best_stop(
    lat: float, lng: float, lang: str = "hu", cluster_km: float = 0.8
) -> list[dict]:
    """
    Top 3 'Best Stop' klaszter: üzemanyag + étel + parkoló együtt.
    cluster_km: mekkora körben keresünk ételt/parkolót az üzemanyag mellé.
    Visszatér: [{fuel, food, parking, score}, ...]
    """
    fuels  = _search_raw(lat, lng, "combustibil",  lang, n=10)
    foods  = _search_raw(lat, lng, "mancare",       lang, n=10)
    parks  = _search_raw(lat, lng, "parcare_tir",   lang, n=10)

    clusters = []
    for fuel in fuels:
        food    = _nearest_within(fuel, foods, cluster_km)
        parking = _nearest_within(fuel, parks, cluster_km)

        # Score: kisebb = jobb
        # Fő tényező: üzemanyag távolsága + büntetés ha hiányzik étel/parkoló
        score = fuel["distance_km"]
        score += (food["dist_to_anchor"]    * 0.2) if food    else 8.0
        score += (parking["dist_to_anchor"] * 0.2) if parking else 8.0

        clusters.append({
            "fuel":    fuel,
            "food":    food,
            "parking": parking,
            "score":   score,
        })

    clusters.sort(key=lambda x: x["score"])
    return clusters[:3]


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distanta in km intre doua coordonate GPS."""
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return round(R * 2 * atan2(sqrt(a), sqrt(1 - a)), 1)
