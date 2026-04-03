"""Main simulation engine.

Runs at 60 FPS, updates traffic, spawns incidents via Poisson process,
and drives dispatch + FSM transitions.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass

import pygame

from agents import Ambulance, AmbulanceState, EmergencyEvent
from database import Database
from dispatch_center import DispatchCenter
from map_manager import MapManager

BLACK = (0, 0, 0)
ROAD = (78, 78, 78)
WHITE = (255, 255, 255)
YELLOW = (255, 220, 0)
BLUE = (70, 140, 255)
RED = (255, 40, 40)
CYAN = (60, 220, 255)
PANEL_BG = (18, 25, 40)


@dataclass
class EngineRuntime:
    dispatcher: DispatchCenter
    running: bool = True


class SimulationEngine:
    def __init__(self, width: int = 1280, height: int = 800):
        self.width = width
        self.height = height
        self.map = MapManager(cols=11, rows=9, spacing=65)
        self.db = Database("sqlite:///emergency_response.db")
        self.dispatcher = DispatchCenter(self.map, self._spawn_ambulances(), self.db)
        self.runtime = EngineRuntime(dispatcher=self.dispatcher)

        self.lambda_calls_per_second = 0.17
        self.next_spawn_at = time.time() + random.expovariate(self.lambda_calls_per_second)

        self.dispatcher.subscribe("incident_created", self._on_incident_created)

        self.vehicle_sprites = self._spawn_background_vehicles(55)
        self.incident_popups: list[dict] = []

    def _spawn_ambulances(self) -> list[Ambulance]:
        units = []
        i = 1
        for h in self.map.hospitals:
            for _ in range(3):
                units.append(Ambulance(id=f"AMB-{i}", base_hospital_id=h.id, current_node=h.node_id))
                i += 1
        return units

    def _spawn_background_vehicles(self, n: int):
        # White cars, yellow buses, blue motorcycles.
        lanes = [90, 220, 350, 480, 610]
        entries = []
        for _ in range(n):
            kind = random.choice(["car", "bus", "bike"])
            color = WHITE if kind == "car" else YELLOW if kind == "bus" else BLUE
            entries.append(
                {
                    "kind": kind,
                    "color": color,
                    "x": random.randint(30, 860),
                    "y": random.choice(lanes),
                    "speed": random.uniform(0.8, 2.4),
                }
            )
        return entries

    def _on_incident_created(self, payload: dict):
        event: EmergencyEvent = payload["event"]
        self.incident_popups.append({"node": event.node_id, "severity": event.severity, "t": time.time()})

    def _poisson_spawn_incident(self):
        now = time.time()
        if now < self.next_spawn_at:
            return

        self.next_spawn_at = now + random.expovariate(self.lambda_calls_per_second)
        building = random.choice(self.map.buildings)
        severity = "CRITICAL" if random.random() < 0.35 else "MINOR"
        preferred = random.choice(self.map.hospitals).id

        # Priority queue: lower number = higher priority
        priority = 0 if severity == "CRITICAL" else 1
        ev = EmergencyEvent(
            priority=priority,
            created_at_ts=now,
            incident_id=f"INC-{int(now * 1000)}",
            node_id=building.node_id,
            severity=severity,
            preferred_hospital_id=preferred,
        )
        self.dispatcher.enqueue_incident(ev)

    def _render_map(self, screen):
        screen.fill(BLACK)

        # Draw roads (edges)
        for u, v in self.map.graph.edges:
            x1, y1 = self.map.pos[u]
            x2, y2 = self.map.pos[v]
            pygame.draw.line(screen, ROAD, (x1, y1), (x2, y2), 16)
            pygame.draw.line(screen, WHITE, (x1, y1), (x2, y2), 2)

        # Buildings
        for b in self.map.buildings:
            x, y = self.map.pos[b.node_id]
            pygame.draw.rect(screen, (20, 170, 60), (x - 5, y - 5, 10, 10))

        # Hospitals
        for h in self.map.hospitals:
            x, y = self.map.pos[h.node_id]
            pygame.draw.rect(screen, (195, 195, 195), (x - 10, y - 10, 20, 20))
            pygame.draw.line(screen, RED, (x - 6, y), (x + 6, y), 3)
            pygame.draw.line(screen, RED, (x, y - 6), (x, y + 6), 3)

        # Traffic vehicles
        for veh in self.vehicle_sprites:
            w = 18 if veh["kind"] == "bus" else 12
            pygame.draw.rect(screen, veh["color"], (veh["x"], veh["y"], w, 6), border_radius=2)
            veh["x"] += veh["speed"]
            if veh["x"] > 880:
                veh["x"] = 25

        # Incident pulse + floating text
        now = time.time()
        self.incident_popups = [p for p in self.incident_popups if now - p["t"] < 2.8]
        for popup in self.incident_popups:
            x, y = self.map.pos[popup["node"]]
            age = now - popup["t"]
            radius = int(6 + age * 24)
            alpha = max(40, 255 - int(age * 85))
            s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (255, 0, 0, alpha), (radius, radius), radius, 2)
            screen.blit(s, (x - radius, y - radius))

    def _render_ambulances(self, screen, font):
        blink_on = int(time.time() * 6) % 2 == 0
        for amb in self.dispatcher.ambulances:
            x, y = self.map.pos[amb.current_node]
            pygame.draw.rect(screen, (245, 245, 245), (x - 8, y - 5, 16, 10), border_radius=2)
            light_color = RED if blink_on else CYAN
            pygame.draw.circle(screen, light_color, (x - 4, y - 5), 3)
            pygame.draw.circle(screen, CYAN if blink_on else RED, (x + 4, y - 5), 3)
            label = font.render("A", True, (0, 0, 0))
            screen.blit(label, (x - 4, y - 6))

    def _render_side_dashboard(self, screen, font, small_font):
        panel_x = 900
        pygame.draw.rect(screen, PANEL_BG, (panel_x, 0, self.width - panel_x, self.height))
        snap = self.dispatcher.snapshot()

        lines = [
            f"Active Emergencies: {snap['active_emergencies']}",
            f"Ambulance Availability: {snap['availability']}",
            f"Total Lives Saved: {snap['total_lives_saved']}",
            f"Critical / Minor: {snap['critical_incidents']} / {snap['minor_incidents']}",
        ]
        y = 20
        screen.blit(font.render("Status Dashboard", True, WHITE), (panel_x + 16, y))
        y += 36
        for line in lines:
            screen.blit(small_font.render(line, True, WHITE), (panel_x + 16, y))
            y += 24

        y += 8
        screen.blit(font.render("Hospital Idle Units", True, WHITE), (panel_x + 16, y))
        y += 28
        for hid, count in snap["hospital_idle"].items():
            screen.blit(small_font.render(f"{hid}: {count}", True, WHITE), (panel_x + 16, y))
            y += 22

        y += 12
        screen.blit(font.render("Alerts", True, WHITE), (panel_x + 16, y))
        y += 24
        for msg in reversed(snap["alerts"][-10:]):
            screen.blit(small_font.render(msg[:40], True, (255, 200, 200)), (panel_x + 16, y))
            y += 18

    def run(self):
        pygame.init()
        screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("High-Fidelity Emergency Dispatch Simulator")
        clock = pygame.time.Clock()
        font = pygame.font.SysFont("Arial", 22)
        small_font = pygame.font.SysFont("Arial", 16)

        while self.runtime.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.runtime.running = False

            self.map.update_dynamic_traffic()
            self._poisson_spawn_incident()
            self.dispatcher.process_queue()
            self.dispatcher.step_ambulances()

            self._render_map(screen)
            self._render_ambulances(screen, small_font)
            self._render_side_dashboard(screen, font, small_font)
            pygame.display.flip()
            clock.tick(60)

        pygame.quit()


def start_engine_thread() -> SimulationEngine:
    engine = SimulationEngine()
    thread = threading.Thread(target=engine.run, daemon=True)
    thread.start()
    return engine
