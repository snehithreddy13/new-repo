import React, { useEffect, useMemo, useState } from 'react';
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet';
import { icon } from 'leaflet';
import { io } from 'socket.io-client';
import 'leaflet/dist/leaflet.css';

const API_BASE = 'http://localhost:5000';

const hospitalIcon = icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconSize: [20, 32],
  iconAnchor: [10, 32]
});

const incidentIcon = icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
  iconSize: [20, 32],
  iconAnchor: [10, 32]
});

const ambulanceIcon = icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-green.png',
  iconSize: [20, 32],
  iconAnchor: [10, 32]
});

export default function App() {
  const [state, setState] = useState({
    kpi: { queued: 0, dispatched: 0, completed: 0, total: 0, available_ambulances: 0 },
    hospitals: [],
    ambulances: [],
    incidents: [],
    alerts: []
  });

  useEffect(() => {
    fetch(`${API_BASE}/api/state`)
      .then((res) => res.json())
      .then(setState)
      .catch(() => null);

    const socket = io(API_BASE);
    socket.on('state_update', setState);
    socket.on('dispatch_event', (evt) => {
      if (window?.alert) {
        window.alert(`Dispatch update: ${evt.incident_id} (${evt.severity}) -> ${evt.status}`);
      }
    });

    return () => socket.close();
  }, []);

  const center = useMemo(() => {
    if (state.hospitals.length) {
      return [state.hospitals[0].lat, state.hospitals[0].lng];
    }
    return [37.7749, -122.4194];
  }, [state.hospitals]);

  return (
    <div style={{ fontFamily: 'Arial, sans-serif', background: '#0f172a', color: '#e2e8f0', minHeight: '100vh' }}>
      <div style={{ padding: 16, borderBottom: '1px solid #334155' }}>
        <h2 style={{ margin: 0 }}>🚑 Ambulance Dispatch Simulator</h2>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, padding: 16 }}>
        <div style={{ background: '#111827', padding: 12, borderRadius: 12 }}>
          <MapContainer center={center} zoom={13} style={{ height: 600, borderRadius: 12 }}>
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

            {state.hospitals.map((h) => (
              <Marker key={h.id} position={[h.lat, h.lng]} icon={hospitalIcon}>
                <Popup>
                  <b>{h.name}</b>
                  <br />
                  {h.id}
                </Popup>
              </Marker>
            ))}

            {state.ambulances.map((a) => (
              <Marker key={a.id} position={[a.lat, a.lng]} icon={ambulanceIcon}>
                <Popup>
                  <b>{a.id}</b>
                  <br />
                  Status: {a.status}
                  <br />
                  Hospital: {a.hospital_id}
                </Popup>
              </Marker>
            ))}

            {state.incidents
              .filter((i) => i.status !== 'completed')
              .map((i) => (
                <Marker key={i.id} position={[i.lat, i.lng]} icon={incidentIcon}>
                  <Popup>
                    <b>{i.id}</b>
                    <br />
                    Severity: {i.severity}
                    <br />
                    Status: {i.status}
                  </Popup>
                </Marker>
              ))}
          </MapContainer>
        </div>

        <div style={{ display: 'grid', gap: 12 }}>
          <div style={{ background: '#111827', padding: 12, borderRadius: 12 }}>
            <h3 style={{ marginTop: 0 }}>Live KPI</h3>
            <p>Queued: {state.kpi.queued}</p>
            <p>Dispatched: {state.kpi.dispatched}</p>
            <p>Completed: {state.kpi.completed}</p>
            <p>Available Units: {state.kpi.available_ambulances}</p>
          </div>

          <div style={{ background: '#111827', padding: 12, borderRadius: 12 }}>
            <h3 style={{ marginTop: 0 }}>Recent Alerts</h3>
            <div style={{ maxHeight: 280, overflow: 'auto' }}>
              {state.alerts.slice().reverse().map((a, idx) => (
                <div key={`${a.incident_id}-${idx}`} style={{ padding: '6px 0', borderBottom: '1px solid #1f2937' }}>
                  {new Date(a.ts * 1000).toLocaleTimeString()} — {a.type} — {a.incident_id} ({a.severity})
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
