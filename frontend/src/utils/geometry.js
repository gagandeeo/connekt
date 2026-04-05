export function pointInPolygon(lat, lon, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [rlon_i, rlat_i] = ring[i];
    const [rlon_j, rlat_j] = ring[j];
    if (
      rlat_i > lat !== rlat_j > lat &&
      lon < ((rlon_j - rlon_i) * (lat - rlat_i)) / (rlat_j - rlat_i) + rlon_i
    ) {
      inside = !inside;
    }
  }
  return inside;
}

export function isInsideBoundary(lat, lon, boundaryCoords) {
  if (!boundaryCoords) return false;
  for (const ring of boundaryCoords) {
    if (pointInPolygon(lat, lon, ring)) return true;
  }
  return false;
}
