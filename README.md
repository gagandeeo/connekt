# Connekt - City Satellite Map

A multi-user web application that displays interactive satellite maps of cities with boundary visualization, coordinate checking, and custom landmark management. Features role-based access (admin/normal users) with per-user landmark versioning.

## Features

### User Authentication
- Login/register system with HMAC-signed token authentication
- Two roles: **Admin** (full access) and **Normal** (landmark editing only)
- Session persisted in browser localStorage

### City Search & Boundary Drawing
- Search for any city/region by name
- If a direct boundary polygon isn't found, the app shows Nominatim suggestions so you can pick the correct place
- Draws the administrative boundary as a red polygon overlay on the map
- Boundaries are cached in PostgreSQL for instant loading on subsequent searches

### Multi-Layer Map
Switch between four tile layers via the layer control (top-right corner):
- **Esri Satellite** - Default satellite imagery
- **Google Satellite** - Often better aligned in many regions
- **Google Hybrid** - Satellite with street/building labels (useful for identifying landmarks)
- **OpenStreetMap** - Standard vector map for precise reference

### Coordinate Check & Pinning
- Enter latitude and longitude as a comma-separated pair (e.g., `20.287677, 72.879487`)
- Uses ray casting algorithm (client-side) to determine if the coordinate falls within the drawn boundary
- If outside the boundary, a red toast notification appears

### Custom Landmark Management
- **Normal users:** place landmarks inside the boundary (grey `?` until named, then red stars). **Save Landmarks** stores *your* version in the database. **Base** landmarks (blue stars) are read-only. Toggle **Base** / **My Landmarks** to show or hide each layer. **Voronoi** regions are not shown to normal users.
- **Admins:** edit the shared **base** layer directly (blue markers: add, name, delete in the popup, then **Save Base**). There is no separate “my landmarks” layer for admins. **Voronoi** (dashed polygons) is computed and shown for admins when saving base or promoting.

### Landmark Persistence
- Normal users: **Save Landmarks** persists their version (`is_base=false`, scoped to their account). Reloading a city loads base + their landmarks.
- Admins: **Save Base** replaces the base landmark set (`as_base=true`).

### Admin Landmark Management (preview & promote)
- **User versions** dropdown lists users who have saved landmarks for the current city
- Selecting a user shows purple preview markers; popups can **rename** (DB) or **Promote to base** (merge one landmark) or use **Promote to Base** in the toolbar to replace all base landmarks with that user’s set

### Nested Boundaries (Admin Only)
- Toggle **"Boundary Mode"** (visible to admins only) to switch from landmark placement to boundary-point placement
- Click on the map to place numbered cyan square markers defining a sub-boundary within the parent city boundary
- Boundary points are **draggable** (reposition by dragging) and **removable** (right-click to delete)
- A dashed preview line connects points as you place them, closing into a polygon at 3+ points
- Enter a name and click **"Save Boundary"** in the side panel to persist the nested boundary
- Saved nested boundaries appear as cyan polygons with name labels on the map
- **Edit** existing nested boundaries to modify their points, or **Delete** them from the panel

### Fill Toggle
- Click **"Hide Fill" / "Show Fill"** to toggle the filled color on all boundary polygons (parent + nested)
- Boundary edges remain visible at all times — only the interior fill is toggled
- Useful for seeing satellite imagery clearly underneath the boundaries

## Tech Stack

