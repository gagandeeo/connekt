import { useState, useEffect } from 'react';
import { useMapState } from '../contexts/MapContext';
import { getNestedBoundaries, saveNestedBoundary, deleteNestedBoundary as apiDeleteNested } from '../api';

export default function NestedPanel({ showToast }) {
  const {
    boundaryName, boundaryPointMode,
    boundaryPoints, setBoundaryPoints,
    nestedBoundaries, setNestedBoundaries,
    editingNestedName, setEditingNestedName,
    setStatus, mapRef,
  } = useMapState();

  const [nameInput, setNameInput] = useState('');

  useEffect(() => {
    if (editingNestedName) {
      setNameInput(editingNestedName);
    }
  }, [editingNestedName]);

  if (!boundaryPointMode) return null;

  const names = Object.keys(nestedBoundaries);

  const handleZoom = (name) => {
    const coords = nestedBoundaries[name];
    if (!coords || !mapRef.current) return;
    const bounds = coords.map(c => [c.lat, c.lon]);
    mapRef.current.fitBounds(bounds, { padding: [50, 50] });
  };

  const handleEdit = async (name) => {
    setBoundaryPoints([]);
    setEditingNestedName(name);
    setNameInput(name);

    const nested = await getNestedBoundaries(boundaryName);
    const coords = nested[name];
    if (coords) {
      setBoundaryPoints(coords.map(c => ({ lat: c.lat, lon: c.lon })));
    }

    // Remove the polygon temporarily
    setNestedBoundaries(prev => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    setStatus(`Editing "${name}" — move/add/remove points, then update.`);
  };

  const handleDelete = async (name) => {
    if (!confirm(`Delete nested boundary "${name}"?`)) return;
    try {
      const data = await apiDeleteNested(boundaryName, name);
      if (data.ok) {
        setNestedBoundaries(prev => {
          const next = { ...prev };
          delete next[name];
          return next;
        });
        if (editingNestedName === name) {
          setBoundaryPoints([]);
          setEditingNestedName(null);
        }
        showToast(`Deleted "${name}"`, 'success');
      } else {
        showToast(data.error || 'Failed to delete', 'error');
      }
    } catch (err) {
      showToast('Error: ' + err.message, 'error');
    }
  };

  const handleSave = async () => {
    const childName = nameInput.trim();
    if (!childName) {
      showToast('Enter a boundary name', 'error');
      return;
    }
    if (boundaryPoints.length < 3) {
      showToast('Place at least 3 boundary points', 'error');
      return;
    }

    const coords = boundaryPoints.map(bp => ({ lat: bp.lat, lon: bp.lon }));

    // If renaming, delete old first
    if (editingNestedName && editingNestedName !== childName) {
      await apiDeleteNested(boundaryName, editingNestedName);
    }

    try {
      const data = await saveNestedBoundary(boundaryName, childName, coords);
      if (data.ok) {
        setBoundaryPoints([]);
        setEditingNestedName(null);
        setNameInput('');
        setNestedBoundaries(prev => ({ ...prev, [childName]: coords }));
        showToast(`Saved boundary "${childName}"`, 'success');
        setStatus(`Boundary "${childName}" saved.`);
      } else {
        showToast(data.error || 'Failed to save', 'error');
      }
    } catch (err) {
      showToast('Error: ' + err.message, 'error');
    }
  };

  const handleCancel = () => {
    setBoundaryPoints([]);
    if (editingNestedName) {
      // Reload nested boundaries to restore the removed polygon
      getNestedBoundaries(boundaryName).then(nested => {
        setNestedBoundaries(nested);
      });
    }
    setEditingNestedName(null);
    setNameInput('');
  };

  const showCreateForm = boundaryPoints.length > 0 || editingNestedName;

  return (
    <div className="nested-panel visible">
      <h3>Nested Boundaries</h3>
      <div>
        {names.length === 0 ? (
          <div style={{ color: '#7a7a9e', fontSize: '0.82rem', marginBottom: 8 }}>
            {boundaryName ? 'No nested boundaries yet.' : 'Search for a city first.'}
          </div>
        ) : (
          names.map(name => (
            <div key={name} className="nested-list-item">
              <span className="name" onClick={() => handleZoom(name)}>{name}</span>
              <div className="actions">
                <button className="btn-edit" onClick={() => handleEdit(name)}>Edit</button>
                <button className="btn-delete" onClick={() => handleDelete(name)}>Delete</button>
              </div>
            </div>
          ))
        )}
      </div>
      {showCreateForm && (
        <div>
          <input
            type="text"
            placeholder="Boundary name..."
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
          />
          <button
            className={editingNestedName ? 'btn-update' : 'btn-create'}
            onClick={handleSave}
          >
            {editingNestedName ? 'Update Boundary' : 'Save Boundary'}
          </button>
          <button className="btn-cancel" onClick={handleCancel}>Cancel</button>
        </div>
      )}
    </div>
  );
}
