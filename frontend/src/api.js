let tokenGetter = () => null;

export function setTokenGetter(fn) {
  tokenGetter = fn;
}

function authHeaders(extra = {}) {
  const headers = { 'Content-Type': 'application/json', ...extra };
  const token = tokenGetter();
  if (token) headers['Authorization'] = 'Bearer ' + token;
  return headers;
}

async function authFetch(url, options = {}) {
  options.headers = authHeaders(options.headers);
  return fetch(url, options);
}

// --- Auth ---

export async function login(username, password) {
  const resp = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  return resp.json();
}

export async function register(username, password) {
  const resp = await fetch('/api/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  return resp.json();
}

export async function getMe(token) {
  const resp = await fetch('/api/me', {
    headers: { Authorization: 'Bearer ' + token },
  });
  if (!resp.ok) return null;
  return resp.json();
}

// --- Search & Boundary ---

export async function searchCity(cityName) {
  const resp = await fetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ city_name: cityName }),
  });
  return resp.json();
}

export async function fetchBoundary(suggestion) {
  const resp = await fetch('/api/boundary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      osm_type: suggestion.osm_type,
      osm_id: suggestion.osm_id,
      display_name: suggestion.display_name,
    }),
  });
  return resp.json();
}

// --- Landmarks ---

export async function getSavedLandmarks(boundaryName, version, userId) {
  const body = { boundary_name: boundaryName, version };
  if (userId != null) body.user_id = parseInt(userId);
  const resp = await authFetch('/api/saved-landmarks', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return resp.json();
}

export async function saveLandmarks(boundaryName, landmarks, asBase) {
  const resp = await authFetch('/api/save-landmarks', {
    method: 'POST',
    body: JSON.stringify({ boundary_name: boundaryName, landmarks, as_base: asBase }),
  });
  return resp.json();
}

export async function reverseGeocode(lat, lon) {
  const resp = await authFetch('/api/reverse-geocode', {
    method: 'POST',
    body: JSON.stringify({ lat, lon }),
  });
  const data = await resp.json();
  return data.name || '';
}

// --- Nested Boundaries ---

export async function getNestedBoundaries(parentName) {
  const resp = await authFetch('/api/nested-boundaries', {
    method: 'POST',
    body: JSON.stringify({ parent_name: parentName }),
  });
  const data = await resp.json();
  return data.nested_boundaries || {};
}

export async function saveNestedBoundary(parentName, childName, coords) {
  const resp = await authFetch('/api/save-nested-boundary', {
    method: 'POST',
    body: JSON.stringify({ parent_name: parentName, child_name: childName, coords }),
  });
  return resp.json();
}

export async function updateNestedBoundary(parentName, childName, coords) {
  const resp = await authFetch('/api/update-nested-boundary', {
    method: 'POST',
    body: JSON.stringify({ parent_name: parentName, child_name: childName, coords }),
  });
  return resp.json();
}

export async function deleteNestedBoundary(parentName, childName) {
  const resp = await authFetch('/api/delete-nested-boundary', {
    method: 'POST',
    body: JSON.stringify({ parent_name: parentName, child_name: childName }),
  });
  return resp.json();
}

// --- Voronoi ---

export async function computeVoronoi(boundaryName, landmarks, boundaryCoords) {
  const resp = await authFetch('/api/compute-voronoi', {
    method: 'POST',
    body: JSON.stringify({
      boundary_name: boundaryName,
      landmarks,
      boundary_coords: boundaryCoords,
    }),
  });
  return resp.json();
}

export async function getCachedVoronoi(boundaryName) {
  const resp = await authFetch('/api/voronoi', {
    method: 'POST',
    body: JSON.stringify({ boundary_name: boundaryName }),
  });
  return resp.json();
}

// --- Admin ---

export async function getLandmarkUsers(boundaryName) {
  const resp = await authFetch('/api/admin/landmark-users', {
    method: 'POST',
    body: JSON.stringify({ boundary_name: boundaryName }),
  });
  return resp.json();
}

export async function promoteBase(boundaryName, userId) {
  const resp = await authFetch('/api/admin/promote-base', {
    method: 'POST',
    body: JSON.stringify({ boundary_name: boundaryName, user_id: parseInt(userId) }),
  });
  return resp.json();
}

export async function promoteLandmarksToBase(boundaryName, userId, landmarkIds) {
  const resp = await authFetch('/api/admin/promote-landmarks-to-base', {
    method: 'POST',
    body: JSON.stringify({
      boundary_name: boundaryName,
      user_id: parseInt(userId),
      landmark_ids: landmarkIds,
    }),
  });
  return resp.json();
}

export async function adminUpdateLandmark(boundaryName, landmarkId, name) {
  const resp = await authFetch('/api/admin/update-landmark', {
    method: 'POST',
    body: JSON.stringify({
      boundary_name: boundaryName,
      landmark_id: landmarkId,
      name,
    }),
  });
  return resp.json();
}
