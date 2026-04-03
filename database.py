"""SQLite/SQLAlchemy persistence layer for simulation telemetry.

This module stores:
- incidents
- ambulance trips
- state transitions (for FSM auditing)
- daily aggregate logs
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class IncidentLog(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    preferred_hospital_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TripLog(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ambulance_id: Mapped[str] = mapped_column(String(64), index=True)
    incident_id: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hospital_reached: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class StateChangeLog(Base):
    __tablename__ = "state_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ambulance_id: Mapped[str] = mapped_column(String(64), index=True)
    from_state: Mapped[str] = mapped_column(String(64), nullable=False)
    to_state: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DailyLog(Base):
    __tablename__ = "daily_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    total_incidents: Mapped[int] = mapped_column(Integer, default=0)
    critical_incidents: Mapped[int] = mapped_column(Integer, default=0)
    minor_incidents: Mapped[int] = mapped_column(Integer, default=0)
    completed_trips: Mapped[int] = mapped_column(Integer, default=0)
    lives_saved: Mapped[int] = mapped_column(Integer, default=0)


@dataclass
class Database:
    db_url: str = "sqlite:///emergency_response.db"

    def __post_init__(self):
        self.engine = create_engine(self.db_url, future=True, connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self.SessionLocal()

    def log_incident(self, *, external_id: str, node_id: str, severity: str, preferred_hospital_id: str):
        with self.session() as s:
            s.add(
                IncidentLog(
                    external_id=external_id,
                    node_id=node_id,
                    severity=severity,
                    preferred_hospital_id=preferred_hospital_id,
                )
            )
            s.commit()

    def log_state_change(self, ambulance_id: str, from_state: str, to_state: str, reason: str):
        with self.session() as s:
            s.add(
                StateChangeLog(
                    ambulance_id=ambulance_id,
                    from_state=from_state,
                    to_state=to_state,
                    reason=reason,
                )
            )
            s.commit()

    def open_trip(self, *, ambulance_id: str, incident_id: str, severity: str, started_at: datetime):
        with self.session() as s:
            trip = TripLog(
                ambulance_id=ambulance_id,
                incident_id=incident_id,
                severity=severity,
                start_time=started_at,
            )
            s.add(trip)
            s.commit()

    def close_trip(
        self,
        *,
        ambulance_id: str,
        incident_id: str,
        hospital_reached: str,
        end_time: datetime,
        response_time_seconds: float,
    ):
        with self.session() as s:
            trip = (
                s.query(TripLog)
                .filter(TripLog.ambulance_id == ambulance_id, TripLog.incident_id == incident_id)
                .order_by(TripLog.id.desc())
                .first()
            )
            if trip:
                trip.end_time = end_time
                trip.hospital_reached = hospital_reached
                trip.response_time_seconds = response_time_seconds
            s.commit()

    def rollup_daily(self, *, total_incidents: int, critical_incidents: int, minor_incidents: int, completed_trips: int, lives_saved: int):
        today = date.today()
        with self.session() as s:
            rec = s.query(DailyLog).filter_by(day=today).first()
            if not rec:
                rec = DailyLog(day=today)
                s.add(rec)
            rec.total_incidents = total_incidents
            rec.critical_incidents = critical_incidents
            rec.minor_incidents = minor_incidents
            rec.completed_trips = completed_trips
            rec.lives_saved = lives_saved
            s.commit()
