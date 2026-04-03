"""Dispatch center with observer pattern, priority queue, and rerouting logic."""

from __future__ import annotations

import heapq
import random
import time
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from agents import Ambulance, AmbulanceState, EmergencyEvent

if TYPE_CHECKING:
    from database import Database


class DispatchCenter:
    def __init__(self, city_map, ambulances: list[Ambulance], db: "Database"):
        self.city_map = city_map
        self.ambulances = ambulances
        self.db = db
        self.event_queue: list[EmergencyEvent] = []
        self.subscribers: dict[str, list[Callable[[dict], None]]] = defaultdict(list)

        self.total_lives_saved = 0
        self.total_incidents = 0
        self.critical_incidents = 0
        self.minor_incidents = 0
        self.completed_trips = 0
        self.alert_feed: list[str] = []
        self.hospital_release_schedule: list[tuple[float, str]] = []

    def subscribe(self, event_type: str, callback: Callable[[dict], None]):
        self.subscribers[event_type].append(callback)

    def notify(self, event_type: str, payload: dict):
        for cb in self.subscribers[event_type]:
            cb(payload)

    def enqueue_incident(self, event: EmergencyEvent):
        heapq.heappush(self.event_queue, event)
        self.total_incidents += 1
        if event.severity == "CRITICAL":
            self.critical_incidents += 1
        else:
            self.minor_incidents += 1

        self.db.log_incident(
            external_id=event.incident_id,
            node_id=event.node_id,
            severity=event.severity,
            preferred_hospital_id=event.preferred_hospital_id,
        )
        self.alert_feed.append(
            f"{datetime.utcnow().strftime('%H:%M:%S')} - {event.incident_id} @ {event.node_id} ({event.severity})"
        )
        self.notify("incident_created", {"event": event})

    def get_best_hospital(self, patient_node: str, severity: str, preferred_hospital_id: str):
        hospitals = self.city_map.hospitals
        if severity == "CRITICAL":
            return self.city_map.nearest_hospital_by_time(patient_node, hospitals)

        preferred = next((h for h in hospitals if h.id == preferred_hospital_id), None)
        if preferred and preferred.has_capacity:
            return preferred

        with_capacity = [h for h in hospitals if h.has_capacity]
        if with_capacity:
            return self.city_map.nearest_hospital_by_time(patient_node, with_capacity)

        return self.city_map.nearest_hospital_by_time(patient_node, hospitals)

    def _candidate_ambulances(self, severity: str) -> list[Ambulance]:
        if severity == "CRITICAL":
            return [
                a
                for a in self.ambulances
                if a.state == AmbulanceState.IDLE
                or (a.state == AmbulanceState.DISPATCHED_TO_PATIENT and a.severity == "MINOR")
            ]
        return [a for a in self.ambulances if a.state == AmbulanceState.IDLE]

    def _select_ambulance_for_event(self, event: EmergencyEvent) -> Ambulance | None:
        candidates = self._candidate_ambulances(event.severity)
        if not candidates:
            return None
        return min(candidates, key=lambda amb: self.city_map.travel_time(amb.current_node, event.node_id))

    def process_queue(self):
        if not self.event_queue:
            return
        event = heapq.heappop(self.event_queue)
        amb = self._select_ambulance_for_event(event)
        if not amb:
            heapq.heappush(self.event_queue, event)
            return

        if amb.state != AmbulanceState.IDLE and event.severity == "CRITICAL":
            old, new = amb.transition(AmbulanceState.DIVERTED)
            self.db.log_state_change(amb.id, old.value, new.value, "critical_interceptor_diversion")

        amb.assigned_incident_id = event.incident_id
        amb.severity = event.severity
        amb.dispatch_time = datetime.utcnow()
        amb.incident_created_at_ts = event.created_at_ts

        amb.set_route(self.city_map.shortest_path(amb.current_node, event.node_id))
        old, new = amb.transition(AmbulanceState.DISPATCHED_TO_PATIENT)
        self.db.log_state_change(amb.id, old.value, new.value, f"dispatch:{event.incident_id}")
        self.db.open_trip(
            ambulance_id=amb.id,
            incident_id=event.incident_id,
            severity=event.severity,
            started_at=amb.dispatch_time,
        )

        target_hospital = self.get_best_hospital(event.node_id, event.severity, event.preferred_hospital_id)
        amb.target_hospital_id = target_hospital.id
        amb.target_hospital_node = target_hospital.node_id

        self.notify("ambulance_dispatched", {"ambulance": amb, "event": event})

    def _release_hospital_capacity(self):
        now = time.time()
        pending = []
        for release_ts, hospital_id in self.hospital_release_schedule:
            if now >= release_ts:
                hospital = next(h for h in self.city_map.hospitals if h.id == hospital_id)
                hospital.current_load = max(0, hospital.current_load - 1)
            else:
                pending.append((release_ts, hospital_id))
        self.hospital_release_schedule = pending

    def step_ambulances(self):
        self._release_hospital_capacity()

        for amb in self.ambulances:
            if amb.state in (AmbulanceState.DISPATCHED_TO_PATIENT, AmbulanceState.DIVERTED):
                amb.step()
                if amb.at_route_end:
                    old, new = amb.transition(AmbulanceState.PICKED_UP)
                    amb.pickup_time = datetime.utcnow()
                    self.db.log_state_change(amb.id, old.value, new.value, "patient_picked_up")

                    hospital_node = amb.target_hospital_node or amb.current_node
                    amb.set_route(self.city_map.shortest_path(amb.current_node, hospital_node))
                    old, new = amb.transition(AmbulanceState.EN_ROUTE_TO_HOSPITAL)
                    self.db.log_state_change(amb.id, old.value, new.value, f"to_hospital:{amb.target_hospital_id}")

            elif amb.state == AmbulanceState.EN_ROUTE_TO_HOSPITAL:
                amb.step()
                if amb.at_route_end:
                    now = datetime.utcnow()
                    created_ts = amb.incident_created_at_ts if amb.incident_created_at_ts is not None else time.time()
                    response = max(0.0, now.timestamp() - created_ts)
                    self.total_lives_saved += 1
                    self.completed_trips += 1

                    hospital = next((h for h in self.city_map.hospitals if h.id == amb.target_hospital_id), None)
                    if hospital:
                        hospital.current_load += 1
                        self.hospital_release_schedule.append((time.time() + random.uniform(20, 40), hospital.id))

                    self.db.close_trip(
                        ambulance_id=amb.id,
                        incident_id=amb.assigned_incident_id or "UNKNOWN",
                        hospital_reached=amb.target_hospital_id or "UNKNOWN",
                        end_time=now,
                        response_time_seconds=response,
                    )
                    old, new = amb.transition(AmbulanceState.IDLE)
                    self.db.log_state_change(amb.id, old.value, new.value, "trip_complete_return_idle")

                    home = next(h for h in self.city_map.hospitals if h.id == amb.base_hospital_id)
                    amb.current_node = home.node_id
                    amb.set_route([])
                    amb.assigned_incident_id = None
                    amb.severity = None
                    amb.pickup_time = None
                    amb.dispatch_time = None
                    amb.incident_created_at_ts = None
                    amb.target_hospital_id = None
                    amb.target_hospital_node = None

        self.db.rollup_daily(
            total_incidents=self.total_incidents,
            critical_incidents=self.critical_incidents,
            minor_incidents=self.minor_incidents,
            completed_trips=self.completed_trips,
            lives_saved=self.total_lives_saved,
        )

    def snapshot(self) -> dict:
        availability = sum(1 for a in self.ambulances if a.state == AmbulanceState.IDLE)
        hospital_idle = {}
        for h in self.city_map.hospitals:
            hospital_idle[h.id] = sum(
                1 for a in self.ambulances if a.base_hospital_id == h.id and a.state == AmbulanceState.IDLE
            )

        return {
            "active_emergencies": len(self.event_queue),
            "availability": availability,
            "total_lives_saved": self.total_lives_saved,
            "critical_incidents": self.critical_incidents,
            "minor_incidents": self.minor_incidents,
            "hospital_idle": hospital_idle,
            "hospital_capacity": {h.id: {"load": h.current_load, "capacity": h.capacity} for h in self.city_map.hospitals},
            "alerts": self.alert_feed[-25:],
        }
