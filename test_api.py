#!/usr/bin/env python3
"""API endpoint test script for Connekt.

Usage: python test_api.py
Server must be running at http://localhost:5000.

Setup uses Prisma directly to create a test boundary and seeded admin/normal
users (so auth-protected endpoints can be exercised). All test rows are
cascade-deleted at the end.
"""

import asyncio
import hashlib
import os
import sys

import requests
from prisma import Json, Prisma

BASE = "http://localhost:5000"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"

PASSWORD_SALT = os.environ.get("PASSWORD_SALT", "connekt-salt")

TEST_BOUNDARY_NAME = "__test_boundary__"
TEST_ADMIN = ("__test_admin__", "test_admin_pw")
TEST_NORMAL = ("__test_user__", "test_user_pw")
TEST_COORDS = [
    [
        [72.860, 19.060],
        [72.900, 19.060],
        [72.900, 19.100],
        [72.860, 19.100],
        [72.860, 19.060],
    ]
]

passed = 0
failed = 0
total = 0


def hash_password(password: str) -> str:
    salted = f"{PASSWORD_SALT}:{password}"
    return hashlib.sha256(salted.encode()).hexdigest()


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


def post(endpoint, json=None, headers=None, timeout=10):
    return requests.post(
        f"{BASE}{endpoint}", json=json or {}, headers=headers or {}, timeout=timeout
    )


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def section(title):
    print(f"\n{YELLOW}--- {title} ---{NC}")


# --------------------------------------------------
# Setup / teardown
# --------------------------------------------------
async def setup():
    db = Prisma()
    await db.connect()
    try:
        existing = await db.boundary.find_first(
            where={"name": {"equals": TEST_BOUNDARY_NAME, "mode": "insensitive"}}
        )
        if existing:
            await db.boundary.delete(where={"boundary_id": existing.boundary_id})
        boundary = await db.boundary.create(
            data={"name": TEST_BOUNDARY_NAME, "coords": Json(TEST_COORDS)}
        )

        async def upsert_user(username, password, role):
            existing_user = await db.user.find_unique(where={"username": username})
            data = {"password": hash_password(password), "role": role}
            if existing_user:
                await db.user.update(where={"id": existing_user.id}, data=data)
                return existing_user.id
            created = await db.user.create(data={"username": username, **data})
            return created.id

        admin_id = await upsert_user(TEST_ADMIN[0], TEST_ADMIN[1], "ADMIN")
        normal_id = await upsert_user(TEST_NORMAL[0], TEST_NORMAL[1], "NORMAL")

        return int(boundary.boundary_id), admin_id, normal_id
    finally:
        await db.disconnect()


async def teardown(boundary_id, admin_id, normal_id):
    db = Prisma()
    await db.connect()
    try:
        try:
            await db.boundary.delete(where={"boundary_id": boundary_id})
        except Exception:
            pass
        for uid in (admin_id, normal_id):
            try:
                await db.user.delete(where={"id": uid})
            except Exception:
                pass
    finally:
        await db.disconnect()


def login(username, password):
    r = requests.post(
        f"{BASE}/api/login", json={"username": username, "password": password}, timeout=10
    )
    if r.status_code != 200:
        raise RuntimeError(f"Login failed for {username}: {r.status_code} {r.text}")
    return r.json()["token"]


print("==============================")
print(" Connekt API Test Suite")
print("==============================")

boundary_id, admin_id, normal_id = asyncio.run(setup())
admin_token = login(*TEST_ADMIN)
normal_token = login(*TEST_NORMAL)
print(f"Test boundary_id={boundary_id} admin_id={admin_id} normal_id={normal_id}")

