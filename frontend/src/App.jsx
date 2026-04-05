import { useState } from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { MapProvider } from './contexts/MapContext';
import AuthModal from './components/AuthModal';
import Header from './components/Header';
import Toolbar from './components/Toolbar';
import MapView, { setShowToastGlobal } from './components/MapView';
import InfoCard from './components/InfoCard';
import NestedPanel from './components/NestedPanel';
import VoronoiSpinner from './components/VoronoiSpinner';
import Toast, { useToast } from './components/Toast';

function AppContent() {
  const { currentUser, loading } = useAuth();
  const [infoOpen, setInfoOpen] = useState(false);
  const { toast, showToast } = useToast();

  // Wire up global toast for MapView
  setShowToastGlobal(showToast);

  if (loading) return null;

  return (
    <>
      <AuthModal />
      {currentUser && (
        <>
          <Header
            showToast={showToast}
            onInfoToggle={() => setInfoOpen(!infoOpen)}
            infoOpen={infoOpen}
          />
          <Toolbar showToast={showToast} />
          <MapView />
          <InfoCard visible={infoOpen} onClose={() => setInfoOpen(false)} />
          <NestedPanel showToast={showToast} />
          <VoronoiSpinner />
        </>
      )}
      <Toast toast={toast} />
    </>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <MapProvider>
        <AppContent />
      </MapProvider>
    </AuthProvider>
  );
}
