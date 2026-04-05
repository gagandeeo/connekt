import L from 'leaflet';

export function createUserLandmarkIcon(named) {
  const color = named ? '#e94560' : '#888';
  return L.divIcon({
    className: 'landmark-icon',
    html: `<div style="
      background: ${color};
      width: 24px; height: 24px;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 13px;
      border: 2px solid #fff;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
      color: #fff;
    ">${named ? '&#9733;' : '?'}</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -14],
  });
}

export function createBaseLandmarkIcon() {
  return L.divIcon({
    className: 'landmark-icon',
    html: `<div style="
      background: #3498db;
      width: 24px; height: 24px;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 13px;
      border: 2px solid #fff;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
      color: #fff;
    ">&#9733;</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -14],
  });
}

export function createEditableBaseLandmarkIcon(named) {
  const color = named ? '#3498db' : '#888';
  return L.divIcon({
    className: 'landmark-icon',
    html: `<div style="
      background: ${color};
      width: 24px; height: 24px;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 13px;
      border: 2px solid #fff;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
      color: #fff;
    ">${named ? '&#9733;' : '?'}</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -14],
  });
}

export function createViewedUserLandmarkIcon() {
  return L.divIcon({
    className: 'landmark-icon',
    html: `<div style="
      background: #9b59b6;
      width: 24px; height: 24px;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 13px;
      border: 2px solid #fff;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
      color: #fff;
    ">&#9733;</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -14],
  });
}

export function createBoundaryPointIcon(index) {
  return L.divIcon({
    className: 'landmark-icon',
    html: `<div style="
      background: #00bcd4;
      width: 22px; height: 22px;
      border-radius: 3px;
      display: flex; align-items: center; justify-content: center;
      font-size: 11px; font-weight: bold;
      border: 2px solid #fff;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
      color: #fff;
    ">${index + 1}</div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}