try:
    # --------------------------------------------------
    section("GET /")
    r = requests.get(f"{BASE}/", timeout=10)
    check("GET / returns 200", 200, r)

    # --------------------------------------------------
    section("POST /api/register")
    r = post("/api/register", {})
    check("register: missing fields returns 400", 400, r)
    check_body("register: error message present", "username and password are required", r)

    # --------------------------------------------------
    section("POST /api/login")
    r = post("/api/login", {"username": TEST_NORMAL[0], "password": "wrong"})
    check("login: bad password returns 401", 401, r)

    r = post("/api/login", {"username": TEST_NORMAL[0], "password": TEST_NORMAL[1]})
    check("login: valid creds returns 200", 200, r)
    check_body("login: response has token", '"token"', r)

    # --------------------------------------------------
    section("GET /api/me")
    r = requests.get(f"{BASE}/api/me", timeout=10)
    check("me: no auth returns 401", 401, r)

    r = requests.get(f"{BASE}/api/me", headers=auth_headers(normal_token), timeout=10)
    check("me: valid auth returns 200", 200, r)

    # --------------------------------------------------
    section("POST /api/search")
    r = post("/api/search", {})
    check("search: empty city_name returns 400", 400, r)
    check_body("search: error message present", "city_name is required", r)

    r = post("/api/search", {"city_name": TEST_BOUNDARY_NAME}, timeout=15)
    check("search: cached test boundary returns 200", 200, r)
    check_body("search: response includes boundary_id", '"boundary_id"', r)

    # --------------------------------------------------
    section("POST /api/boundary")
    r = post("/api/boundary", {})
    check("boundary: missing fields returns 400", 400, r)
    check_body("boundary: error mentions required fields", "osm_type and osm_id are required", r)

    # --------------------------------------------------
    section("POST /api/landmarks")
    r = post("/api/landmarks", {})
    check("landmarks: missing lat/lon returns 400", 400, r)
    check_body("landmarks: error message present", "lat and lon are required", r)

    # --------------------------------------------------
    section("POST /api/reverse-geocode")
    r = post("/api/reverse-geocode", {})
    check("reverse-geocode: missing lat/lon returns 400", 400, r)

    # --------------------------------------------------
    section("POST /api/saved-landmarks")
    r = post("/api/saved-landmarks", {})
    check("saved-landmarks: missing identifier returns 400", 400, r)

    r = post("/api/saved-landmarks", {"boundary_id": boundary_id})
    check("saved-landmarks: by boundary_id returns 200", 200, r)
    check_body("saved-landmarks: response has landmarks array", '"landmarks"', r)

    r = post("/api/saved-landmarks", {"boundary_name": TEST_BOUNDARY_NAME})
    check("saved-landmarks: by boundary_name returns 200", 200, r)

    # --------------------------------------------------
    section("POST /api/save-landmarks")
    r = post("/api/save-landmarks", {"boundary_id": boundary_id, "landmarks": []})
    check("save-landmarks: no auth returns 401", 401, r)

    r = post(
        "/api/save-landmarks",
        {"landmarks": []},
        headers=auth_headers(normal_token),
    )
    check("save-landmarks: missing identifier returns 400", 400, r)

    r = post(
        "/api/save-landmarks",
        {
            "boundary_id": boundary_id,
            "landmarks": [
                {"name": "Test Point A", "lat": 19.076, "lon": 72.877},
                {"name": "Test Point B", "lat": 19.080, "lon": 72.880},
            ],
        },
        headers=auth_headers(normal_token),
    )
    check("save-landmarks: valid save returns 200", 200, r)
    check_body("save-landmarks: response has ok:true", '"ok":true', r)
    check_body("save-landmarks: count is 2", '"count":2', r)
    check_body("save-landmarks: response includes landmark_ids array", '"landmark_ids"', r)

    r = post(
        "/api/saved-landmarks",
        {"boundary_id": boundary_id, "version": "user"},
        headers=auth_headers(normal_token),
    )
    check("save-landmarks: reload (user version) returns 200", 200, r)
    check_body("save-landmarks: reload contains Test Point A", "Test Point A", r)
    check_body("save-landmarks: reload contains Test Point B", "Test Point B", r)

    r = post(
        "/api/save-landmarks",
        {
            "boundary_id": boundary_id,
            "as_base": True,
            "landmarks": [{"name": "Base Point", "lat": 19.07, "lon": 72.87}],
        },
        headers=auth_headers(normal_token),
    )
    check("save-landmarks: normal user as_base returns 403", 403, r)

    r = post(
        "/api/save-landmarks",
        {
            "boundary_id": boundary_id,
            "as_base": True,
            "landmarks": [{"name": "Base Point", "lat": 19.07, "lon": 72.87}],
        },
        headers=auth_headers(admin_token),
    )
    check("save-landmarks: admin as_base returns 200", 200, r)

    # --------------------------------------------------
    section("POST /api/nested-boundaries")
    r = post("/api/nested-boundaries", {})
    check("nested-boundaries: missing identifier returns 400", 400, r)

    r = post("/api/nested-boundaries", {"boundary_id": boundary_id})
    check("nested-boundaries: valid request returns 200", 200, r)
    check_body("nested-boundaries: response has nested_boundaries", '"nested_boundaries"', r)

    # --------------------------------------------------
    section("POST /api/save-nested-boundary")
    r = post("/api/save-nested-boundary", {})
    check("save-nested: no auth returns 401", 401, r)

    r = post(
        "/api/save-nested-boundary", {}, headers=auth_headers(normal_token)
    )
    check("save-nested: normal user returns 403", 403, r)

    r = post(
        "/api/save-nested-boundary", {}, headers=auth_headers(admin_token)
    )
    check("save-nested: missing fields returns 400", 400, r)

    r = post(
        "/api/save-nested-boundary",
        {
            "boundary_id": boundary_id,
            "child_name": "zone1",
            "coords": [{"lat": 19.0, "lon": 72.8}],
        },
        headers=auth_headers(admin_token),
    )
    check("save-nested: <3 coords returns 400", 400, r)
    check_body("save-nested: error mentions 3 points", "At least 3", r)

    r = post(
        "/api/save-nested-boundary",
        {
            "boundary_id": boundary_id,
            "child_name": "__test_zone__",
            "coords": [
                {"lat": 19.07, "lon": 72.87},
                {"lat": 19.08, "lon": 72.87},
                {"lat": 19.08, "lon": 72.88},
            ],
        },
        headers=auth_headers(admin_token),
    )
    check("save-nested: valid save returns 200", 200, r)
    check_body("save-nested: response has ok:true", '"ok":true', r)

    r = post("/api/nested-boundaries", {"boundary_id": boundary_id})
    check("save-nested: appears in listing", 200, r)
    check_body("save-nested: listing contains __test_zone__", "__test_zone__", r)

    # --------------------------------------------------
    section("POST /api/update-nested-boundary")
    r = post(
        "/api/update-nested-boundary", {}, headers=auth_headers(admin_token)
    )
    check("update-nested: missing fields returns 400", 400, r)

    r = post(
        "/api/update-nested-boundary",
        {
            "boundary_id": boundary_id,
            "child_name": "__nonexistent__",
            "coords": [{"lat": 1, "lon": 1}, {"lat": 2, "lon": 2}, {"lat": 3, "lon": 3}],
        },
        headers=auth_headers(admin_token),
    )
    check("update-nested: nonexistent returns 404", 404, r)

    r = post(
        "/api/update-nested-boundary",
        {
            "boundary_id": boundary_id,
            "child_name": "__test_zone__",
            "coords": [
                {"lat": 19.071, "lon": 72.871},
                {"lat": 19.081, "lon": 72.871},
                {"lat": 19.081, "lon": 72.881},
            ],
        },
        headers=auth_headers(admin_token),
    )
    check("update-nested: valid update returns 200", 200, r)
    check_body("update-nested: response has ok:true", '"ok":true', r)

    # --------------------------------------------------
    section("POST /api/delete-nested-boundary")
    r = post(
        "/api/delete-nested-boundary", {}, headers=auth_headers(admin_token)
    )
    check("delete-nested: missing fields returns 400", 400, r)

    r = post(
        "/api/delete-nested-boundary",
        {"boundary_id": boundary_id, "child_name": "__nonexistent__"},
        headers=auth_headers(admin_token),
    )
    check("delete-nested: nonexistent returns 404", 404, r)

    r = post(
        "/api/delete-nested-boundary",
        {"boundary_id": boundary_id, "child_name": "__test_zone__"},
        headers=auth_headers(admin_token),
    )
    check("delete-nested: valid delete returns 200", 200, r)
    check_body("delete-nested: response has ok:true", '"ok":true', r)

    r = post("/api/nested-boundaries", {"boundary_id": boundary_id})
    total += 1
    if "__test_zone__" not in r.text:
        passed += 1
        print(f"{GREEN}PASS{NC} delete-nested: zone removed from listing")
    else:
        failed += 1
        print(f"{RED}FAIL{NC} delete-nested: zone still present after delete")

    # --------------------------------------------------
    section("POST /api/admin/landmark-users")
    r = post("/api/admin/landmark-users", {"boundary_id": boundary_id})
    check("landmark-users: no auth returns 401", 401, r)

    r = post(
        "/api/admin/landmark-users",
        {"boundary_id": boundary_id},
        headers=auth_headers(normal_token),
    )
    check("landmark-users: normal user returns 403", 403, r)

    r = post(
        "/api/admin/landmark-users",
        {"boundary_id": boundary_id},
        headers=auth_headers(admin_token),
    )
    check("landmark-users: admin returns 200", 200, r)
    check_body("landmark-users: response has users array", '"users"', r)

    # --------------------------------------------------
    section("POST /api/compute-voronoi")
    r = post("/api/compute-voronoi", {"landmarks": [], "boundary_coords": []})
    check("compute-voronoi: missing identifier returns 400", 400, r)

    r = post(
        "/api/compute-voronoi",
        {
            "boundary_id": boundary_id,
            "landmarks": [{"name": "A", "lat": 19.07, "lon": 72.87}],
            "boundary_coords": [[1, 2]],
        },
    )
    check("compute-voronoi: <2 landmarks returns 400", 400, r)

    r = post(
        "/api/compute-voronoi",
        {
            "boundary_id": boundary_id,
            "landmarks": [
                {"name": "A", "lat": 19.07, "lon": 72.87},
                {"name": "B", "lat": 19.08, "lon": 72.88},
            ],
            "boundary_coords": [],
        },
    )
    check("compute-voronoi: empty boundary_coords returns 400", 400, r)

    r = post(
        "/api/compute-voronoi",
        {
            "boundary_id": boundary_id,
            "landmarks": [
                {"name": "A", "lat": 19.075, "lon": 72.875},
                {"name": "B", "lat": 19.078, "lon": 72.878},
            ],
            "boundary_coords": [
                [[72.87, 19.07], [72.88, 19.07], [72.875, 19.09], [72.87, 19.07]],
            ],
        },
    )
    check("compute-voronoi: valid compute returns 200", 200, r)
    check_body("compute-voronoi: response has cells", '"cells"', r)

    # --------------------------------------------------
    section("POST /api/voronoi")
    r = post("/api/voronoi", {})
    check("voronoi: missing identifier returns 400", 400, r)

    r = post("/api/voronoi", {"boundary_id": boundary_id})
    check("voronoi: valid request returns 200", 200, r)
    check_body("voronoi: response has cells", '"cells"', r)

finally:
    asyncio.run(teardown(boundary_id, admin_id, normal_id))

# --------------------------------------------------
print()
print("==============================")
print(f" Results: {GREEN}{passed} passed{NC}, {RED}{failed} failed{NC}, {total} total")
print("==============================")

sys.exit(1 if failed > 0 else 0)
