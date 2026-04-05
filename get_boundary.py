import sys
import json
import asyncio
import requests
import osmnx as ox
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import shape, Point, MultiPolygon, Polygon

from prisma import Json
from db import db


HEADERS = {"User-Agent": "boundary-finder/1.0"}


def cache_key(city_name):
    """Normalize city name to a consistent cache key."""
    return city_name.strip().lower()


async def find_in_cache(city_name):
    """Search boundary DB by key or by matching the resolved name."""
    key = cache_key(city_name)
    entry = await db.boundary.find_unique(where={"key": key})
    if entry:
        return {"name": entry.name, "coords": entry.coords}
    entry = await db.boundary.find_first(where={"name": {"equals": key, "mode": "insensitive"}})
    if entry:
        return {"name": entry.name, "coords": entry.coords}
    return None


async def save_to_cache(city_name, resolved_name, coords):
    """Save boundary under both the query key and the resolved name key."""
    coords_clean = json.loads(json.dumps(coords, default=_serialize))
    key1 = cache_key(city_name)
    key2 = cache_key(resolved_name)
    await db.boundary.upsert(
        where={"key": key1},
        data={"create": {"key": key1, "name": resolved_name, "coords": Json(coords_clean)},
              "update": {"name": resolved_name, "coords": Json(coords_clean)}},
    )
    if key1 != key2:
        await db.boundary.upsert(
            where={"key": key2},
            data={"create": {"key": key2, "name": resolved_name, "coords": Json(coords_clean)},
                  "update": {"name": resolved_name, "coords": Json(coords_clean)}},
        )


def _serialize(obj):
    """JSON serializer for numpy/tuple types in coords."""
    if hasattr(obj, 'tolist'):
        return obj.tolist()
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def coords_to_polygon(coords):
    """Reconstruct a Shapely polygon from cached coordinate rings."""
    polys = [Polygon(ring) for ring in coords]
    if len(polys) == 1:
        return polys[0]
    return MultiPolygon(polys)


