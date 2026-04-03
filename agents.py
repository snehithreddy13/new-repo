"""Simulation agents and finite-state machine implementation for ambulances."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AmbulanceState(str, Enum):
    IDLE = "IDLE"
    DISPATCHED_TO_PATIENT = "DISPATCHED_TO_PATIENT"
    PICKED_UP = "PICKED_UP"
    EN_ROUTE_TO_HOSPITAL = "EN_ROUTE_TO_HOSPITAL"
    DIVERTED = "DIVERTED"


@dataclass(order=True)
class EmergencyEvent:
    """Priority-queue event. Lower sort index = higher priority."""

    priority: int
    created_at_ts: float
    incident_id: str = field(compare=False)
    node_id: str = field(compare=False)
    severity: str = field(compare=False)
    preferred_hospital_id: str = field(compare=False)


@dataclass
class Ambulance:
    id: str
    base_hospital_id: str
    current_node: str
    state: AmbulanceState = AmbulanceState.IDLE
    assigned_incident_id: Optional[str] = None
    severity: Optional[str] = None
    route: list[str] = field(default_factory=list)
    route_index: int = 0
    pickup_time: Optional[datetime] = None
    dispatch_time: Optional[datetime] = None
    incident_created_at_ts: Optional[float] = None
    target_hospital_id: Optional[str] = None
    target_hospital_node: Optional[str] = None

    def transition(self, new_state: AmbulanceState):
        old = self.state
        self.state = new_state
        return old, new_state

    @property
    def available(self) -> bool:
        return self.state == AmbulanceState.IDLE

    def set_route(self, route: list[str]):
        self.route = route
        self.route_index = 0

    def step(self):
        """Move one node along the computed route."""
        if not self.route:
            return
        self.route_index = min(self.route_index + 1, max(0, len(self.route) - 1))
        self.current_node = self.route[self.route_index]

    @property
    def at_route_end(self) -> bool:
        return bool(self.route) and self.route_index >= len(self.route) - 1
