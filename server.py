from contextlib import asynccontextmanager
import base64
import hashlib
import hmac
import json as json_mod
import os

import numpy as np
import requests
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from scipy.spatial import Voronoi
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from prisma import Json
from db import db
from get_boundary import (
    find_in_cache, save_to_cache,
    search_nominatim, get_address_relations,
    fetch_polygon_from_osm_fr, extract_coords,
)
from get_landmarks import fetch_landmarks

import osmnx as ox

SECRET_KEY = os.environ.get("SECRET_KEY", "connekt-default-secret-change-me")
PASSWORD_SALT = os.environ.get("PASSWORD_SALT", "connekt-salt")


def hash_password(password: str) -> str:
    salted = f"{PASSWORD_SALT}:{password}"
    return hashlib.sha256(salted.encode()).hexdigest()


def create_token(user_id: int, username: str, role: str) -> str:
    payload = json_mod.dumps({"id": user_id, "username": username, "role": role})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        payload_b64, sig = token.rsplit(".", 1)
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json_mod.loads(base64.urlsafe_b64decode(payload_b64))
        return payload
    except Exception:
        return None


def get_current_user(request: Request) -> dict | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return verify_token(auth[7:])


async def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def require_admin(request: Request) -> dict:
    user = await require_user(request)
    if user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(lifespan=lifespan)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


REACT_DIST = Path(__file__).parent / "frontend" / "dist"


@app.get("/")
async def index():
    react_index = REACT_DIST / "index.html"
    # if react_index.exists():
    return FileResponse(str(react_index))
    # return FileResponse("index.html")


@app.post("/api/register")
async def api_register(request: Request):
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not username or not password:
        return JSONResponse({"error": "username and password are required"}, status_code=400)

    existing = await db.user.find_unique(where={"username": username})
    if existing:
        return JSONResponse({"error": "Username already taken"}, status_code=400)

    hashed = hash_password(password)
    user = await db.user.create(data={
        "username": username,
        "password": hashed,
        "role": "NORMAL",
    })
    return {"user": {"id": user.id, "username": user.username, "role": user.role}}


@app.post("/api/login")
async def api_login(request: Request):
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not username or not password:
        return JSONResponse({"error": "username and password are required"}, status_code=400)

    user = await db.user.find_unique(where={"username": username})
    if not user or user.password != hash_password(password):
        return JSONResponse({"error": "Invalid username or password"}, status_code=401)

    token = create_token(user.id, user.username, user.role)
    return {"user": {"id": user.id, "username": user.username, "role": user.role}, "token": token}


@app.get("/api/me")
async def api_me(request: Request):
    user = await require_user(request)
    return {"user": user}


@app.post("/api/search")
async def api_search(request: Request):
    """Search for a city. Always return nominatim suggestions so the user
    can pick the correct place (OSMnx geocode can match the wrong region)."""
    body = await request.json()
    city_name = body.get("city_name", "").strip()
    if not city_name:
        return JSONResponse({"error": "city_name is required"}, status_code=400)

    cached = await find_in_cache(city_name)
    if cached:
        coords = [list(map(list, ring)) for ring in cached["coords"]]
        return {"boundary": coords, "name": cached["name"]}

    results = search_nominatim(city_name)
    suggestions = [
        {
            "display_name": r["display_name"],
            "osm_type": r["osm_type"],
            "osm_id": r["osm_id"],
            "lat": r["lat"],
            "lon": r["lon"],
        }
        for r in results
    ]
    return {"suggestions": suggestions}


