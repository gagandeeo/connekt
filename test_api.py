#!/usr/bin/env python3
"""API endpoint test script for Connekt.

Usage: python test_api.py
Server must be running at http://localhost:5000
"""

import requests
import sys

BASE = "http://localhost:5000"

# Colors
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"

passed = 0
failed = 0
total = 0

city_name = "Mumbai"
osm_id = "7964375"
lat = 19.162583946827276
lon = 72.86873706595648

def check(test_name, expected_code, resp):
    global passed, failed, total
    total += 1
    if resp.status_code == expected_code:
        print(f"{GREEN}PASS{NC} [{resp.status_code}] {test_name}")
        passed += 1
    else:
        print(f"{RED}FAIL{NC} [{resp.status_code}, expected {expected_code}] {test_name}")
        print(f"  Response: {resp.text}")
        failed += 1


def check_body(test_name, pattern, resp):
    global passed, failed, total
    total += 1
    if pattern in resp.text:
        print(f"{GREEN}PASS{NC} {test_name} (body contains '{pattern}')")
        passed += 1
    else:
        print(f"{RED}FAIL{NC} {test_name} (body missing '{pattern}')")
        print(f"  Response: {resp.text}")
        failed += 1


def post(endpoint, json=None, timeout=10):
    return requests.post(f"{BASE}{endpoint}", json=json or {}, timeout=timeout)


def section(title):
    print(f"\n{YELLOW}--- {title} ---{NC}")


print("==============================")
print(" Connekt API Test Suite")
print("==============================")

# --------------------------------------------------
# GET /
# --------------------------------------------------
section("GET /")

r = requests.get(f"{BASE}/", timeout=10)
check("GET / returns 200", 200, r)

# --------------------------------------------------
# POST /api/search
# --------------------------------------------------
section("POST /api/search")

r = post("/api/search", {})
check("search: empty city_name returns 400", 400, r)
check_body("search: error message present", "city_name is required", r)

r = post("/api/search", {"city_name": "   "})
check("search: whitespace-only city_name returns 400", 400, r)

r = post("/api/search", {"city_name": city_name}, timeout=30)
check("search: valid city returns 200", 200, r)
data = r.json()
if "boundary" in data or "suggestions" in data:
    total += 1
    passed += 1
    print(f"{GREEN}PASS{NC} search: response has boundary or suggestions")
else:
    total += 1
    failed += 1
    print(f"{RED}FAIL{NC} search: response missing both boundary and suggestions keys")
    print(f"  Response: {r.text}")

# --------------------------------------------------
# POST /api/boundary
# --------------------------------------------------
section("POST /api/boundary")

r = post("/api/boundary", {})
check("boundary: missing fields returns 400", 400, r)
check_body("boundary: error mentions required fields", "osm_type and osm_id are required", r)

r = post("/api/boundary", {"osm_type": "relation", "osm_id": osm_id, "display_name": "Nonexistent Place"}, timeout=30)
check("boundary: invalid osm_id returns 404", 404, r)

# --------------------------------------------------
# POST /api/landmarks
# --------------------------------------------------
section("POST /api/landmarks")

r = post("/api/landmarks", {})
check("landmarks: missing lat/lon returns 400", 400, r)
check_body("landmarks: error message present", "lat and lon are required", r)

r = post("/api/landmarks", {"lat": lat, "lon": lon}, timeout=30)
check("landmarks: valid lat/lon returns 200", 200, r)

# --------------------------------------------------
# POST /api/reverse-geocode
# --------------------------------------------------
section("POST /api/reverse-geocode")

r = post("/api/reverse-geocode", {})
check("reverse-geocode: missing lat/lon returns 400", 400, r)

r = post("/api/reverse-geocode", {"lat": lat, "lon": lon}, timeout=15)
check("reverse-geocode: valid lat/lon returns 200", 200, r)
check_body("reverse-geocode: response has name field", '"name"', r)

# --------------------------------------------------
# POST /api/saved-landmarks
# --------------------------------------------------
section("POST /api/saved-landmarks")

