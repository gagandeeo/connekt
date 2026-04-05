import { useMapState } from '../contexts/MapContext';

export default function VoronoiSpinner() {
  const { showVoronoiSpinner } = useMapState();

  if (!showVoronoiSpinner) return null;

  return (
    <div className="voronoi-spinner">
      <div className="spinner-content">
        <div className="spinner-icon" />
        <div>Computing Voronoi regions...</div>
      </div>
    </div>
  );
}
