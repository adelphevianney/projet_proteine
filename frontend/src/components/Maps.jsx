import { CircleMarker, MapContainer, Popup, TileLayer, useMapEvents } from "react-leaflet";

const TILE = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const ABIDJAN = [5.36, -4.01];

function Clicker({ onPick }) {
  useMapEvents({ click: (e) => onPick({ lat: +e.latlng.lat.toFixed(5), lng: +e.latlng.lng.toFixed(5) }) });
  return null;
}

// Placer un point en touchant la carte, ou avec la position du téléphone.
export function MapPicker({ value, onChange }) {
  const center = value?.lat ? [value.lat, value.lng] : ABIDJAN;
  const locate = () => navigator.geolocation?.getCurrentPosition(
    (p) => onChange({ lat: +p.coords.latitude.toFixed(5), lng: +p.coords.longitude.toFixed(5) }),
    () => alert("Position indisponible : touchez la carte pour placer le point."));
  return (
    <div>
      <MapContainer center={center} zoom={value?.lat ? 13 : 10} className="map">
        <TileLayer url={TILE} attribution={ATTR} />
        <Clicker onPick={onChange} />
        {value?.lat && <CircleMarker center={[value.lat, value.lng]} radius={10} pathOptions={{ color: "#1f6f43" }} />}
      </MapContainer>
      <div className="row space">
        <small className="muted">{value?.lat ? `${value.lat}, ${value.lng}` : "Touchez la carte pour placer le lieu"}</small>
        <button type="button" className="btn ghost small" onClick={locate}>Ma position</button>
      </div>
    </div>
  );
}

export function MapView({ points, center }) {
  const c = center?.lat ? [center.lat, center.lng] : points[0] ? [points[0].lat, points[0].lng] : ABIDJAN;
  return (
    <MapContainer center={c} zoom={10} className="map">
      <TileLayer url={TILE} attribution={ATTR} />
      {center?.lat && <CircleMarker center={[center.lat, center.lng]} radius={7}
                                    pathOptions={{ color: "#1d4ed8", fillOpacity: 0.8 }}><Popup>Vous</Popup></CircleMarker>}
      {points.filter((p) => p.lat).map((p) => (
        <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={9} pathOptions={{ color: "#b45309" }}>
          <Popup>{p.label}</Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