r = post("/api/saved-landmarks", {})
check("saved-landmarks: missing boundary_name returns 400", 400, r)

r = post("/api/saved-landmarks", {"boundary_name": "__test_boundary__"})
check("saved-landmarks: valid request returns 200", 200, r)
check_body("saved-landmarks: response has landmarks array", '"landmarks"', r)

# --------------------------------------------------
# POST /api/save-landmarks
# --------------------------------------------------
section("POST /api/save-landmarks")

r = post("/api/save-landmarks", {"landmarks": []})
check("save-landmarks: missing boundary_name returns 400", 400, r)

r = post("/api/save-landmarks", {
    "boundary_name": "__test_boundary__",
    "landmarks": [
        {"name": "Test Point A", "lat": 19.076, "lon": 72.877},
        {"name": "Test Point B", "lat": 19.080, "lon": 72.880},
    ],
})
check("save-landmarks: valid save returns 200", 200, r)
check_body("save-landmarks: response has ok:true", '"ok":true', r)
check_body("save-landmarks: count is 2", '"count":2', r)
check_body("save-landmarks: response includes landmark_ids array", '"landmark_ids"', r)

# Verify saved landmarks can be loaded back
r = post("/api/saved-landmarks", {"boundary_name": "__test_boundary__"})
check("save-landmarks: reload returns 200", 200, r)
check_body("save-landmarks: reload contains Test Point A", "Test Point A", r)
check_body("save-landmarks: reload contains Test Point B", "Test Point B", r)

# --------------------------------------------------
# POST /api/nested-boundaries
# --------------------------------------------------
section("POST /api/nested-boundaries")

r = post("/api/nested-boundaries", {})
check("nested-boundaries: missing parent_name returns 400", 400, r)

r = post("/api/nested-boundaries", {"parent_name": "__test_boundary__"})
check("nested-boundaries: valid request returns 200", 200, r)
check_body("nested-boundaries: response has nested_boundaries", '"nested_boundaries"', r)

# --------------------------------------------------
# POST /api/save-nested-boundary
# --------------------------------------------------
section("POST /api/save-nested-boundary")

r = post("/api/save-nested-boundary", {})
check("save-nested: missing fields returns 400", 400, r)

r = post("/api/save-nested-boundary", {
    "parent_name": "__test_boundary__",
    "child_name": "zone1",
    "coords": [{"lat": 19.0, "lon": 72.8}],
})
check("save-nested: <3 coords returns 400", 400, r)
check_body("save-nested: error mentions 3 points", "At least 3", r)

r = post("/api/save-nested-boundary", {
    "parent_name": "__test_boundary__",
    "child_name": "__test_zone__",
    "coords": [
        {"lat": 19.07, "lon": 72.87},
        {"lat": 19.08, "lon": 72.87},
        {"lat": 19.08, "lon": 72.88},
    ],
})
check("save-nested: valid save returns 200", 200, r)
check_body("save-nested: response has ok:true", '"ok":true', r)

# Verify it appears in list
r = post("/api/nested-boundaries", {"parent_name": "__test_boundary__"})
check("save-nested: appears in listing", 200, r)
check_body("save-nested: listing contains __test_zone__", "__test_zone__", r)

# --------------------------------------------------
# POST /api/update-nested-boundary
# --------------------------------------------------
section("POST /api/update-nested-boundary")

r = post("/api/update-nested-boundary", {})
check("update-nested: missing fields returns 400", 400, r)

r = post("/api/update-nested-boundary", {
    "parent_name": "__test_boundary__",
    "child_name": "__test_zone__",
    "coords": [{"lat": 1, "lon": 1}],
})
check("update-nested: <3 coords returns 400", 400, r)

r = post("/api/update-nested-boundary", {
    "parent_name": "__test_boundary__",
    "child_name": "__nonexistent__",
    "coords": [{"lat": 1, "lon": 1}, {"lat": 2, "lon": 2}, {"lat": 3, "lon": 3}],
})
check("update-nested: nonexistent returns 404", 404, r)

