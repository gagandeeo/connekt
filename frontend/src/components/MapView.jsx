import { useEffect, useCallback, useRef } from 'react';
import { MapContainer, TileLayer, Polygon, Tooltip, useMap, useMapEvents, LayersControl } from 'react-leaflet';
import L from 'leaflet';
import { useAuth } from '../contexts/AuthContext';
import { useMapState } from '../contexts/MapContext';
import { isInsideBoundary } from '../utils/geometry';
import {
  createUserLandmarkIcon,
  createBaseLandmarkIcon,
  createEditableBaseLandmarkIcon,
  createViewedUserLandmarkIcon,
  createBoundaryPointIcon,
} from '../utils/icons';

const VORONOI_COLORS = [
  '#e94560', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
  '#1abc9c', '#e67e22', '#e74c3c', '#00bcd4', '#8e44ad',
  '#16a085', '#d35400', '#c0392b', '#2980b9', '#27ae60',
];

// --- Client-side ID generator (stable identity for diff-based marker sync) ---
let _nextCid = 1;
export function genCid() { return _nextCid++; }

function MapRefSetter() {
  const map = useMap();
  const { mapRef } = useMapState();
  useEffect(() => {
    mapRef.current = map;
  }, [map, mapRef]);
  return null;
}

function MapClickHandler({ onMapClick }) {
  useMapEvents({ click: onMapClick });
  return null;
}