@app.post("/api/boundary")
async def api_boundary(request: Request):
    """Fetch boundary for a selected nominatim result via its address relations."""
    data = await request.json()
    osm_type = data.get("osm_type", "")
    osm_id = data.get("osm_id", "")
    display_name = data.get("display_name", "")

    if not osm_type or not osm_id:
        return JSONResponse({"error": "osm_type and osm_id are required"}, status_code=400)

    cached = await find_in_cache(display_name)
    if cached:
        coords = [list(map(list, ring)) for ring in cached["coords"]]
        return {"boundary": coords, "name": cached["name"]}

    relations = get_address_relations(osm_type, osm_id)

    for rel in relations:
        relation_id = rel["relation_id"]
        local_name = rel["local_name"]

        cached = await find_in_cache(local_name)
        if cached:
            coords = [list(map(list, ring)) for ring in cached["coords"]]
            await save_to_cache(display_name, cached["name"], coords)
            return {"boundary": coords, "name": cached["name"]}

        osm_id_str = f"R{relation_id}"
        try:
            gdf = ox.geocode_to_gdf(osm_id_str, by_osmid=True)
            polygon = gdf.geometry.iloc[0]
            if polygon.geom_type in ("Polygon", "MultiPolygon"):
                coords = extract_coords(polygon)
                await save_to_cache(display_name, local_name, coords)
                coords = [list(map(list, ring)) for ring in coords]
                return {"boundary": coords, "name": local_name}
        except Exception:
            pass

        try:
            polygon = fetch_polygon_from_osm_fr(relation_id)
            coords = extract_coords(polygon)
            await save_to_cache(display_name, local_name, coords)
            coords = [list(map(list, ring)) for ring in coords]
            return {"boundary": coords, "name": local_name}
        except Exception:
            continue

    return JSONResponse({"error": "No boundary polygon found for this place."}, status_code=404)


@app.post("/api/landmarks")
async def api_landmarks(request: Request):
    """Fetch popular landmarks near a given lat/lon."""
    data = await request.json()
    lat = data.get("lat")
    lon = data.get("lon")
    radius = data.get("radius", 10000)

    if lat is None or lon is None:
        return JSONResponse({"error": "lat and lon are required"}, status_code=400)

    landmarks = fetch_landmarks(float(lat), float(lon), int(radius))
    return {"landmarks": landmarks}


OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