- **Frontend**: HTML, CSS, JavaScript, [Leaflet.js](https://leafletjs.com/) (via CDN)
- **Backend**: Python, [FastAPI](https://fastapi.tiangolo.com/) + [uvicorn](https://www.uvicorn.org/)
- **Database**: PostgreSQL via [Prisma Client Python](https://prisma-client-py.readthedocs.io/)
- **Geocoding**: [Nominatim](https://nominatim.openstreetmap.org/) (OpenStreetMap)
- **Boundary Polygons**: [OSMnx](https://osmnx.readthedocs.io/), [polygons.openstreetmap.fr](https://polygons.openstreetmap.fr/) (fallback)
- **Landmark Lookup** (disabled): [Overpass API](https://overpass-api.de/), [Wikipedia Geosearch API](https://www.mediawiki.org/wiki/API:Geosearch) (fallback)

## Project Structure

```
connekt/
  index.html              # Frontend - map UI, auth modal, all client-side logic
  server.py               # FastAPI backend - auth, async API endpoints
  db.py                   # Prisma client initialization
  schema.prisma           # Database schema (User, Boundary, Landmark, NestedBoundary, VoronoiCell)
  .env                    # DATABASE_URL, SECRET_KEY, PASSWORD_SALT
  get_boundary.py         # Boundary fetching logic (Nominatim, OSMnx, OSM.fr)
  get_landmarks.py        # Landmark fetching via Overpass/Wikipedia (currently disabled)
  migrate_json_to_db.py   # One-time migration script: JSON cache files → database
  test_api.py             # API endpoint test script (run manually)
  test_api.sh             # API endpoint test script (bash version)
```

## Setup & Running

```bash
# Activate the virtual environment
source .venv/bin/activate

# Push the Prisma schema to the database (first time or after schema changes)
prisma db push

# Generate the Prisma client
prisma generate

# (Optional) Migrate existing JSON cache data into the database
python migrate_json_to_db.py

# (Optional) Mark existing landmarks as base version
# psql: UPDATE "Landmark" SET is_base = true;

# Create an admin user (must be done manually via SQL)
# First generate the password hash:
python -c "import hashlib; print(hashlib.sha256('connekt-salt:YOUR_PASSWORD'.encode()).hexdigest())"
# Then insert:
# psql: INSERT INTO "User" (username, password, role) VALUES ('admin', '<hash>', 'ADMIN');

# Run the server
python server.py
```

The app will be available at `http://localhost:5000`.

### Environment Variables (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | (in `.env`) | PostgreSQL connection string |
| `SECRET_KEY` | `connekt-default-secret-change-me` | HMAC signing key for auth tokens |
| `PASSWORD_SALT` | `connekt-salt` | Salt prepended to passwords before hashing |

## API Endpoints

### Authentication
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/register` | — | Register a new normal user |
| `POST` | `/api/login` | — | Login, returns user + token |
| `GET` | `/api/me` | User | Validate token, return user info |

### City & Boundary
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/` | — | Serves the frontend |
| `POST` | `/api/search` | — | Search for a city (returns boundary or suggestions) |
| `POST` | `/api/boundary` | — | Fetch boundary for a selected Nominatim result |
| `POST` | `/api/landmarks` | — | Fetch landmarks near a lat/lon (disabled in UI) |
| `POST` | `/api/reverse-geocode` | — | Reverse geocode a lat/lon to find nearest POI name |

### Landmarks (User-Scoped)
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/saved-landmarks` | User | Load landmarks (`id`, `name`, `lat`, `lon`). `version: "base"` or `"user"`. Admin can pass `user_id` to view another user's. |
| `POST` | `/api/save-landmarks` | User | Save landmarks. Normal users save as their version. Admin can pass `as_base: true`. User-version saves return `landmark_ids` (same order as the payload) for per-marker actions. |

### Nested Boundaries (Admin Only)
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/nested-boundaries` | — | Load all nested boundaries for a parent boundary |
| `POST` | `/api/save-nested-boundary` | Admin | Create a nested boundary (name + 3+ coords) |
| `POST` | `/api/update-nested-boundary` | Admin | Update coordinates of an existing nested boundary |
| `POST` | `/api/delete-nested-boundary` | Admin | Delete a nested boundary |

### Voronoi
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/compute-voronoi` | — | Compute Voronoi cells for landmarks clipped to boundary |
| `POST` | `/api/voronoi` | — | Load cached Voronoi cells for a boundary |

### Admin
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/admin/landmark-users` | Admin | List users who have landmark versions for a boundary |
| `POST` | `/api/admin/promote-base` | Admin | Replace base with a full copy of a user's landmarks |
| `POST` | `/api/admin/promote-landmarks-to-base` | Admin | Merge selected user landmark rows into base (`landmark_ids` + `user_id` + `boundary_name`) |
| `POST` | `/api/admin/update-landmark` | Admin | Rename a landmark (`boundary_name`, `landmark_id`, `name`) — base or user version |