// --- Popup HTML builders ---
function buildUserPopupHtml(lm) {
  const nameVal = (lm.name || '').replace(/"/g, '&quot;');
  return `<div class="landmark-popup-form">
    <label style="font-size:0.8rem;color:#666;">${lm.lat.toFixed(6)}, ${lm.lon.toFixed(6)}</label>
    <input type="text" class="lm-name-input" value="${nameVal}" placeholder="Enter landmark name..." />
    <div class="popup-btns">
      <button class="btn-save" data-action="save-user" data-cid="${lm._cid}">Save</button>
      <button class="btn-delete" data-action="delete-user" data-cid="${lm._cid}">Delete</button>
    </div>
  </div>`;
}

function buildAdminBasePopupHtml(lm) {
  const nameVal = (lm.name || '').replace(/"/g, '&quot;');
  return `<div class="landmark-popup-form">
    <div style="font-size:0.75rem;color:#3498db;font-weight:600;margin-bottom:4px;">Base landmark</div>
    <label style="font-size:0.8rem;color:#666;">${lm.lat.toFixed(6)}, ${lm.lon.toFixed(6)}</label>
    <input type="text" class="lm-name-input" value="${nameVal}" placeholder="Landmark name..." />
    <div class="popup-btns">
      <button class="btn-save" data-action="save-admin-base" data-cid="${lm._cid}">Save</button>
      <button class="btn-delete" data-action="delete-admin-base" data-cid="${lm._cid}">Delete</button>
    </div>
  </div>`;
}

function buildViewedUserPopupHtml(lm) {
  const nameVal = (lm.name || '').replace(/"/g, '&quot;');
  return `<div class="landmark-popup-form">
    <label style="font-size:0.8rem;color:#666;">${lm.lat.toFixed(6)}, ${lm.lon.toFixed(6)}</label>
    <input type="text" class="lm-name-input" value="${nameVal}" placeholder="Landmark name..." />
    <div class="popup-btns" style="margin-top:8px;">
      <button type="button" class="btn-save" data-action="save-viewed-name" data-id="${lm.id}">Save name</button>
    </div>
    <button type="button" class="btn-promote-one" data-action="promote-one" data-id="${lm.id}">Promote to base</button>
  </div>`;
}

export default function MapView() {
  const { isAdmin } = useAuth();
  const {
    boundaryCoords, boundaryName,
    baseLandmarks, setBaseLandmarks,
    userLandmarks, setUserLandmarks,
    viewedUserLandmarks,
    showBase, showUser,
    fillVisible, screenLocked,
    boundaryPointMode, boundaryPoints, setBoundaryPoints,
    nestedBoundaries,
    voronoiCells,
    setStatus,
  } = useMapState();

  // Marker caches: Map<_cid, L.Marker>
  const baseMarkerCache = useRef(new Map());
  const userMarkerCache = useRef(new Map());
  const viewedMarkerCache = useRef(new Map());
  const bpMarkersRef = useRef([]);
  const bpLineRef = useRef(null);
  const mapInstanceRef = useRef(null);

  // Refs for viewed-user popup callbacks (set by parent)
  const onSaveViewedNameRef = useRef(null);
  const onPromoteOneRef = useRef(null);

  // --- Sync base landmarks (diff-based) ---
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;
    const cache = baseMarkerCache.current;
    const activeCids = new Set(baseLandmarks.map(l => l._cid));

    // Remove markers for deleted landmarks
    for (const [cid, marker] of cache) {
      if (!activeCids.has(cid)) {
        map.removeLayer(marker);
        cache.delete(cid);
      }
    }

    // Add or update markers
    baseLandmarks.forEach((lm) => {
      const existing = cache.get(lm._cid);
      if (existing) {
        // Update in-place: icon + tooltip + popup
        const named = !!(lm.name && String(lm.name).trim());
        existing.setIcon(isAdmin ? createEditableBaseLandmarkIcon(named) : createBaseLandmarkIcon());
        existing.unbindTooltip();
        existing.bindTooltip((lm.name || '').trim() || 'Unnamed', { direction: 'top' });
        if (isAdmin) {
          existing.setPopupContent(buildAdminBasePopupHtml(lm));
        }
        // Visibility
        if (showBase && !map.hasLayer(existing)) existing.addTo(map);
        else if (!showBase && map.hasLayer(existing)) map.removeLayer(existing);
      } else {
        // Create new marker
        const named = !!(lm.name && String(lm.name).trim());
        const icon = isAdmin ? createEditableBaseLandmarkIcon(named) : createBaseLandmarkIcon();
        const marker = L.marker([lm.lat, lm.lon], { icon, interactive: true });
        marker.bindTooltip((lm.name || '').trim() || 'Unnamed', { direction: 'top' });

        if (isAdmin) {
          marker.bindPopup(buildAdminBasePopupHtml(lm));
          marker.on('click', () => {
            // Re-read current data from state ref
            const cur = baseLandmarksRef.current.find(l => l._cid === lm._cid);
            if (cur) marker.setPopupContent(buildAdminBasePopupHtml(cur));
          });
          marker.on('popupopen', () => {
            const container = marker.getPopup()?.getElement();
            if (!container) return;
            const cid = lm._cid;
            container.querySelector('[data-action="save-admin-base"]')?.addEventListener('click', () => {
              const input = container.querySelector('.lm-name-input');
              const name = input?.value.trim() || '';
              marker.closePopup();
              // Defer state update so popup DOM is cleaned up first
              setTimeout(() => {
                setBaseLandmarks(prev => prev.map(l => l._cid === cid ? { ...l, name } : l));
              }, 0);
            });
            container.querySelector('[data-action="delete-admin-base"]')?.addEventListener('click', () => {
              marker.closePopup();
              setTimeout(() => {
                setBaseLandmarks(prev => prev.filter(l => l._cid !== cid));
              }, 0);
            });
          });
        }

        if (showBase) marker.addTo(map);
        cache.set(lm._cid, marker);
      }
    });
  }, [baseLandmarks, showBase, isAdmin, setBaseLandmarks]);

  // --- Sync user landmarks (diff-based) ---
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;
    const cache = userMarkerCache.current;
    const activeCids = new Set(userLandmarks.map(l => l._cid));

    // Remove deleted
    for (const [cid, marker] of cache) {
      if (!activeCids.has(cid)) {
        map.removeLayer(marker);
        cache.delete(cid);
      }
    }

    // Add or update
    userLandmarks.forEach((lm) => {
      const existing = cache.get(lm._cid);
      if (existing) {
        existing.setIcon(createUserLandmarkIcon(!!lm.name));
        existing.setPopupContent(buildUserPopupHtml(lm));
        if (showUser && !map.hasLayer(existing)) existing.addTo(map);
        else if (!showUser && map.hasLayer(existing)) map.removeLayer(existing);
      } else {
        const icon = createUserLandmarkIcon(!!lm.name);
        const marker = L.marker([lm.lat, lm.lon], { icon });
        marker.bindPopup(buildUserPopupHtml(lm));
        marker.on('click', () => {
          const cur = userLandmarksRef.current.find(l => l._cid === lm._cid);
          if (cur) marker.setPopupContent(buildUserPopupHtml(cur));
        });
        marker.on('popupopen', () => {
          const container = marker.getPopup()?.getElement();
          if (!container) return;
          const cid = lm._cid;
          container.querySelector('[data-action="save-user"]')?.addEventListener('click', () => {
            const input = container.querySelector('.lm-name-input');
            const name = input?.value.trim() || '';
            marker.closePopup();
            setTimeout(() => {
              setUserLandmarks(prev => prev.map(l => l._cid === cid ? { ...l, name } : l));
            }, 0);
          });
          container.querySelector('[data-action="delete-user"]')?.addEventListener('click', () => {
            marker.closePopup();
            setTimeout(() => {
              setUserLandmarks(prev => prev.filter(l => l._cid !== cid));
            }, 0);
          });
        });

        if (showUser) marker.addTo(map);
        cache.set(lm._cid, marker);
      }
    });
  }, [userLandmarks, showUser, setUserLandmarks]);

  // --- Sync viewed user landmarks (diff-based) ---
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;
    const cache = viewedMarkerCache.current;
    const activeIds = new Set(viewedUserLandmarks.map(l => l.id));

    for (const [id, marker] of cache) {
      if (!activeIds.has(id)) {
        map.removeLayer(marker);
        cache.delete(id);
      }
    }

    viewedUserLandmarks.forEach((lm) => {
      if (cache.has(lm.id)) {
        const existing = cache.get(lm.id);
        existing.unbindTooltip();
        existing.bindTooltip(lm.name || 'Unnamed', { direction: 'top' });
        existing.setPopupContent(buildViewedUserPopupHtml(lm));
        return;
      }
      const icon = createViewedUserLandmarkIcon();
      const marker = L.marker([lm.lat, lm.lon], { icon, interactive: true }).addTo(map);
      marker.bindTooltip(lm.name || 'Unnamed', { direction: 'top' });
      marker.bindPopup(buildViewedUserPopupHtml(lm));
      marker.on('click', () => marker.setPopupContent(buildViewedUserPopupHtml(lm)));
      marker.on('popupopen', () => {
        const container = marker.getPopup()?.getElement();
        if (!container) return;
        container.querySelector('[data-action="save-viewed-name"]')?.addEventListener('click', () => {
          if (onSaveViewedNameRef.current) {
            const input = container.querySelector('.lm-name-input');
            onSaveViewedNameRef.current(lm.id, input?.value.trim() || '');
          }
        });
        container.querySelector('[data-action="promote-one"]')?.addEventListener('click', () => {
          if (onPromoteOneRef.current) {
            onPromoteOneRef.current(lm.id);
          }
        });
      });
      cache.set(lm.id, marker);
    });
  }, [viewedUserLandmarks]);

  // --- Refs to always have current landmark arrays (for popup click handlers) ---
  const baseLandmarksRef = useRef(baseLandmarks);
  baseLandmarksRef.current = baseLandmarks;
  const userLandmarksRef = useRef(userLandmarks);
  userLandmarksRef.current = userLandmarks;

  // --- Cleanup all caches on unmount ---
  useEffect(() => {
    return () => {
      const map = mapInstanceRef.current;
      if (!map) return;
      for (const m of baseMarkerCache.current.values()) map.removeLayer(m);
      for (const m of userMarkerCache.current.values()) map.removeLayer(m);
      for (const m of viewedMarkerCache.current.values()) map.removeLayer(m);
      baseMarkerCache.current.clear();
      userMarkerCache.current.clear();
      viewedMarkerCache.current.clear();
    };
  }, []);

  // --- Boundary Points (imperative draggable markers) ---
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    bpMarkersRef.current.forEach(m => map.removeLayer(m));
    bpMarkersRef.current = [];
    if (bpLineRef.current) {
      map.removeLayer(bpLineRef.current);
      bpLineRef.current = null;
    }

    boundaryPoints.forEach((bp, idx) => {
      const icon = createBoundaryPointIcon(idx);
      const marker = L.marker([bp.lat, bp.lon], { icon, draggable: true }).addTo(map);

      marker.on('drag', (e) => {
        const pos = e.target.getLatLng();
        setBoundaryPoints(prev =>
          prev.map((p, i) => i === idx ? { ...p, lat: pos.lat, lon: pos.lng } : p)
        );
      });

      marker.on('contextmenu', (e) => {
        L.DomEvent.stopPropagation(e);
        map.removeLayer(marker);
        setBoundaryPoints(prev => prev.filter((_, i) => i !== idx));
      });

      bpMarkersRef.current.push(marker);
    });

    // Draw connecting line
    if (boundaryPoints.length >= 2) {
      const latlngs = boundaryPoints.map(bp => [bp.lat, bp.lon]);
      if (boundaryPoints.length >= 3) latlngs.push(latlngs[0]);
      bpLineRef.current = L.polyline(latlngs, {
        color: '#00bcd4',
        weight: 2,
        dashArray: '6, 4',
        opacity: 0.8,
      }).addTo(map);
    }
  }, [boundaryPoints, setBoundaryPoints]);

  // --- Map Click Handler ---
  const handleMapClick = useCallback((e) => {
    if (screenLocked || !boundaryCoords) return;

    const { lat, lng: lon } = e.latlng;

    if (boundaryPointMode) {
      if (isInsideBoundary(lat, lon, boundaryCoords)) {
        setBoundaryPoints(prev => [...prev, { lat, lon }]);
        setStatus(`Boundary point #${boundaryPoints.length + 1} placed. Right-click to remove.`);
      } else {
        showToastGlobal('Point is outside the parent boundary!', 'error');
      }
    } else {
      if (isInsideBoundary(lat, lon, boundaryCoords)) {
        if (isAdmin) {
          setBaseLandmarks(prev => [...prev, { lat, lon, name: '', id: null, _cid: genCid() }]);
          setStatus('Base landmark placed — give it a name.');
        } else {
          setUserLandmarks(prev => [...prev, { lat, lon, name: '', id: null, _cid: genCid() }]);
          setStatus('Landmark placed — give it a name.');
        }
      } else {
        showToastGlobal('Coordinate is outside the boundary!', 'error');
      }
    }
  }, [screenLocked, boundaryCoords, boundaryPointMode, isAdmin, boundaryPoints.length, setBaseLandmarks, setUserLandmarks, setBoundaryPoints, setStatus]);

  // Boundary polygon coords for react-leaflet
  const boundaryPolygons = boundaryCoords
    ? boundaryCoords.map(ring => ring.map(([lon, lat]) => [lat, lon]))
    : null;

  return (
    <div className="map-container">
      <div className={`lock-overlay ${screenLocked ? 'active' : ''}`}>
        <div className="lock-banner">Map interaction locked. Click &quot;Lock&quot; to unlock.</div>
      </div>
      <MapContainer
        center={[20, 0]}
        zoom={3}
        style={{ height: '100%', width: '100%' }}
        whenReady={(mapInstance) => {
          mapInstanceRef.current = mapInstance.target;
        }}
      >
        <MapRefSetter />
        <MapClickHandler onMapClick={handleMapClick} />

        <LayersControl position="topright">
          <LayersControl.BaseLayer name="Esri Satellite">
            <TileLayer
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              attribution="Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics"
              maxZoom={19}
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Google Satellite">
            <TileLayer
              url="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
              attribution="&copy; Google"
              maxZoom={20}
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer checked name="Google Hybrid">
            <TileLayer
              url="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"
              attribution="&copy; Google"
              maxZoom={20}
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="OpenStreetMap">
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution="&copy; OpenStreetMap contributors"
              maxZoom={19}
            />
          </LayersControl.BaseLayer>
        </LayersControl>

        {/* Boundary polygon */}
        {boundaryPolygons && (
          <Polygon
            positions={boundaryPolygons}
            pathOptions={{
              color: '#e94560',
              weight: 2.5,
              fillColor: '#e94560',
              fillOpacity: fillVisible ? 0.12 : 0,
            }}
          />
        )}

        {/* Nested boundary polygons */}
        {Object.entries(nestedBoundaries).map(([name, coords]) => (
          <Polygon
            key={name}
            positions={coords.map(c => [c.lat, c.lon])}
            pathOptions={{
              color: '#00bcd4',
              weight: 2,
              fillColor: '#00bcd4',
              fillOpacity: fillVisible ? 0.15 : 0,
            }}
          >
            <Tooltip permanent direction="center" className="nested-tooltip">{name}</Tooltip>
          </Polygon>
        ))}

        {/* Voronoi cells */}
        {voronoiCells.map((cell, i) => {
          const color = VORONOI_COLORS[i % VORONOI_COLORS.length];
          return cell.polygon.map((ring, ri) => (
            <Polygon
              key={`voronoi-${i}-${ri}`}
              positions={ring.map(([lat, lon]) => [lat, lon])}
              pathOptions={{
                color,
                weight: 2,
                fillColor: color,
                fillOpacity: fillVisible ? 0.15 : 0,
                dashArray: '5, 5',
              }}
            >
              <Tooltip direction="center" className="nested-tooltip">{cell.name || 'Unnamed'}</Tooltip>
            </Polygon>
          ));
        })}
      </MapContainer>
    </div>
  );
}

// Global toast function — will be set by App
let showToastGlobal = () => {};
export function setShowToastGlobal(fn) {
  showToastGlobal = fn;
}