def _overpass_nearest_poi(lat, lon, radius=50):
    """Find the nearest named POI via Overpass within radius meters."""
    query = f"""
    [out:json][timeout:5];
    (
      node["name"]["tourism"](around:{radius},{lat},{lon});
      node["name"]["historic"](around:{radius},{lat},{lon});
      node["name"]["amenity"](around:{radius},{lat},{lon});
      node["name"]["leisure"](around:{radius},{lat},{lon});
      node["name"]["shop"](around:{radius},{lat},{lon});
      node["name"]["building"](around:{radius},{lat},{lon});
      way["name"]["tourism"](around:{radius},{lat},{lon});
      way["name"]["historic"](around:{radius},{lat},{lon});
      way["name"]["amenity"](around:{radius},{lat},{lon});
      way["name"]["leisure"](around:{radius},{lat},{lon});
    );
    out tags center 5;
    """
    headers = {"User-Agent": "boundary-finder/1.0"}
    for url in OVERPASS_URLS:
        try:
            resp = requests.post(url, data={"data": query}, headers=headers, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            elements = data.get("elements", [])
            if elements:
                for el in elements:
                    name = el.get("tags", {}).get("name")
                    if name:
                        return name
            return None
        except Exception:
            continue
    return None


@app.post("/api/reverse-geocode")
async def api_reverse_geocode(request: Request):
    """Reverse geocode a lat/lon to find the nearest named place/POI."""
    data = await request.json()
    lat = data.get("lat")
    lon = data.get("lon")

    if lat is None or lon is None:
        return JSONResponse({"error": "lat and lon are required"}, status_code=400)

    name = _overpass_nearest_poi(lat, lon)
    if name:
        return {"name": name}

    headers = {"User-Agent": "boundary-finder/1.0"}
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat, "lon": lon, "format": "json",
            "zoom": 18, "namedetails": 1,
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        name = result.get("namedetails", {}).get("name") or result.get("name", "")
        return {"name": name}
    except Exception as e:
        return {"name": "", "error": str(e)}


@app.post("/api/saved-landmarks")
async def api_get_saved_landmarks(request: Request):
    """Load saved landmarks for a boundary name.
    version='base' returns base landmarks, version='user' returns user's landmarks."""
    body = await request.json()
    boundary_name = body.get("boundary_name", "").strip().lower()
    version = body.get("version", "base")
    if not boundary_name:
        return JSONResponse({"error": "boundary_name is required"}, status_code=400)

    if version == "user":
        user = await require_user(request)
        # Admin can view another user's landmarks via user_id param
        target_user_id = body.get("user_id", user["id"])
        if target_user_id != user["id"] and user["role"] != "ADMIN":
            return JSONResponse({"error": "Cannot view other users' landmarks"}, status_code=403)
        rows = await db.landmark.find_many(where={
            "boundary_name": boundary_name,
            "user_id": int(target_user_id),
            "is_base": False,
        })
    else:
        rows = await db.landmark.find_many(where={
            "boundary_name": boundary_name,
            "is_base": True,
        })

    landmarks = [{"id": r.id, "name": r.name, "lat": r.lat, "lon": r.lon} for r in rows]
    return {"landmarks": landmarks}


@app.post("/api/save-landmarks")
async def api_save_landmarks(request: Request):
    """Save landmarks for a boundary. Normal users save their own version.
    Admins can save as base with as_base=true."""
    user = await require_user(request)
    data = await request.json()
    boundary_name = data.get("boundary_name", "").strip().lower()
    landmarks = data.get("landmarks", [])
    as_base = data.get("as_base", False)

    if not boundary_name:
        return JSONResponse({"error": "boundary_name is required"}, status_code=400)

    if as_base:
        if user["role"] != "ADMIN":
            return JSONResponse({"error": "Admin access required to save as base"}, status_code=403)
        await db.landmark.delete_many(where={"boundary_name": boundary_name, "is_base": True})
        for lm in landmarks:
            await db.landmark.create(data={
                "boundary_name": boundary_name,
                "name": lm.get("name", ""),
                "lat": float(lm["lat"]),
                "lon": float(lm["lon"]),
                "is_base": True,
            })
        return {"ok": True, "count": len(landmarks)}
    else:
        await db.landmark.delete_many(where={
            "boundary_name": boundary_name,
            "user_id": user["id"],
            "is_base": False,
        })
        landmark_ids = []
        for lm in landmarks:
            row = await db.landmark.create(data={
                "boundary_name": boundary_name,
                "name": lm.get("name", ""),
                "lat": float(lm["lat"]),
                "lon": float(lm["lon"]),
                "is_base": False,
                "user_id": user["id"],
            })
            landmark_ids.append(row.id)
        return {"ok": True, "count": len(landmarks), "landmark_ids": landmark_ids}


@app.post("/api/nested-boundaries")
async def api_get_nested_boundaries(request: Request):
    """Load all nested boundaries for a parent boundary."""
    body = await request.json()
    parent_name = body.get("parent_name", "").strip().lower()
    if not parent_name:
        return JSONResponse({"error": "parent_name is required"}, status_code=400)

    rows = await db.nestedboundary.find_many(where={"parent_name": parent_name})
    children = {r.child_name: r.coords for r in rows}
    return {"nested_boundaries": children}


@app.post("/api/save-nested-boundary")
async def api_save_nested_boundary(request: Request):
    """Save or create a nested boundary under a parent. Admin only."""
    await require_admin(request)
    data = await request.json()
    parent_name = data.get("parent_name", "").strip().lower()
    child_name = data.get("child_name", "").strip()
    coords = data.get("coords", [])

    if not parent_name or not child_name:
        return JSONResponse({"error": "parent_name and child_name are required"}, status_code=400)
    if len(coords) < 3:
        return JSONResponse({"error": "At least 3 boundary points are required"}, status_code=400)

    await db.nestedboundary.upsert(
        where={"parent_name_child_name": {"parent_name": parent_name, "child_name": child_name}},
        data={
            "create": {"parent_name": parent_name, "child_name": child_name, "coords": Json(coords)},
            "update": {"coords": Json(coords)},
        },
    )
    return {"ok": True, "child_name": child_name}


@app.post("/api/update-nested-boundary")
async def api_update_nested_boundary(request: Request):
    """Update coordinates of an existing nested boundary. Admin only."""
    await require_admin(request)
    data = await request.json()
    parent_name = data.get("parent_name", "").strip().lower()
    child_name = data.get("child_name", "").strip()
    coords = data.get("coords", [])

    if not parent_name or not child_name:
        return JSONResponse({"error": "parent_name and child_name are required"}, status_code=400)
    if len(coords) < 3:
        return JSONResponse({"error": "At least 3 boundary points are required"}, status_code=400)

    existing = await db.nestedboundary.find_unique(
        where={"parent_name_child_name": {"parent_name": parent_name, "child_name": child_name}}
    )
    if not existing:
        return JSONResponse({"error": "Nested boundary not found"}, status_code=404)

    await db.nestedboundary.update(
        where={"parent_name_child_name": {"parent_name": parent_name, "child_name": child_name}},
        data={"coords": Json(coords)},
    )
    return {"ok": True, "child_name": child_name}


@app.post("/api/delete-nested-boundary")
async def api_delete_nested_boundary(request: Request):
    """Delete a nested boundary. Admin only."""
    await require_admin(request)
    data = await request.json()
    parent_name = data.get("parent_name", "").strip().lower()
    child_name = data.get("child_name", "").strip()

    if not parent_name or not child_name:
        return JSONResponse({"error": "parent_name and child_name are required"}, status_code=400)

    existing = await db.nestedboundary.find_unique(
        where={"parent_name_child_name": {"parent_name": parent_name, "child_name": child_name}}
    )
    if not existing:
        return JSONResponse({"error": "Nested boundary not found"}, status_code=404)

    await db.nestedboundary.delete(
        where={"parent_name_child_name": {"parent_name": parent_name, "child_name": child_name}}
    )
    return {"ok": True}


@app.post("/api/admin/landmark-users")
async def api_admin_landmark_users(request: Request):
    """List users who have landmark versions for a boundary. Admin only."""
    await require_admin(request)
    body = await request.json()
    boundary_name = body.get("boundary_name", "").strip().lower()
    if not boundary_name:
        return JSONResponse({"error": "boundary_name is required"}, status_code=400)

    rows = await db.landmark.find_many(
        where={"boundary_name": boundary_name, "is_base": False},
        include={"user": True},
    )
    user_map = {}
    for r in rows:
        if r.user_id and r.user:
            if r.user_id not in user_map:
                user_map[r.user_id] = {"id": r.user_id, "username": r.user.username, "count": 0}
            user_map[r.user_id]["count"] += 1

    return {"users": list(user_map.values())}


@app.post("/api/admin/promote-base")
async def api_admin_promote_base(request: Request):
    """Replace all base landmarks with a copy of this user's set. Admin only."""
    await require_admin(request)
    body = await request.json()
    boundary_name = body.get("boundary_name", "").strip().lower()
    user_id = body.get("user_id")

    if not boundary_name or user_id is None:
        return JSONResponse({"error": "boundary_name and user_id are required"}, status_code=400)

    user_landmarks = await db.landmark.find_many(where={
        "boundary_name": boundary_name,
        "user_id": int(user_id),
        "is_base": False,
    })
    if not user_landmarks:
        return JSONResponse({"error": "No landmarks found for this user and boundary"}, status_code=404)

    await db.landmark.delete_many(where={"boundary_name": boundary_name, "is_base": True})
    for lm in user_landmarks:
        await db.landmark.create(data={
            "boundary_name": boundary_name,
            "name": lm.name,
            "lat": lm.lat,
            "lon": lm.lon,
            "is_base": True,
        })
    return {"ok": True, "count": len(user_landmarks)}


@app.post("/api/admin/promote-landmarks-to-base")
async def api_admin_promote_landmarks_to_base(request: Request):
    """Merge selected user landmarks into the base version (admin only).
    Named landmarks update an existing base row with the same name if one exists; otherwise a new base row is created.
    Unnamed landmarks are always added as new base rows."""
    await require_admin(request)
    body = await request.json()
    boundary_name = body.get("boundary_name", "").strip().lower()
    user_id = body.get("user_id")
    landmark_ids = body.get("landmark_ids", [])

    if not boundary_name or user_id is None:
        return JSONResponse({"error": "boundary_name and user_id are required"}, status_code=400)
    if not landmark_ids or not isinstance(landmark_ids, list):
        return JSONResponse({"error": "landmark_ids must be a non-empty list"}, status_code=400)

    uid = int(user_id)
    promoted = 0
    for raw_id in landmark_ids:
        try:
            lm_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        row = await db.landmark.find_unique(where={"id": lm_id})
        if not row:
            continue
        if (
            row.boundary_name != boundary_name
            or row.is_base
            or row.user_id != uid
        ):
            continue
        if row.name and row.name.strip():
            existing = await db.landmark.find_first(
                where={
                    "boundary_name": boundary_name,
                    "is_base": True,
                    "name": row.name,
                }
            )
            if existing:
                await db.landmark.update(
                    where={"id": existing.id},
                    data={"lat": row.lat, "lon": row.lon},
                )
            else:
                await db.landmark.create(
                    data={
                        "boundary_name": boundary_name,
                        "name": row.name,
                        "lat": row.lat,
                        "lon": row.lon,
                        "is_base": True,
                    }
                )
        else:
            await db.landmark.create(
                data={
                    "boundary_name": boundary_name,
                    "name": row.name,
                    "lat": row.lat,
                    "lon": row.lon,
                    "is_base": True,
                }
            )
        promoted += 1

    if promoted == 0:
        return JSONResponse(
            {"error": "No matching user landmarks were promoted"},
            status_code=404,
        )
    return {"ok": True, "promoted": promoted}


@app.post("/api/admin/update-landmark")
async def api_admin_update_landmark(request: Request):
    """Rename any landmark row for a boundary (base or per-user). Admin only."""
    await require_admin(request)
    body = await request.json()
    boundary_name = body.get("boundary_name", "").strip().lower()
    landmark_id = body.get("landmark_id")
    name = body.get("name")

    if not boundary_name or landmark_id is None:
        return JSONResponse(
            {"error": "boundary_name and landmark_id are required"},
            status_code=400,
        )
    if not isinstance(name, str):
        return JSONResponse({"error": "name must be a string"}, status_code=400)

    try:
        lid = int(landmark_id)
    except (TypeError, ValueError):
        return JSONResponse({"error": "Invalid landmark_id"}, status_code=400)

    row = await db.landmark.find_unique(where={"id": lid})
    if not row or row.boundary_name != boundary_name:
        return JSONResponse({"error": "Landmark not found"}, status_code=404)

    await db.landmark.update(where={"id": lid}, data={"name": name})
    return {"ok": True}


def compute_voronoi_cells(landmarks, boundary_coords):
    """Compute Voronoi cells for landmarks, clipped to the parent boundary."""
    if len(landmarks) < 2:
        return []

    shapely_polys = []
    for ring in boundary_coords:
        coords = [(pt[0], pt[1]) for pt in ring]
        if len(coords) >= 3:
            try:
                p = Polygon(coords)
                if p.is_valid:
                    shapely_polys.append(p)
            except Exception:
                pass
    if not shapely_polys:
        return []
    parent_poly = unary_union(shapely_polys)
    if parent_poly.is_empty:
        return []

    points = np.array([[lm["lon"], lm["lat"]] for lm in landmarks])

    bounds = parent_poly.bounds
    dx = (bounds[2] - bounds[0]) * 2
    dy = (bounds[3] - bounds[1]) * 2
    cx = (bounds[0] + bounds[2]) / 2
    cy = (bounds[1] + bounds[3]) / 2
    far_points = np.array([
        [cx - dx, cy - dy],
        [cx + dx, cy - dy],
        [cx + dx, cy + dy],
        [cx - dx, cy + dy],
    ])
    all_points = np.vstack([points, far_points])

    vor = Voronoi(all_points)

    results = []
    for i, lm in enumerate(landmarks):
        region_idx = vor.point_region[i]
        region = vor.regions[region_idx]

        if not region or -1 in region:
            continue

        vertices = [vor.vertices[v] for v in region]
        try:
            cell = Polygon(vertices)
            if not cell.is_valid:
                cell = cell.buffer(0)
            clipped = cell.intersection(parent_poly)
            if clipped.is_empty:
                continue

            def poly_coords(geom):
                if geom.geom_type == "Polygon":
                    return [[[c[1], c[0]] for c in geom.exterior.coords]]
                elif geom.geom_type == "MultiPolygon":
                    result = []
                    for p in geom.geoms:
                        result.append([[c[1], c[0]] for c in p.exterior.coords])
                    return result
                return []

            coords_out = poly_coords(clipped)
            if coords_out:
                results.append({
                    "name": lm.get("name", ""),
                    "lat": lm["lat"],
                    "lon": lm["lon"],
                    "polygon": coords_out,
                })
        except Exception:
            continue

    return results


async def find_containing_nested_boundary(landmarks, parent_name):
    """Find the nested boundary that contains all the given landmarks."""
    rows = await db.nestedboundary.find_many(where={"parent_name": parent_name})

    for row in rows:
        child_coords = row.coords
        ring = [(pt["lon"], pt["lat"]) for pt in child_coords]
        if len(ring) < 3:
            continue
        try:
            poly = Polygon(ring)
            if not poly.is_valid:
                poly = poly.buffer(0)

            all_inside = all(
                poly.contains(Point(lm["lon"], lm["lat"]))
                for lm in landmarks
            )
            if all_inside:
                return row.child_name, [ring + [ring[0]]]
        except Exception:
            continue

    return None, None


@app.post("/api/compute-voronoi")
async def api_compute_voronoi(request: Request):
    """Compute Voronoi polygons for landmarks, clipped to the nested boundary containing them."""
    data = await request.json()
    boundary_name = data.get("boundary_name", "").strip().lower()
    landmarks = data.get("landmarks", [])
    boundary_coords = data.get("boundary_coords", [])

    if not boundary_name:
        return JSONResponse({"error": "boundary_name is required"}, status_code=400)
    if len(landmarks) < 2:
        return JSONResponse({"error": "At least 2 landmarks are required for Voronoi"}, status_code=400)
    if not boundary_coords:
        return JSONResponse({"error": "boundary_coords are required"}, status_code=400)

    nested_name, nested_coords = await find_containing_nested_boundary(landmarks, boundary_name)
    clip_coords = nested_coords if nested_coords else boundary_coords

    cells = compute_voronoi_cells(landmarks, clip_coords)

    await db.voronoicell.delete_many(where={"boundary_name": boundary_name})
    for cell in cells:
        await db.voronoicell.create(data={
            "boundary_name": boundary_name,
            "name": cell.get("name", ""),
            "lat": float(cell["lat"]),
            "lon": float(cell["lon"]),
            "polygon": Json(cell["polygon"]),
        })

    return {"ok": True, "cells": cells, "clipped_to": nested_name or boundary_name}


@app.post("/api/voronoi")
async def api_get_voronoi(request: Request):
    """Load cached Voronoi cells for a boundary."""
    body = await request.json()
    boundary_name = body.get("boundary_name", "").strip().lower()
    if not boundary_name:
        return JSONResponse({"error": "boundary_name is required"}, status_code=400)

    rows = await db.voronoicell.find_many(where={"boundary_name": boundary_name})
    cells = [{"name": r.name, "lat": r.lat, "lon": r.lon, "polygon": r.polygon} for r in rows]
    return {"cells": cells}


# Serve React static assets if the build exists
if REACT_DIST.exists() and (REACT_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(REACT_DIST / "assets")), name="react-assets")


# Catch-all for SPA client-side routing (must be after all API routes)
@app.get("/{full_path:path}")
async def spa_catch_all(full_path: str):
    return FileResponse(str(REACT_DIST / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=5000, reload=True, reload_delay=1)
