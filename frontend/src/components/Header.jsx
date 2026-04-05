import { useState, useRef, useEffect } from 'react';
import L from 'leaflet';
import { useAuth } from '../contexts/AuthContext';
import { useMapState } from '../contexts/MapContext';
import { searchCity, fetchBoundary, getSavedLandmarks, getNestedBoundaries, getCachedVoronoi } from '../api';
import { isInsideBoundary } from '../utils/geometry';

export default function Header({ showToast, onInfoToggle, infoOpen }) {
  const { currentUser, isAdmin, logout } = useAuth();
  const {
    boundaryCoords, boundaryName,
    setBoundaryName, setBoundaryCoords,
    setBaseLandmarks, setUserLandmarks,
    setNestedBoundaries,
    setVoronoiCells,
    boundaryPointMode, setBoundaryPoints,
    setStatus, suggestions, setSuggestions,
    clearBoundary, mapRef,
  } = useMapState();

  const [cityInput, setCityInput] = useState('');
  const [coordInput, setCoordInput] = useState('');
  const [searching, setSearching] = useState(false);
  const [headerHidden, setHeaderHidden] = useState(false);
  const searchAreaRef = useRef(null);

  // Close suggestions on outside click
  useEffect(() => {
    const handler = (e) => {
      if (searchAreaRef.current && !searchAreaRef.current.contains(e.target)) {
        setSuggestions(null);
      }
    };
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, [setSuggestions]);

  const loadBoundaryData = async (coords, name) => {
    clearBoundary();
    setBoundaryName(name);
    setBoundaryCoords(coords);

    const map = mapRef.current;
    if (map) {
      const polygons = coords.map(ring => ring.map(([lon, lat]) => [lat, lon]));
      const bounds = L.latLngBounds(polygons.flat());
      map.fitBounds(bounds, { padding: [30, 30] });
    }

    setStatus(`${name} — click to place landmarks`);

    // Load base landmarks
    try {
      const baseData = await getSavedLandmarks(name, 'base');
      if (baseData.landmarks?.length > 0) {
        setBaseLandmarks(baseData.landmarks.map(lm => ({
          lat: lm.lat, lon: lm.lon, name: lm.name, id: lm.id,
        })));
      }
    } catch (err) {
      console.error('Error loading base landmarks:', err);
    }

    // Load user landmarks (non-admin)
    if (!isAdmin) {
      try {
        const userData = await getSavedLandmarks(name, 'user');
        if (userData.landmarks?.length > 0) {
          setUserLandmarks(userData.landmarks.map(lm => ({
            lat: lm.lat, lon: lm.lon, name: lm.name, id: lm.id,
          })));
        }
      } catch (err) {
        console.error('Error loading user landmarks:', err);
      }
    }

    // Load nested boundaries
    try {
      const nested = await getNestedBoundaries(name);
      setNestedBoundaries(nested);
    } catch (err) {
      console.error('Error loading nested boundaries:', err);
    }

    // Load voronoi (admin only)
    if (isAdmin) {
      try {
        const voronoiData = await getCachedVoronoi(name);
        if (voronoiData.cells?.length > 0) {
          setVoronoiCells(voronoiData.cells);
        }
      } catch (err) {
        console.error('Error loading voronoi:', err);
      }
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    setSuggestions(null);
    const city = cityInput.trim();
    if (!city) return;

    setSearching(true);
    setStatus('Searching...');
    try {
      const data = await searchCity(city);
      if (data.boundary) {
        await loadBoundaryData(data.boundary, data.name);
      } else if (data.suggestions) {
        setSuggestions(data.suggestions);
        setStatus('Select a place from the suggestions.');
      } else {
        setStatus('No results found.');
      }
    } catch (err) {
      setStatus('Error: ' + err.message);
    } finally {
      setSearching(false);
    }
  };

  const handleSuggestionClick = async (suggestion) => {
    setSuggestions(null);
    setCityInput(suggestion.display_name);
    setSearching(true);
    setStatus('Fetching boundary...');

    const map = mapRef.current;
    if (map) {
      map.flyTo([parseFloat(suggestion.lat), parseFloat(suggestion.lon)], 12, { duration: 1.5 });
    }

    try {
      const data = await fetchBoundary(suggestion);
      if (data.boundary) {
        await loadBoundaryData(data.boundary, data.name);
      } else {
        setStatus(data.error || 'No boundary found for this place.');
      }
    } catch (err) {
      setStatus('Error: ' + err.message);
    } finally {
      setSearching(false);
    }
  };

  const handleCoordSubmit = (e) => {
    e.preventDefault();
    const parts = coordInput.split(',').map(s => s.trim());
    if (parts.length !== 2) {
      setStatus('Enter coordinates as: Latitude, Longitude');
      return;
    }
    const lat = parseFloat(parts[0]);
    const lon = parseFloat(parts[1]);
    if (isNaN(lat) || isNaN(lon)) {
      setStatus('Enter valid latitude and longitude.');
      return;
    }
    if (!boundaryCoords) {
      setStatus('Search for a city first.');
      return;
    }

    if (isInsideBoundary(lat, lon, boundaryCoords)) {
      const map = mapRef.current;
      if (map) map.panTo([lat, lon]);

      if (boundaryPointMode) {
        setBoundaryPoints(prev => [...prev, { lat, lon }]);
        setStatus(`Boundary point placed at (${lat.toFixed(6)}, ${lon.toFixed(6)}).`);
      } else if (isAdmin) {
        setBaseLandmarks(prev => [...prev, { lat, lon, name: '', id: null }]);
        setStatus(`Base landmark placed at (${lat.toFixed(6)}, ${lon.toFixed(6)}) — give it a name.`);
      } else {
        setUserLandmarks(prev => [...prev, { lat, lon, name: '', id: null }]);
        setStatus(`Landmark placed at (${lat.toFixed(6)}, ${lon.toFixed(6)}) — give it a name.`);
      }
    } else {
      showToast('Coordinate is outside the boundary!', 'error');
      setStatus(`(${lat.toFixed(6)}, ${lon.toFixed(6)}) is outside the boundary.`);
    }
  };

  const handleLogout = () => {
    clearBoundary();
    logout();
  };

  if (headerHidden) {
    return (
      <div className="header-show-bar visible" onClick={() => {
        setHeaderHidden(false);
        setTimeout(() => mapRef.current?.invalidateSize(), 50);
      }}>
        <span>&#9660; Show header</span>
      </div>
    );
  }

  return (
    <header>
      <h1>Connekt</h1>
      <div className="search-area" ref={searchAreaRef}>
        <form className="search-form" onSubmit={handleSearch}>
          <input
            type="text"
            placeholder="Search for a city..."
            autoComplete="off"
            required
            value={cityInput}
            onChange={(e) => setCityInput(e.target.value)}
          />
          <button type="submit" disabled={searching}>Search</button>
        </form>
        {suggestions && (
          <div className="suggestions visible">
            {suggestions.length === 0 ? (
              <div className="suggestions-header">No results found</div>
            ) : (
              <>
                <div className="suggestions-header">No direct boundary found — select a place:</div>
                {suggestions.map((s, i) => (
                  <div
                    key={i}
                    className="suggestion-item"
                    onClick={() => handleSuggestionClick(s)}
                  >
                    {s.display_name}
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </div>
      <form className="coord-form" onSubmit={handleCoordSubmit}>
        <input
          type="text"
          placeholder="Lat, Lon"
          autoComplete="off"
          required
          value={coordInput}
          onChange={(e) => setCoordInput(e.target.value)}
        />
        <button type="submit" disabled={!boundaryName}>Pin</button>
      </form>
      <button
        className={`btn-info ${infoOpen ? 'active' : ''}`}
        title="Help & Info"
        onClick={onInfoToggle}
      >
        ?
      </button>
      {currentUser && (
        <div className="user-section" style={{ display: 'flex' }}>
          <span className="username">{currentUser.username}</span>
          <span className={`role-badge ${currentUser.role.toLowerCase()}`}>{currentUser.role}</span>
          <button className="btn-logout" onClick={handleLogout}>Logout</button>
        </div>
      )}
      <button
        className="header-toggle"
        title="Hide header"
        onClick={() => {
          setHeaderHidden(true);
          setTimeout(() => mapRef.current?.invalidateSize(), 50);
        }}
      >
        &#9650;
      </button>
    </header>
  );
}
