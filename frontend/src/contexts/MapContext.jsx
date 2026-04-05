import { createContext, useContext, useState, useCallback, useRef } from 'react';

const MapContext = createContext(null);

export function MapProvider({ children }) {
  const [boundaryName, setBoundaryName] = useState(null);
  const [boundaryCoords, setBoundaryCoords] = useState(null);

  const [baseLandmarks, setBaseLandmarks] = useState([]);
  const [userLandmarks, setUserLandmarks] = useState([]);
  const [viewedUserLandmarks, setViewedUserLandmarks] = useState([]);

  const [showBase, setShowBase] = useState(true);
  const [showUser, setShowUser] = useState(true);
  const [fillVisible, setFillVisible] = useState(true);
  const [screenLocked, setScreenLocked] = useState(false);

  const [boundaryPointMode, setBoundaryPointMode] = useState(false);
  const [boundaryPoints, setBoundaryPoints] = useState([]);

  const [nestedBoundaries, setNestedBoundaries] = useState({});
  const [voronoiCells, setVoronoiCells] = useState([]);

  const [status, setStatus] = useState('');
  const [suggestions, setSuggestions] = useState(null);
  const [editingNestedName, setEditingNestedName] = useState(null);
  const [showVoronoiSpinner, setShowVoronoiSpinner] = useState(false);

  // Ref to the Leaflet map instance for imperative operations
  const mapRef = useRef(null);

  const clearBoundary = useCallback(() => {
    setBoundaryName(null);
    setBoundaryCoords(null);
    setBaseLandmarks([]);
    setUserLandmarks([]);
    setViewedUserLandmarks([]);
    setVoronoiCells([]);
    setBoundaryPoints([]);
    setBoundaryPointMode(false);
    setNestedBoundaries({});
    setEditingNestedName(null);
    setFillVisible(true);
  }, []);

  return (
    <MapContext.Provider
      value={{
        boundaryName, setBoundaryName,
        boundaryCoords, setBoundaryCoords,
        baseLandmarks, setBaseLandmarks,
        userLandmarks, setUserLandmarks,
        viewedUserLandmarks, setViewedUserLandmarks,
        showBase, setShowBase,
        showUser, setShowUser,
        fillVisible, setFillVisible,
        screenLocked, setScreenLocked,
        boundaryPointMode, setBoundaryPointMode,
        boundaryPoints, setBoundaryPoints,
        nestedBoundaries, setNestedBoundaries,
        voronoiCells, setVoronoiCells,
        status, setStatus,
        suggestions, setSuggestions,
        editingNestedName, setEditingNestedName,
        showVoronoiSpinner, setShowVoronoiSpinner,
        mapRef,
        clearBoundary,
      }}
    >
      {children}
    </MapContext.Provider>
  );
}

export function useMapState() {
  return useContext(MapContext);
}
