from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .domain import Job, Technician

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS technicians (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL,
  capacity_minutes INTEGER NOT NULL CHECK(capacity_minutes > 0)
);
CREATE TABLE IF NOT EXISTS technician_skills (
  technician_id INTEGER NOT NULL REFERENCES technicians(id), skill TEXT NOT NULL,
  PRIMARY KEY (technician_id, skill)
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, customer TEXT NOT NULL,
  urgency TEXT NOT NULL CHECK(urgency IN ('low','medium','high')), sla_due TEXT NOT NULL,
  latitude REAL NOT NULL, longitude REAL NOT NULL, required_skill TEXT NOT NULL,
  duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','assigned','completed')),
  assigned_to INTEGER REFERENCES technicians(id), version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES jobs(id),
  actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
        self.seed()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def seed(self) -> None:
        with self.connect() as connection:
            if connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]:
                return
            technicians = [
                (1, "Ayşe Demir", 39.925, 32.836, 360, ("network", "hardware")),
                (2, "Mert Kaya", 39.890, 32.808, 420, ("software", "network")),
                (3, "Selin Aras", 39.965, 32.790, 300, ("hardware", "electrical")),
            ]
            for technician_id, name, lat, lon, capacity, skills in technicians:
                connection.execute(
                    "INSERT INTO technicians VALUES (?, ?, ?, ?, ?)",
                    (technician_id, name, lat, lon, capacity),
                )
                connection.executemany(
                    "INSERT INTO technician_skills VALUES (?, ?)",
                    [(technician_id, skill) for skill in skills],
                )
            now = datetime.now(UTC)
            jobs = [
                (
                    1,
                    "Şube internet kesintisi",
                    "Kızılay Mağaza",
                    "high",
                    now - timedelta(hours=1),
                    39.920,
                    32.854,
                    "network",
                    90,
                ),
                (
                    2,
                    "POS yazılım güncellemesi",
                    "Bahçelievler Kafe",
                    "medium",
                    now + timedelta(hours=5),
                    39.925,
                    32.826,
                    "software",
                    60,
                ),
                (
                    3,
                    "Kamera görüntü sorunu",
                    "Çayyolu Depo",
                    "medium",
                    now + timedelta(hours=20),
                    39.879,
                    32.688,
                    "hardware",
                    120,
                ),
                (
                    4,
                    "Yeni priz hattı kontrolü",
                    "OSTİM Atölye",
                    "low",
                    now + timedelta(hours=30),
                    39.977,
                    32.748,
                    "electrical",
                    150,
                ),
                (
                    5,
                    "Kablosuz ağ kapsama",
                    "Ümitköy Ofis",
                    "high",
                    now + timedelta(hours=2),
                    39.897,
                    32.700,
                    "network",
                    100,
                ),
            ]
            connection.executemany(
                "INSERT INTO jobs("
                "id,title,customer,urgency,sla_due,latitude,longitude,required_skill,"
                "duration_minutes) VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (job_id, title, customer, urgency, due.isoformat(), lat, lon, skill, duration)
                    for job_id, title, customer, urgency, due, lat, lon, skill, duration in jobs
                ],
            )

    def jobs(self) -> list[Job]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY id").fetchall()
        return [
            Job(
                id=row["id"],
                title=row["title"],
                customer=row["customer"],
                urgency=row["urgency"],
                sla_due=datetime.fromisoformat(row["sla_due"]),
                latitude=row["latitude"],
                longitude=row["longitude"],
                required_skill=row["required_skill"],
                duration_minutes=row["duration_minutes"],
                status=row["status"],
                assigned_to=row["assigned_to"],
                version=row["version"],
            )
            for row in rows
        ]

    def technicians(self) -> list[Technician]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM technicians ORDER BY id").fetchall()
            skills = connection.execute("SELECT * FROM technician_skills").fetchall()
            committed_rows = connection.execute(
                "SELECT assigned_to, COALESCE(SUM(duration_minutes),0) total "
                "FROM jobs WHERE status='assigned' GROUP BY assigned_to"
            ).fetchall()
        skill_map: dict[int, list[str]] = {}
        for row in skills:
            skill_map.setdefault(row["technician_id"], []).append(row["skill"])
        committed = {row["assigned_to"]: row["total"] for row in committed_rows}
        return [
            Technician(
                id=row["id"],
                name=row["name"],
                skills=tuple(sorted(skill_map.get(row["id"], []))),
                latitude=row["latitude"],
                longitude=row["longitude"],
                capacity_minutes=row["capacity_minutes"],
                committed_minutes=committed.get(row["id"], 0),
            )
            for row in rows
        ]

    def assign(self, job_id: int, technician_id: int, expected_version: int, actor: str) -> None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None:
                raise LookupError("İş bulunamadı.")
            if job["status"] != "open":
                raise RuntimeError("İş artık açık değil.")
            if job["version"] != expected_version:
                raise RuntimeError("Kayıt başka bir kullanıcı tarafından değiştirildi.")
            skill = connection.execute(
                "SELECT 1 FROM technician_skills WHERE technician_id=? AND skill=?",
                (technician_id, job["required_skill"]),
            ).fetchone()
            technician = connection.execute(
                "SELECT capacity_minutes FROM technicians WHERE id=?", (technician_id,)
            ).fetchone()
            if technician is None:
                raise LookupError("Teknisyen bulunamadı.")
            if skill is None:
                raise ValueError("Teknisyen gerekli beceriye sahip değil.")
            committed = connection.execute(
                "SELECT COALESCE(SUM(duration_minutes),0) FROM jobs "
                "WHERE assigned_to=? AND status='assigned'",
                (technician_id,),
            ).fetchone()[0]
            if committed + job["duration_minutes"] > technician["capacity_minutes"]:
                raise ValueError("Teknisyenin vardiya kapasitesi yetersiz.")
            cursor = connection.execute(
                "UPDATE jobs SET assigned_to=?,status='assigned',version=version+1 "
                "WHERE id=? AND version=?",
                (technician_id, job_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Atama sırasında sürüm çakışması oluştu.")
            detail = json.dumps(
                {
                    "before": {"status": "open", "assigned_to": None},
                    "after": {"status": "assigned", "assigned_to": technician_id},
                    "expected_version": expected_version,
                },
                ensure_ascii=False,
            )
            connection.execute(
                "INSERT INTO audit_events(job_id,actor,action,detail,created_at) "
                "VALUES (?,?,?,?,?)",
                (job_id, actor, "assigned", detail, datetime.now(UTC).isoformat()),
            )

    def audit_events(self, limit: int = 20) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
