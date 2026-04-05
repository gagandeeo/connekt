import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useMapState } from '../contexts/MapContext';
import {
  saveLandmarks, getSavedLandmarks, getCachedVoronoi,
  computeVoronoi as apiComputeVoronoi,
  getLandmarkUsers, promoteBase,
  promoteLandmarksToBase, adminUpdateLandmark,
} from '../api';

export default function Toolbar({ showToast }) {
  const { isAdmin } = useAuth();
  const {
    boundaryName, boundaryCoords,
    baseLandmarks, setBaseLandmarks,
    userLandmarks, setUserLandmarks,
    viewedUserLandmarks, setViewedUserLandmarks,
    showBase, setShowBase,
    showUser, setShowUser,
    fillVisible, setFillVisible,
    screenLocked, setScreenLocked,
    boundaryPointMode, setBoundaryPointMode,
    boundaryPoints, setBoundaryPoints,
    setNestedBoundaries,
    voronoiCells, setVoronoiCells,
    status, setStatus,
    setEditingNestedName,
    setShowVoronoiSpinner,
    mapRef,
  } = useMapState();

  const [saving, setSaving] = useState(false);
  const [userVersions, setUserVersions] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [promoting, setPromoting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Load landmark users when boundary loads (admin)
  useEffect(() => {
    if (boundaryName && isAdmin) {
      getLandmarkUsers(boundaryName).then(data => {
        setUserVersions(data.users || []);
      }).catch(console.error);
    } else {
      setUserVersions([]);
    }
    setSelectedUserId('');
  }, [boundaryName, isAdmin]);

  const refreshBaseLandmarks = useCallback(async () => {
    if (!boundaryName) return;
    try {
      const baseData = await getSavedLandmarks(boundaryName, 'base');
      setBaseLandmarks(
        (baseData.landmarks || []).map(lm => ({
          lat: lm.lat, lon: lm.lon, name: lm.name, id: lm.id,
        }))
      );
    } catch (err) {
      console.error('Error refreshing base:', err);
    }
  }, [boundaryName, setBaseLandmarks]);

  const loadCachedVoronoi = useCallback(async () => {
    if (!boundaryName || !isAdmin) {
      setVoronoiCells([]);
      return;
    }
    try {
      const data = await getCachedVoronoi(boundaryName);
      setVoronoiCells(data.cells?.length > 0 ? data.cells : []);
    } catch (err) {
      console.error('Error loading voronoi:', err);
    }
  }, [boundaryName, isAdmin, setVoronoiCells]);

  const computeAndDrawVoronoi = useCallback(async () => {
    if (!isAdmin || !boundaryName || !boundaryCoords) return;
    const namedLandmarks = baseLandmarks.filter(l => l.name);
    if (namedLandmarks.length < 2) {
      setVoronoiCells([]);
      return;
    }
    const landmarks = namedLandmarks.map(l => ({ lat: l.lat, lon: l.lon, name: l.name }));
    setShowVoronoiSpinner(true);
    try {
      const data = await apiComputeVoronoi(boundaryName, landmarks, boundaryCoords);
      if (data.ok && data.cells) {
        setVoronoiCells(data.cells);
      }
    } catch (err) {
      console.error('Voronoi computation error:', err);
    } finally {
      setShowVoronoiSpinner(false);
    }
  }, [isAdmin, boundaryName, boundaryCoords, baseLandmarks, setVoronoiCells, setShowVoronoiSpinner]);

  const handleSave = async () => {
    if (!boundaryName) return;

    if (isAdmin) {
      if (baseLandmarks.length === 0) return;
      const landmarks = baseLandmarks.map(l => ({
        lat: l.lat, lon: l.lon,
        name: l.name || `Unnamed (${l.lat.toFixed(6)}, ${l.lon.toFixed(6)})`,
      }));
      setSaving(true);
      try {
        const data = await saveLandmarks(boundaryName, landmarks, true);
        if (data.ok) {
          showToast(`Saved ${data.count} base landmarks!`, 'success');
          await refreshBaseLandmarks();
          await computeAndDrawVoronoi();
        } else {
          showToast(data.error || 'Failed to save base landmarks.', 'error');
        }
      } catch (err) {
        showToast('Error: ' + err.message, 'error');
      } finally {
        setSaving(false);
      }
      return;
    }

    if (userLandmarks.length === 0) return;
    const landmarks = userLandmarks.map(l => ({
      lat: l.lat, lon: l.lon,
      name: l.name || `Unnamed (${l.lat.toFixed(6)}, ${l.lon.toFixed(6)})`,
    }));
    setSaving(true);
    try {
      const data = await saveLandmarks(boundaryName, landmarks, false);
      if (data.ok) {
        showToast(`Saved ${data.count} landmarks as your version!`, 'success');
        if (Array.isArray(data.landmark_ids) && data.landmark_ids.length === userLandmarks.length) {
          setUserLandmarks(prev => prev.map((l, i) => ({ ...l, id: data.landmark_ids[i] })));
        }
      } else {
        showToast(data.error || 'Failed to save landmarks.', 'error');
      }
    } catch (err) {
      showToast('Error: ' + err.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleRefresh = async () => {
    if (!boundaryName) return;
    setRefreshing(true);
    try {
      await refreshBaseLandmarks();
      if (isAdmin) {
        await loadCachedVoronoi();
      } else {
        setVoronoiCells([]);
      }
      showToast(
        isAdmin ? 'Base landmarks and Voronoi updated.' : 'Base landmarks updated.',
        'success'
      );
    } catch (err) {
      showToast('Refresh failed: ' + err.message, 'error');
    } finally {
      setRefreshing(false);
    }
  };

  const handleUserVersionChange = async (userId) => {
    setSelectedUserId(userId);
    setViewedUserLandmarks([]);
    if (!userId) return;
    try {
      const data = await getSavedLandmarks(boundaryName, 'user', parseInt(userId));
      if (data.landmarks) {
        setViewedUserLandmarks(
          data.landmarks.filter(lm => lm.id != null).map(lm => ({
            lat: lm.lat, lon: lm.lon, name: lm.name, id: lm.id,
          }))
        );
        showToast(`Showing ${data.landmarks.length} landmarks from selected user`, 'success');
      }
    } catch (err) {
      console.error('Error loading user landmarks:', err);
    }
  };

  const handlePromote = async () => {
    if (!selectedUserId || !boundaryName) return;
    const userName = userVersions.find(u => String(u.id) === selectedUserId)?.username || 'user';
    if (!confirm(`Promote landmarks from ${userName} as the new base version?`)) return;

    setPromoting(true);
    try {
      const data = await promoteBase(boundaryName, parseInt(selectedUserId));
      if (data.ok) {
        showToast(`Promoted ${data.count} landmarks to base!`, 'success');
        setViewedUserLandmarks([]);
        setSelectedUserId('');
        await refreshBaseLandmarks();
        await computeAndDrawVoronoi();
      } else {
        showToast(data.error || 'Failed to promote', 'error');
      }
    } catch (err) {
      showToast('Error: ' + err.message, 'error');
    } finally {
      setPromoting(false);
    }
  };

  const toggleBoundaryMode = () => {
    const newMode = !boundaryPointMode;
    setBoundaryPointMode(newMode);
    if (newMode) {
      setStatus('Boundary mode — click to place points. Right-click to remove. Drag to move.');
    } else {
      setStatus(boundaryName ? `${boundaryName} — click to place landmarks` : '');
      setBoundaryPoints([]);
      setEditingNestedName(null);
    }
  };

  const landmarkCount = (() => {
    if (isAdmin) {
      const total = baseLandmarks.length;
      const named = baseLandmarks.filter(l => l.name).length;
      return total > 0 ? `${named}/${total} named (base)` : '';
    }
    const total = userLandmarks.length;
    const named = userLandmarks.filter(l => l.name).length;
    return total > 0 ? `${named}/${total} named` : '';
  })();

  const bpCount = boundaryPoints.length > 0 ? `${boundaryPoints.length} pts` : '';

  return (
    <div className="toolbar">
      <div className="toolbar-group">
        <button
          className="btn-sm btn-save"
          disabled={!boundaryName || saving || (isAdmin ? baseLandmarks.length === 0 : userLandmarks.length === 0)}
          onClick={handleSave}
        >
          {isAdmin ? 'Save Base' : 'Save Landmarks'}
        </button>
        <span className="landmark-count">{landmarkCount}</span>
      </div>
      <div className="toolbar-divider" />
      <div className="toolbar-group">
        <button
          className={`btn-sm btn-version ${showBase ? 'active' : ''}`}
          disabled={!boundaryName}
          onClick={() => setShowBase(!showBase)}
        >
          Base
        </button>
        {!isAdmin && (
          <button
            className={`btn-sm btn-version ${showUser ? 'active' : ''}`}
            disabled={!boundaryName}
            onClick={() => setShowUser(!showUser)}
          >
            My Landmarks
          </button>
        )}
        <button
          type="button"
          className="btn-sm btn-refresh"
          disabled={!boundaryName || refreshing}
          title="Reload base landmarks and Voronoi regions from server"
          onClick={handleRefresh}
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M23 4v6h-6" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
        </button>
      </div>
      <div className="toolbar-divider" />
      {isAdmin && (
        <>
          <div className="toolbar-group admin-group">
            <select
              value={selectedUserId}
              onChange={(e) => handleUserVersionChange(e.target.value)}
            >
              <option value="">-- User versions --</option>
              {userVersions.map(u => (
                <option key={u.id} value={u.id}>{u.username} ({u.count} landmarks)</option>
              ))}
            </select>
            <button
              className="btn-sm btn-promote"
              disabled={!selectedUserId || promoting}
              onClick={handlePromote}
            >
              Promote to Base
            </button>
          </div>
          <div className="toolbar-divider" />
        </>
      )}
      <div className="toolbar-group">
        {isAdmin && (
          <>
            <button
              className={`btn-sm btn-toggle ${boundaryPointMode ? 'active' : ''}`}
              disabled={!boundaryName}
              onClick={toggleBoundaryMode}
            >
              {boundaryPointMode ? 'Landmark Mode' : 'Boundary Mode'}
            </button>
            <span className="bp-count">{bpCount}</span>
          </>
        )}
      </div>
      <div className="toolbar-divider" />
      <div className="toolbar-group">
        <button
          className={`btn-sm btn-toggle ${!fillVisible ? 'active' : ''}`}
          disabled={!boundaryName}
          onClick={() => setFillVisible(!fillVisible)}
        >
          {fillVisible ? 'Hide Fill' : 'Show Fill'}
        </button>
        <button
          className={`btn-sm btn-lock ${screenLocked ? 'active' : ''}`}
          onClick={() => setScreenLocked(!screenLocked)}
        >
          {screenLocked ? 'Unlock' : 'Lock'}
        </button>
      </div>
      <span id="status">{status}</span>
    </div>
  );
}