r = post("/api/update-nested-boundary", {
    "parent_name": "__test_boundary__",
    "child_name": "__test_zone__",
    "coords": [
        {"lat": 19.071, "lon": 72.871},
        {"lat": 19.081, "lon": 72.871},
        {"lat": 19.081, "lon": 72.881},
    ],
})
check("update-nested: valid update returns 200", 200, r)
check_body("update-nested: response has ok:true", '"ok":true', r)

# --------------------------------------------------
# POST /api/delete-nested-boundary
# --------------------------------------------------
section("POST /api/delete-nested-boundary")

r = post("/api/delete-nested-boundary", {})
check("delete-nested: missing fields returns 400", 400, r)

r = post("/api/delete-nested-boundary", {
    "parent_name": "__test_boundary__",
    "child_name": "__nonexistent__",
})
check("delete-nested: nonexistent returns 404", 404, r)

r = post("/api/delete-nested-boundary", {
    "parent_name": "__test_boundary__",
    "child_name": "__test_zone__",
})
check("delete-nested: valid delete returns 200", 200, r)
check_body("delete-nested: response has ok:true", '"ok":true', r)

# Verify it's gone
r = post("/api/nested-boundaries", {"parent_name": "__test_boundary__"})
total += 1
if "__test_zone__" not in r.text:
    passed += 1
    print(f"{GREEN}PASS{NC} delete-nested: zone removed from listing")
else:
    failed += 1
    print(f"{RED}FAIL{NC} delete-nested: zone still present after delete")

# --------------------------------------------------
# POST /api/compute-voronoi
# --------------------------------------------------
section("POST /api/compute-voronoi")

r = post("/api/compute-voronoi", {"landmarks": [], "boundary_coords": []})
check("compute-voronoi: missing boundary_name returns 400", 400, r)

r = post("/api/compute-voronoi", {
    "boundary_name": "__test_boundary__",
    "landmarks": [{"name": "A", "lat": 19.07, "lon": 72.87}],
    "boundary_coords": [[1, 2]],
})
check("compute-voronoi: <2 landmarks returns 400", 400, r)
check_body("compute-voronoi: error mentions 2 landmarks", "At least 2", r)

r = post("/api/compute-voronoi", {
    "boundary_name": "__test_boundary__",
    "landmarks": [
        {"name": "A", "lat": 19.07, "lon": 72.87},
        {"name": "B", "lat": 19.08, "lon": 72.88},
    ],
    "boundary_coords": [],
})
check("compute-voronoi: empty boundary_coords returns 400", 400, r)

r = post("/api/compute-voronoi", {
    "boundary_name": "__test_boundary__",
    "landmarks": [
        {"name": "A", "lat": 19.075, "lon": 72.875},
        {"name": "B", "lat": 19.078, "lon": 72.878},
    ],
    "boundary_coords": [
        [[72.87, 19.07], [72.88, 19.07], [72.875, 19.09], [72.87, 19.07]],
    ],
})
check("compute-voronoi: valid compute returns 200", 200, r)
check_body("compute-voronoi: response has cells", '"cells"', r)

# --------------------------------------------------
# POST /api/voronoi
# --------------------------------------------------
section("POST /api/voronoi")

r = post("/api/voronoi", {})
check("voronoi: missing boundary_name returns 400", 400, r)

r = post("/api/voronoi", {"boundary_name": "__test_boundary__"})
check("voronoi: valid request returns 200", 200, r)
check_body("voronoi: response has cells", '"cells"', r)

# --------------------------------------------------
# Cleanup test data
# --------------------------------------------------
section("Cleanup")

r = post("/api/save-landmarks", {"boundary_name": "__test_boundary__", "landmarks": []})
check("cleanup: clear test landmarks", 200, r)

# --------------------------------------------------
# Summary
# --------------------------------------------------
print()
print("==============================")
print(f" Results: {GREEN}{passed} passed{NC}, {RED}{failed} failed{NC}, {total} total")
print("==============================")

sys.exit(1 if failed > 0 else 0)
