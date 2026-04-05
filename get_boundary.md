# get_boundary.py

A command-line tool to find and cache administrative boundary coordinates for any city or region using OpenStreetMap data.

## Usage

```bash
python get_boundary.py <city_name> [yes|no] [lat,lon]
```

| Argument    | Required | Description                                          |
|-------------|----------|------------------------------------------------------|
| `city_name` | Yes      | Name of the city/region (e.g. `"Vapi, Gujarat, India"`) |
| `plot`      | No       | `yes` to save a boundary plot image (default: `no`)  |
| `lat,lon`   | No       | Coordinate to check against the boundary (e.g. `20.3893,72.9106`) |

### Examples

```bash
# Basic boundary lookup
python get_boundary.py "Surat, Gujarat, India"

# With plot
python get_boundary.py "Surat, Gujarat, India" yes

# With coordinate check and plot
python get_boundary.py "Surat, Gujarat, India" yes 21.1702,72.8311
```

## How It Works

The script resolves boundaries in three steps, stopping at the first success:

### Step 1 — Cache Lookup

Checks `boundary_cache.json` for a previously fetched result. The cache key is the lowercased, trimmed city name. If found, coordinates are loaded instantly with no network requests.

### Step 2 — OSMnx Direct Geocode

Calls `osmnx.geocode_to_gdf(city_name)` which queries Nominatim for a place with a polygon boundary. This works for most well-known cities, districts, states, and countries that have polygon geometries in OpenStreetMap.

### Step 3 — Nominatim Fallback (Interactive)

If no direct polygon exists (e.g. small towns that only have a point node in OSM):

1. **Search**: Queries the [Nominatim Search API](https://nominatim.openstreetmap.org/search) for matching places.
2. **Address Hierarchy**: Takes the top result and queries the [Nominatim Details API](https://nominatim.openstreetmap.org/details) to get its address hierarchy. Extracts all `boundary:administrative` relations (filtered by `osm_type=R`, `class=boundary`, `type=administrative`).
3. **User Selection**: Displays the relations with their `admin_level` and relation ID, prompting the user to pick one.
4. **Cache Check**: Checks the cache for the selected place's resolved name. If a previous search already fetched this boundary (even under a different query), it is returned from cache instantly.
5. **OSMnx Geocode**: Tries `osmnx.geocode_to_gdf("R<relation_id>", by_osmid=True)` to fetch the polygon directly via the selected relation's OSM ID.
6. **Polygon Fetch (fallback)**: If OSMnx fails, downloads the GeoJSON polygon from `polygons.openstreetmap.fr/get_geojson.py?id=<relation_id>&params=0` and converts it to a Shapely geometry.

After any successful fetch (Step 2 or 3), the result is saved to the cache.

## Coordinate Check

When a `lat,lon` coordinate is provided:

- **Inside boundary** — prints `"Coordinate (lat, lon) is inside the boundary."` and marks it as a red dot on the plot (if plotting is enabled).
- **Outside boundary** — prints `"Coordinate (lat, lon) is out of bounds."` The point is not drawn on the plot.

## Caching

Boundary results are stored in `boundary_cache.json` (same directory as the script). The file structure:

```json
{
  "surat, gujarat, india": {
    "name": "Surat, Gujarat, India",
    "coords": [
      [[lon, lat], [lon, lat], ...]
    ]
  }
}
```

- Cache key: lowercased and trimmed `city_name`
- **Dual-key storage**: Each result is saved under both the user's original query (e.g. `"mumbai"`) and the resolved place name (e.g. `"mumbai suburban district"`). This means searching `"mumbai"`, `"mumbai, maharashtra"`, or `"Mumbai Suburban District"` all hit the same cached entry after any one of them has been fetched.
- **Lookup**: First checks for an exact key match, then scans all entries comparing the resolved `name` field.
- To force a fresh fetch, delete the entry from the JSON file or delete the file entirely.

## Output Files

| File                  | Description                              |
|-----------------------|------------------------------------------|
| `boundary_cache.json` | JSON cache of previously fetched boundaries |
| `boundary_plot.png`   | Boundary plot image (when `plot=yes`)    |

## Functions

| Function | Description |
|----------|-------------|
| `get_boundary(city_name, plot, coord)` | Main entry point. Resolves boundary via cache/OSMnx/Nominatim fallback. Returns list of coordinate rings. |
| `search_nominatim(city_name)` | Queries Nominatim Search API for matching places. |
| `get_address_relations(osm_type, osm_id)` | Queries Nominatim Details API and extracts `boundary:administrative` relations from the address hierarchy. |
| `fetch_polygon_from_osm_fr(relation_id)` | Fetches GeoJSON polygon from `polygons.openstreetmap.fr` for a given OSM relation ID. |
| `check_coordinate(polygon, coord, plot_ax)` | Tests if a `(lat, lon)` point is inside a polygon using Shapely's `contains`. |
| `extract_coords(polygon)` | Extracts exterior ring coordinates from a Polygon or MultiPolygon. |
| `plot_boundary(gdf, polygon, title, coord)` | Plots the boundary and optionally marks a coordinate point. |
| `load_cache()` / `save_cache(cache)` | Read/write `boundary_cache.json`. |
| `find_in_cache(cache, city_name)` | Searches cache by exact key match, then by resolved place name. |
| `save_to_cache(cache, city_name, resolved_name, coords)` | Saves boundary under both the query key and the resolved name key. |
| `cache_key(city_name)` | Normalizes city name to a consistent lowercase cache key. |
| `coords_to_polygon(coords)` | Reconstructs a Shapely Polygon/MultiPolygon from cached coordinate rings. |

## Dependencies

- `osmnx`
- `geopandas`
- `matplotlib`
- `shapely`
- `requests`
