import requests

HEADERS = {"User-Agent": "boundary-finder/1.0"}
OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


def fetch_landmarks(lat, lon, radius_m=10000, limit=50):
    """Fetch popular landmarks near (lat, lon).

    Tries Overpass API first, falls back to Wikipedia geosearch API.

    Args:
        lat: Latitude of the city center.
        lon: Longitude of the city center.
        radius_m: Search radius in meters (default 10km).
        limit: Max number of landmarks to return.

    Returns:
        List of dicts with keys: name, lat, lon, type, category.
    """
    landmarks = _fetch_from_overpass(lat, lon, radius_m, limit)
    if not landmarks:
        landmarks = _fetch_from_wikipedia(lat, lon, radius_m, limit)
    return landmarks


def _fetch_from_overpass(lat, lon, radius_m, limit):
    """Try Overpass API for OSM landmarks."""
    query = f"""
    [out:json][timeout:10];
    (
      node["tourism"~"attraction|viewpoint|museum"](around:{radius_m},{lat},{lon});
      node["historic"~"monument|memorial|castle|fort"](around:{radius_m},{lat},{lon});
      node["amenity"="place_of_worship"]["name"](around:{radius_m},{lat},{lon});
      node["leisure"="park"]["name"](around:{radius_m},{lat},{lon});
    );
    out {limit};
    """

    data = None
    for url in OVERPASS_URLS:
        try:
            resp = requests.post(url, data={"data": query}, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception:
            continue

    if data is None:
        return []

    landmarks = []
    seen_names = set()

    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en")
        if not name:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        el_lat = el.get("lat") or el.get("center", {}).get("lat")
        el_lon = el.get("lon") or el.get("center", {}).get("lon")
        if not el_lat or not el_lon:
            continue

        category, ltype = _classify_osm(tags)

        landmarks.append({
            "name": name,
            "lat": el_lat,
            "lon": el_lon,
            "type": ltype,
            "category": category,
        })

    priority = {"attraction": 0, "historic": 1, "worship": 2, "park": 3}
    landmarks.sort(key=lambda x: priority.get(x["category"], 5))
    return landmarks[:limit]


def _fetch_from_wikipedia(lat, lon, radius_m, limit):
    """Fallback: use Wikipedia geosearch to find notable places nearby."""
    radius_m = min(radius_m, 10000)  # Wikipedia API caps at 10km
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "geosearch",
        "gscoord": f"{lat}|{lon}",
        "gsradius": radius_m,
        "gslimit": min(limit, 50),
        "format": "json",
    }

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    landmarks = []
    for place in data.get("query", {}).get("geosearch", []):
        landmarks.append({
            "name": place["title"],
            "lat": place["lat"],
            "lon": place["lon"],
            "type": "landmark",
            "category": "attraction",
        })

    return landmarks


def _classify_osm(tags):
    """Classify a landmark based on its OSM tags."""
    if tags.get("tourism") in ("attraction", "viewpoint", "museum", "artwork"):
        return "attraction", tags.get("tourism")
    if tags.get("historic"):
        return "historic", tags["historic"]
    if tags.get("amenity") == "place_of_worship":
        religion = tags.get("religion", "unknown")
        return "worship", religion
    if tags.get("leisure") == "park":
        return "park", "park"
    return "other", "other"


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python get_landmarks.py <lat> <lon> [radius_m]")
        sys.exit(1)

    lat = float(sys.argv[1])
    lon = float(sys.argv[2])
    radius = int(sys.argv[3]) if len(sys.argv) > 3 else 10000

    results = fetch_landmarks(lat, lon, radius)
    print(f"Found {len(results)} landmarks:\n")
    for lm in results:
        print(f"  [{lm['category']}] {lm['name']} ({lm['lat']:.5f}, {lm['lon']:.5f}) — {lm['type']}")
