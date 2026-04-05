from __future__ import annotations

import heapq
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from flask import Flask, jsonify, request
from flask_socketio import SocketIO

app = Flask(__name__)
app.config["SECRET_KEY"] = "ambulance-sim-secret"
socketio = SocketIO(app, cors_allowed_origins="*")


@dataclass(order=True)
class Incident:
    sort_index: tuple[int, float] = field(init=False, repr=False)
    priority: int
    created_at: float
    id: str
    lat: float
    lng: float
    severity: str
    status: str = "queued"
    assigned_ambulance_id: str | None = None
    assigned_hospital_id: str | None = None

    def __post_init__(self):
        self.sort_index = (self.priority, self.created_at)


class DispatchEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.incident_queue: list[Incident] = []
        self.incidents: dict[str, Incident] = {}
        self.alerts: list[dict[str, Any]] = []

        self.hospitals: list[dict[str, Any]] = [
            {"id": "HOSP-1", "name": "City General", "lat": 37.7749, "lng": -122.4194},
            {"id": "HOSP-2", "name": "North Medical", "lat": 37.7845, "lng": -122.4090},
            {"id": "HOSP-3", "name": "Bay Trauma Center", "lat": 37.7642, "lng": -122.4312},
        ]

        self.ambulances: list[dict[str, Any]] = []
        self._seed_ambulances(per_hospital=3)

    def _seed_ambulances(self, per_hospital: int):
        idx = 1
        for hospital in self.hospitals:
            for _ in range(per_hospital):
                self.ambulances.append(
                    {
                        "id": f"AMB-{idx}",
                        "hospital_id": hospital["id"],
                        "lat": hospital["lat"],
                        "lng": hospital["lng"],
                        "status": "idle",
                        "incident_id": None,
                        "eta_sec": 0,
                        "available_at": 0.0,
                    }
                )
                idx += 1

    @staticmethod
    def _distance_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
        r = 6371.0
        d_lat = math.radians(b_lat - a_lat)
        d_lng = math.radians(b_lng - a_lng)
        aa = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(a_lat))
            * math.cos(math.radians(b_lat))
            * math.sin(d_lng / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(aa), math.sqrt(1 - aa))
        return r * c

    @staticmethod
    def _severity_priority(severity: str) -> int:
        mapping = {"high": 0, "critical": 0, "medium": 1, "low": 2}
        return mapping.get(severity.lower(), 2)

    def _nearest_hospital(self, lat: float, lng: float) -> dict[str, Any]:
        return min(self.hospitals, key=lambda h: self._distance_km(lat, lng, h["lat"], h["lng"]))

    def _idle_ambulances(self) -> list[dict[str, Any]]:
        now = time.time()
        return [a for a in self.ambulances if a["status"] == "idle" and a["available_at"] <= now]

    def create_incident(self, lat: float, lng: float, severity: str) -> Incident:
        incident = Incident(
            priority=self._severity_priority(severity),
            created_at=time.time(),
            id=f"INC-{uuid.uuid4().hex[:8]}",
            lat=lat,
            lng=lng,
            severity=severity.lower(),
        )
        with self.lock:
            heapq.heappush(self.incident_queue, incident)
            self.incidents[incident.id] = incident
            self._push_alert("incident_created", incident)
            self._dispatch_queued_locked()
        return incident

    def _push_alert(self, kind: str, incident: Incident):
        self.alerts.append(
            {
                "ts": time.time(),
                "type": kind,
                "incident_id": incident.id,
                "severity": incident.severity,
                "status": incident.status,
            }
        )
        self.alerts = self.alerts[-100:]

    def _dispatch_queued_locked(self):
        while self.incident_queue:
            idle_units = self._idle_ambulances()
            if not idle_units:
                break

            incident = heapq.heappop(self.incident_queue)
            if incident.status != "queued":
                continue

            chosen = min(
                idle_units,
                key=lambda amb: self._distance_km(amb["lat"], amb["lng"], incident.lat, incident.lng),
            )

            nearest_hospital = self._nearest_hospital(incident.lat, incident.lng)
            dist_to_incident = self._distance_km(chosen["lat"], chosen["lng"], incident.lat, incident.lng)
            dist_to_hospital = self._distance_km(incident.lat, incident.lng, nearest_hospital["lat"], nearest_hospital["lng"])

            speed_kmph = 35.0
            eta_sec = int(((dist_to_incident + dist_to_hospital) / speed_kmph) * 3600)
            eta_sec = max(eta_sec, 60)

            chosen["status"] = "en_route"
            chosen["incident_id"] = incident.id
            chosen["eta_sec"] = eta_sec
            chosen["available_at"] = time.time() + eta_sec
            chosen["lat"] = incident.lat
            chosen["lng"] = incident.lng

            incident.status = "dispatched"
            incident.assigned_ambulance_id = chosen["id"]
            incident.assigned_hospital_id = nearest_hospital["id"]
            self._push_alert("ambulance_dispatched", incident)

    def refresh(self):
        with self.lock:
            now = time.time()
            for amb in self.ambulances:
                if amb["status"] == "en_route" and amb["available_at"] <= now:
                    incident_id = amb["incident_id"]
                    if incident_id and incident_id in self.incidents:
                        incident = self.incidents[incident_id]
                        incident.status = "completed"
                        self._push_alert("incident_completed", incident)

                    home = next(h for h in self.hospitals if h["id"] == amb["hospital_id"])
                    amb["lat"] = home["lat"]
                    amb["lng"] = home["lng"]
                    amb["status"] = "idle"
                    amb["incident_id"] = None
                    amb["eta_sec"] = 0

            self._dispatch_queued_locked()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            now = time.time()
            queued = sum(1 for i in self.incidents.values() if i.status == "queued")
            dispatched = sum(1 for i in self.incidents.values() if i.status == "dispatched")
            completed = sum(1 for i in self.incidents.values() if i.status == "completed")

            hospital_idle = {
                h["id"]: sum(
                    1
                    for amb in self.ambulances
                    if amb["hospital_id"] == h["id"] and amb["status"] == "idle" and amb["available_at"] <= now
                )
                for h in self.hospitals
            }

            return {
                "kpi": {
                    "queued": queued,
                    "dispatched": dispatched,
                    "completed": completed,
                    "total": len(self.incidents),
                    "available_ambulances": sum(1 for a in self.ambulances if a["status"] == "idle"),
                },
                "hospitals": self.hospitals,
                "ambulances": self.ambulances,
                "incidents": [
                    {
                        "id": i.id,
                        "lat": i.lat,
                        "lng": i.lng,
                        "severity": i.severity,
                        "status": i.status,
                        "assigned_ambulance_id": i.assigned_ambulance_id,
                        "assigned_hospital_id": i.assigned_hospital_id,
                    }
                    for i in self.incidents.values()
                ],
                "alerts": self.alerts[-30:],
            }


engine = DispatchEngine()


def tick_loop():
    while True:
        time.sleep(1)
        engine.refresh()
        socketio.emit("state_update", engine.snapshot())


@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/api/state")
def get_state():
    return jsonify(engine.snapshot())


@app.route("/api/incidents", methods=["POST"])
def create_incident():
    body = request.get_json(force=True)
    lat = float(body["lat"])
    lng = float(body["lng"])
    severity = str(body.get("severity", "low"))
    incident = engine.create_incident(lat, lng, severity)
    socketio.emit(
        "dispatch_event",
        {
            "incident_id": incident.id,
            "severity": incident.severity,
            "status": incident.status,
        },
    )
    return jsonify({"incident_id": incident.id, "status": incident.status}), 201


if __name__ == "__main__":
    threading.Thread(target=tick_loop, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