def search_nominatim(city_name):
    """Search Nominatim for places matching city_name."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": city_name,
        "format": "json",
        "limit": 10,
        "addressdetails": 1,
    }
    resp = requests.get(url, params=params, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def get_address_relations(osm_type, osm_id):
    """Use Nominatim details API to get the address hierarchy, extract boundary:administrative relations."""
    osm_type_char = osm_type[0].upper()
    url = "https://nominatim.openstreetmap.org/details"
    params = {
        "osmtype": osm_type_char,
        "osmid": osm_id,
        "format": "json",
        "addressdetails": 1,
    }
    resp = requests.get(url, params=params, headers=HEADERS)
    resp.raise_for_status()
    details = resp.json()

    address_parts = details.get("address", [])
    relations = []

    for part in address_parts:
        if part.get("osm_type") != "R":
            continue
        if part.get("type") != "administrative" or part.get("class") != "boundary":
            continue

        relations.append({
            "relation_id": part["osm_id"],
            "local_name": part.get("localname", "?"),
            "admin_level": part.get("admin_level", "?"),
            "rank_address": part.get("rank_address", "?"),
        })

    return relations


def fetch_polygon_from_osm_fr(relation_id):
    """Fetch GeoJSON polygon from polygons.openstreetmap.fr for a given relation ID."""
    url = f"https://polygons.openstreetmap.fr/get_geojson.py?id={relation_id}&params=0"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    geojson = resp.json()
    polygon = shape(geojson)
    return polygon


def check_coordinate(polygon, coord, plot_ax=None):
    """Check if a coordinate (lat, lon) is inside the polygon. Mark it on plot if provided."""
    lat, lon = coord
    point = Point(lon, lat)
    if polygon.contains(point):
        print(f"Coordinate ({lat}, {lon}) is inside the boundary.")
        if plot_ax:
            plot_ax.plot(lon, lat, "ro", markersize=10, zorder=5, label=f"({lat}, {lon})")
            plot_ax.legend()
        return True
    else:
        print(f"Coordinate ({lat}, {lon}) is out of bounds.")
        return False


async def get_boundary(city_name, plot=False, coord=None):
    """Find administrative boundary coordinates for a given city/region.

    Lookup order:
        1. Database cache — returns instantly if previously searched.
        2. OSMnx direct geocode — works when OSM has a polygon for the place.
        3. Nominatim fallback — searches Nominatim, shows the address hierarchy's
           boundary:administrative relations, lets the user pick one, then fetches
           the polygon from polygons.openstreetmap.fr.

    Results are cached to the database so subsequent calls for the same
    city_name skip all network requests.
    """
    cached = await find_in_cache(city_name)
    if cached:
        print(f"Loaded boundary from cache for: {cached['name']}")
        coords = [list(map(tuple, ring)) for ring in cached["coords"]]
        polygon = coords_to_polygon(coords)
        if coord:
            check_coordinate(polygon, coord)
        if plot:
            gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
            plot_boundary(gdf, polygon, cached["name"], coord=coord)
        return coords

    # First try direct geocode to GeoDataFrame (works if OSM has a polygon)
    try:
        gdf = ox.geocode_to_gdf(city_name)
        polygon = gdf.geometry.iloc[0]
        if polygon.geom_type in ("Polygon", "MultiPolygon"):
            display_name = gdf.iloc[0].get("display_name", city_name)
            print(f"Found boundary for: {display_name}")
            coords = extract_coords(polygon)
            await save_to_cache(city_name, display_name, coords)
            print(f"Cached boundary for '{city_name}'.")
            if coord:
                check_coordinate(polygon, coord)
            if plot:
                plot_boundary(gdf, polygon, city_name, coord=coord)
            return coords
    except Exception:
        pass

    # No direct polygon found — search Nominatim and find administrative relations
    print(f"No direct polygon boundary found for '{city_name}'.")
    print("Searching Nominatim for suggestions...\n")

    results = search_nominatim(city_name)
    if not results:
        print("No results found. Try a more specific name (e.g. 'Vapi, Gujarat, India').")
        return None

    top = results[0]
    print(f"Top result: {top['display_name']}")
    print(f"Fetching address hierarchy from Nominatim details...\n")

    relations = get_address_relations(top["osm_type"], top["osm_id"])

    if not relations:
        print("No boundary:administrative relations found in address hierarchy.")
        return None

    for i, rel in enumerate(relations):
        print(f"  [{i + 1}] {rel['local_name']}")
        print(f"      admin_level: {rel['admin_level']}, relation: {rel['relation_id']}")

    print(f"\n  [0] Cancel")
    choice = input("\nSelect a boundary to use: ").strip()

    if not choice.isdigit() or int(choice) == 0 or int(choice) > len(relations):
        print("Cancelled.")
        return None

    selected = relations[int(choice) - 1]
    relation_id = selected["relation_id"]

    cached = await find_in_cache(selected["local_name"])
    if cached:
        print(f"Loaded boundary from cache for: {cached['name']}")
        coords = [list(map(tuple, ring)) for ring in cached["coords"]]
        polygon = coords_to_polygon(coords)
        await save_to_cache(city_name, cached["name"], coords)
        if coord:
            check_coordinate(polygon, coord)
        if plot:
            gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
            plot_boundary(gdf, polygon, cached["name"], coord=coord)
        return coords

    osm_id_str = f"R{relation_id}"
    print(f"\nTrying OSMnx direct geocode for {osm_id_str}...")
    try:
        gdf = ox.geocode_to_gdf(osm_id_str, by_osmid=True)
        polygon = gdf.geometry.iloc[0]
        if polygon.geom_type in ("Polygon", "MultiPolygon"):
            print(f"Found boundary via OSMnx for: {selected['local_name']}")
            coords = extract_coords(polygon)
            await save_to_cache(city_name, selected["local_name"], coords)
            print(f"Cached boundary for '{city_name}'.")
            if coord:
                check_coordinate(polygon, coord)
            if plot:
                plot_boundary(gdf, polygon, selected["local_name"], coord=coord)
            return coords
    except Exception:
        print(f"OSMnx geocode failed for {osm_id_str}, falling back to polygons.openstreetmap.fr...")

    print(f"Fetching polygon for relation {relation_id} from polygons.openstreetmap.fr...")
    try:
        polygon = fetch_polygon_from_osm_fr(relation_id)
        gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
        print(f"Found boundary for: {selected['local_name']}")
        coords = extract_coords(polygon)
        await save_to_cache(city_name, selected["local_name"], coords)
        print(f"Cached boundary for '{city_name}'.")
        if coord:
            check_coordinate(polygon, coord)
        if plot:
            plot_boundary(gdf, polygon, selected["local_name"], coord=coord)
        return coords
    except Exception as e:
        print(f"Could not fetch polygon for relation {relation_id}: {e}")
        return None


def extract_coords(polygon):
    """Extract boundary coordinates as list of (lon, lat) tuples."""
    coords = []
    if polygon.geom_type == "MultiPolygon":
        for poly in polygon.geoms:
            coords.append(list(poly.exterior.coords))
    else:
        coords.append(list(polygon.exterior.coords))

    total_pts = sum(len(c) for c in coords)
    print(f"Boundary points: {total_pts}")
    return coords


def plot_boundary(gdf, polygon, title, coord=None):
    """Plot the boundary polygon, optionally marking a coordinate."""
    fig, ax = plt.subplots(figsize=(10, 10))
    gdf.plot(ax=ax, edgecolor="blue", facecolor="lightblue", alpha=0.5)

    if polygon.geom_type == "MultiPolygon":
        for poly in polygon.geoms:
            x, y = poly.exterior.xy
            ax.plot(x, y, "b-o", markersize=1)
    else:
        x, y = polygon.exterior.xy
        ax.plot(x, y, "b-o", markersize=1)

    if coord:
        lat, lon = coord
        point = Point(lon, lat)
        if polygon.contains(point):
            ax.plot(lon, lat, "ro", markersize=10, zorder=5, label=f"({lat}, {lon})")
            ax.legend()

    ax.set_title(title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    plt.tight_layout()
    filename = "boundary_plot.png"
    plt.savefig(filename, dpi=150)
    print(f"Plot saved to {filename}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_boundary.py <city_name> [yes|no] [lat,lon]")
        print("  city_name: Name of city/region to find boundary for")
        print("  plot:      'yes' to plot the boundary (default: no)")
        print("  lat,lon:   Optional coordinate to check (e.g. 20.3893,72.9106)")
        sys.exit(1)

    city_name = sys.argv[1]
    plot = len(sys.argv) >= 3 and sys.argv[2].lower() == "yes"

    coord = None
    if len(sys.argv) >= 4:
        parts = sys.argv[3].split(",")
        coord = (float(parts[0]), float(parts[1]))

    async def main():
        await db.connect()
        try:
            coords = await get_boundary(city_name, plot=plot, coord=coord)
            if coords:
                for i, ring in enumerate(coords):
                    print(f"\nRing {i + 1} ({len(ring)} points), first 5:")
                    for lon, lat in ring[:5]:
                        print(f"  lat: {lat:.6f}, lon: {lon:.6f}")
        finally:
            await db.disconnect()

    asyncio.run(main())
