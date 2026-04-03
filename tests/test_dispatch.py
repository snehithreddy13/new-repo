import time
import unittest
from dataclasses import dataclass

from agents import Ambulance, EmergencyEvent
from dispatch_center import DispatchCenter


class FakeDB:
    def log_incident(self, **kwargs):
        pass

    def log_state_change(self, *args, **kwargs):
        pass

    def open_trip(self, **kwargs):
        pass

    def close_trip(self, **kwargs):
        pass

    def rollup_daily(self, **kwargs):
        pass


@dataclass
class FakeHospital:
    id: str
    node_id: str
    capacity: int = 2
    current_load: int = 0

    @property
    def has_capacity(self):
        return self.current_load < self.capacity


@dataclass
class FakeBuilding:
    id: str
    node_id: str


class FakeMap:
    def __init__(self):
        self.hospitals = [FakeHospital("H1", "N1"), FakeHospital("H2", "N2")]
        self.buildings = [FakeBuilding("B1", "N3"), FakeBuilding("B2", "N4")]

    def shortest_path(self, src, dst):
        return [src, dst] if src != dst else [src]

    def travel_time(self, src, dst):
        # deterministic pseudo-distance
        return 1 if src == dst else 2

    def nearest_hospital_by_time(self, node_id, hospitals):
        return hospitals[0]


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.map = FakeMap()
        self.ambulances = [
            Ambulance("AMB-1", self.map.hospitals[0].id, self.map.hospitals[0].node_id),
            Ambulance("AMB-2", self.map.hospitals[1].id, self.map.hospitals[1].node_id),
        ]
        self.center = DispatchCenter(self.map, self.ambulances, FakeDB())

    def test_priority_queue_critical_first(self):
        now = time.time()
        self.center.enqueue_incident(
            EmergencyEvent(1, now, "INC-MINOR", "N3", "MINOR", "H1")
        )
        self.center.enqueue_incident(
            EmergencyEvent(0, now, "INC-CRIT", "N4", "CRITICAL", "H1")
        )

        self.center.process_queue()
        assigned_ids = {a.assigned_incident_id for a in self.ambulances if a.assigned_incident_id}
        self.assertIn("INC-CRIT", assigned_ids)

    def test_minor_preferred_hospital_fallback_when_full(self):
        self.map.hospitals[0].current_load = self.map.hospitals[0].capacity
        selected = self.center.get_best_hospital("N3", "MINOR", "H1")
        self.assertNotEqual(selected.id, "H1")


if __name__ == "__main__":
    unittest.main()
