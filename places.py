"""
Overpass API (OpenStreetMap) — helyek keresése kategória szerint.
Ingyenes, nincs API kulcs, nincs billing szükséges.
Google Maps link a koordinátákból épül fel (API kulcs nélkül).
"""
from __future__ import annotations

import httpx

RADIUS_M = 20_000  # 20 km

_OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
_HEADERS = {"User-Agent": "ConvoyLocator/2.0 (truck escort app)"}

# OSM tag szűrők kategóriánként
# osm: Overpass QL filter string
# name_filter: opcionális névszűrés (pl. MOL)
CATEGORIES: dict[str, dict] = {
    "combustibil": {"osm": '["amenity"="fuel"]',                                  "emoji": "⛽", "label": "Combustibil"},
    "mancare":     {"osm": '["amenity"="restaurant"]',                            "emoji": "🍽", "label": "Restaurant / Mâncare"},
    "fastfood":    {"osm": '["amenity"="fast_food"]',                             "emoji": "🍔", "label": "Fast Food"},
    "parcare_tir": {"osm": '["amenity"~"parking|truck_stop|rest_area"]["hgv"!="no"]', "emoji": "🅿️", "label": "Parcare TIR"},
    "mol":         {"osm": '["amenity"="fuel"]',           "name_filter": "mol",  "emoji": "🔴", "label": "Benzinărie MOL"},
    "service":     {"osm": '["shop"="car_repair"]',                               "emoji": "🔧", "label": "Service auto"},
    "hotel":       {"osm": '["tourism"~"hotel|motel|guest_house"]',               "emoji": "🛏", "label": "Hotel / Cazare"},
    "cafenea":     {"osm": '["amenity"="cafe"]',                                  "emoji": "☕", "label": "Cafenea"},
    "supermarket": {"osm": '["shop"="supermarket"]',                              "emoji": "🛒", "label": "Supermarket"},
    "vulcanizare": {"osm": '["shop"~"tyres|car_repair"]["name"~"vulcan|gumi|tyre",i]', "emoji": "🔩", "label": "Vulcanizare"},
    "atm":         {"osm": '["amenity"="atm"]',                                   "emoji": "💶", "label": "ATM / Bancă"},
    "spital":      {"osm": '["amenity"~"hospital|clinic"]',                       "emoji": "🏥", "label": "Spital / Urgențe"},
    "wc":          {"osm": '["amenity"="toilets"]',                               "emoji": "🚻", "label": "WC"},
    "pekseg":      {"osm": '["shop"="bakery"]',                                   "emoji": "🥐", "label": "Pékség / Bakery"},
}

_FAST_FOOD_BRANDS = {"mcdonald", "kfc", "burger king", "subway", "pizza hut", "domino", "hesburger"}


def _overpass_get(lat: float, lng: float, osm_filter: str, limit: int = 20) -> list[dict]:
    """Overpass API hívás — visszaadja a helyeket névvel, koordinátával, Maps linkkel.
    Automatikusan próbálja a mirror szervereket ha az első nem válaszol.
    """
    query = (
        f"[out:json][timeout:20];\n"
        f"(\n"
        f"  node{osm_filter}(around:{RADIUS_M},{lat},{lng});\n"
        f"  way{osm_filter}(around:{RADIUS_M},{lat},{lng});\n"
        f");\n"
        f"out center {limit};"
    )
    last_err: Exception | None = None
    for mirror in _OVERPASS_MIRRORS:
        try:
            resp = httpx.post(mirror, data={"data": query}, headers=_HEADERS, timeout=25)
            if resp.status_code == 200:
                break
            last_err = RuntimeError(f"Overpass {mirror} returned {resp.status_code}")
        except Exception as e:
            last_err = e
    else:
        raise RuntimeError(f"Overpass API nem érhető el: {last_err}")
    resp.raise_for_status()

    results = []
    for el in resp.json().get("elements", []):
        if el["type"] == "node":
            elat, elng = el["lat"], el["lon"]
        elif "center" in el:
            elat, elng = el["center"]["lat"], el["center"]["lon"]
        else:
            continue
        tags = el.get("tags", {})
        name = (
            tags.get("name:hu")
            or tags.get("name:ro")
            or tags.get("name")
            or tags.get("brand")
            or "?"
        )
        results.append({
            "name":         name,
            "address":      _fmt_addr(tags),
            "rating":       None,
            "maps_url":     f"https://maps.google.com/?q={elat},{elng}",
            "distance_km":  _haversine(lat, lng, elat, elng),
            "lat":          elat,
            "lng":          elng,
        })
    results.sort(key=lambda x: x["distance_km"])
    return results


def _fmt_addr(tags: dict) -> str:
    street = tags.get("addr:street", "")
    num    = tags.get("addr:housenumber", "")
    city   = tags.get("addr:city", "")
    parts  = []
    if street:
        parts.append(f"{street} {num}".strip())
    if city:
        parts.append(city)
    return ", ".join(parts)


def search(lat: float, lng: float, category: str, lang: str = "hu") -> list[dict]:
    """Top 5 hely egy kategóriában, 20 km-es körzetben."""
    cat = CATEGORIES.get(category)
    if not cat:
        return []
    results = _overpass_get(lat, lng, cat["osm"])
    if "name_filter" in cat:
        needle = cat["name_filter"].lower()
        results = [r for r in results if needle in r["name"].lower()]
    return results[:5]


def search_fastfood(lat: float, lng: float, lang: str = "hu") -> dict:
    """Fast food: márkák és egyéb gyorsételek külön listában."""
    results = _overpass_get(lat, lng, '["amenity"="fast_food"]')
    brands     = [r for r in results if any(b in r["name"].lower() for b in _FAST_FOOD_BRANDS)]
    brand_names = {r["name"] for r in brands}
    others     = [r for r in results if r["name"] not in brand_names]
    return {"brands": brands[:4], "others": others[:4]}


def _search_raw(lat: float, lng: float, category: str, lang: str, n: int = 10) -> list[dict]:
    """Mint search(), de lat/lng-t is tartalmaz a klaszterezéshez."""
    cat = CATEGORIES.get(category)
    if not cat:
        return []
    results = _overpass_get(lat, lng, cat["osm"], limit=n)
    if "name_filter" in cat:
        needle = cat["name_filter"].lower()
        results = [r for r in results if needle in r["name"].lower()]
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
    lat: float, lng: float, lang: str = "hu", cluster_km: float = 2.0
) -> list[dict]:
    """
    Top 3 Best Stop klaszter: üzemanyag + étel + parkoló együtt.
    cluster_km: ételt/parkolót ennyire keressük az üzemanyag mellé.
    """
    fuels = _search_raw(lat, lng, "combustibil", lang, n=10)
    foods = _search_raw(lat, lng, "mancare",      lang, n=10)
    parks = _search_raw(lat, lng, "parcare_tir",  lang, n=10)

    clusters = []
    for fuel in fuels:
        food    = _nearest_within(fuel, foods, cluster_km)
        parking = _nearest_within(fuel, parks, cluster_km)

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
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return round(R * 2 * atan2(sqrt(a), sqrt(1 - a)), 1)
