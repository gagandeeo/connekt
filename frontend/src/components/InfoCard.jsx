export default function InfoCard({ visible, onClose }) {
  if (!visible) return null;

  return (
    <div className="info-card visible">
      <h2>
        Help &amp; Controls
        <button className="close-btn" onClick={onClose}>&times;</button>
      </h2>
      <section>
        <h3>Header</h3>
        <ul>
          <li><kbd>Search</kbd> &mdash; type a city or region name, then pick from suggestions to load its boundary on the map.</li>
          <li><kbd>Lat, Lon</kbd> + <kbd>Pin</kbd> &mdash; enter comma-separated coordinates to drop a landmark at that exact location.</li>
          <li><kbd>?</kbd> &mdash; opens this help card.</li>
          <li><kbd>Logout</kbd> &mdash; signs you out and returns to the login screen.</li>
          <li><kbd>&#9650;</kbd> &mdash; hides the header and toolbar for a full-screen map view. Click the <em>&quot;Show header&quot;</em> bar at the top to bring them back.</li>
        </ul>
      </section>
      <section>
        <h3>Toolbar</h3>
        <ul>
          <li><kbd>Save Landmarks</kbd> &mdash; saves all your placed landmarks for the current boundary. Each user has their own version.</li>
          <li><kbd>Base</kbd> &mdash; toggles visibility of the shared base landmarks (blue stars). These are read-only.</li>
          <li><kbd>My Landmarks</kbd> &mdash; toggles visibility of your personal landmarks (red stars). Click a red star to rename or delete it.</li>
          <li><kbd>&#8635;</kbd> (refresh) &mdash; reloads the base landmarks from the server.</li>
          <li><kbd>Hide Fill</kbd> / <kbd>Show Fill</kbd> &mdash; toggles polygon fill transparency while keeping edges visible.</li>
          <li><kbd>Lock</kbd> &mdash; locks the map to prevent accidental landmark placement. Click again to unlock.</li>
        </ul>
      </section>
      <section>
        <h3>Map</h3>
        <ul>
          <li><strong>Placing landmarks:</strong> click inside a loaded boundary to place a marker. It appears as a grey <kbd>?</kbd> until you name it, then becomes a red star.</li>
          <li><strong>Editing landmarks:</strong> click a red star to open its popup where you can rename or remove it.</li>
          <li><strong>Layer switcher</strong> (top-right corner) &mdash; change the map tile layer (satellite, hybrid, street). Tap the <kbd>&times;</kbd> or tap the map to close it.</li>
          <li><strong>Nested boundaries:</strong> cyan polygons with name labels that represent sub-regions within a city. These are view-only for normal users.</li>
        </ul>
      </section>
    </div>
  );
}
