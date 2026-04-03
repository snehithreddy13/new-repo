"""Graph-based city map manager with traffic-aware edge weights."""

from __future__ import annotations

import random
from dataclasses import dataclass

import networkx as nx


@dataclass
class Building:
    id: str
    node_id: str


@dataclass
class HospitalNode:
    id: str
    node_id: str
    capacity: int
    current_load: int = 0

    @property
    def has_capacity(self) -> bool:
        return self.current_load < self.capacity


class MapManager:
    def __init__(self, cols: int = 11, rows: int = 9, spacing: int = 70):
        self.cols = cols
        self.rows = rows
        self.spacing = spacing
        self.graph = nx.Graph()
        self.pos: dict[str, tuple[float, float]] = {}

        self._build_grid_graph()
        self.buildings = self._spawn_buildings(100)
        self.hospitals = self._spawn_hospitals(5)

    def _node(self, c: int, r: int) -> str:
        return f"N{c}_{r}"

    def _build_grid_graph(self):
        for r in range(self.rows):
            for c in range(self.cols):
                node = self._node(c, r)
                x = 80 + c * self.spacing
                y = 80 + r * self.spacing
                self.graph.add_node(node)
                self.pos[node] = (x, y)

        for r in range(self.rows):
            for c in range(self.cols):
                here = self._node(c, r)
                for dc, dr in ((1, 0), (0, 1)):
                    nc, nr = c + dc, r + dr
                    if nc < self.cols and nr < self.rows:
                        there = self._node(nc, nr)
                        base_distance = self.spacing
                        traffic_density = random.uniform(0.6, 1.8)
                        speed = random.uniform(25, 45)
                        travel_time = (base_distance / speed) * traffic_density
                        self.graph.add_edge(
                            here,
                            there,
                            distance=base_distance,
                            traffic_density=traffic_density,
                            speed=speed,
                            weight=travel_time,
                        )

    def update_dynamic_traffic(self):
        """Perturb edge traffic to reflect changing road congestion over time."""
        for u, v, data in self.graph.edges(data=True):
            data["traffic_density"] = min(2.5, max(0.5, data["traffic_density"] + random.uniform(-0.07, 0.07)))
            data["weight"] = (data["distance"] / data["speed"]) * data["traffic_density"]

    def _spawn_buildings(self, n: int) -> list[Building]:
        nodes = list(self.graph.nodes)
        picks = random.sample(nodes, k=min(n, len(nodes)))
        return [Building(id=f"B{i+1}", node_id=node) for i, node in enumerate(picks)]

    def _spawn_hospitals(self, n: int) -> list[HospitalNode]:
        candidates = [node for node in self.graph.nodes if node not in {b.node_id for b in self.buildings[:20]}]
        picks = random.sample(candidates, k=min(n, len(candidates)))
        return [HospitalNode(id=f"H{i+1}", node_id=node, capacity=8) for i, node in enumerate(picks)]

    def shortest_path(self, src: str, dst: str) -> list[str]:
        return nx.shortest_path(self.graph, src, dst, weight="weight")

    def travel_time(self, src: str, dst: str) -> float:
        path = self.shortest_path(src, dst)
        t = 0.0
        for a, b in zip(path, path[1:]):
            t += self.graph[a][b]["weight"]
        return t

    def nearest_hospital_by_time(self, node_id: str, hospitals: list[HospitalNode]) -> HospitalNode:
        return min(hospitals, key=lambda h: self.travel_time(node_id, h.node_id))
