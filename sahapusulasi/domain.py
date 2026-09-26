from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

Urgency = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class Job:
    id: int
    title: str
    customer: str
    urgency: Urgency
    sla_due: datetime
    latitude: float
    longitude: float
    required_skill: str
    duration_minutes: int
    status: str = "open"
    assigned_to: int | None = None
    version: int = 0


@dataclass(frozen=True, slots=True)
class Technician:
    id: int
    name: str
    skills: tuple[str, ...]
    latitude: float
    longitude: float
    capacity_minutes: int
    committed_minutes: int = 0


@dataclass(frozen=True, slots=True)
class Priority:
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Suggestion:
    job_id: int
    technician_id: int
    technician_name: str
    priority_score: int
    distance_km: float
    reasons: tuple[str, ...]


def utc_now() -> datetime:
    return datetime.now(UTC)


def priority_for(job: Job, now: datetime) -> Priority:
    if now.tzinfo is None or job.sla_due.tzinfo is None:
        raise ValueError("Tarihler saat dilimi içermelidir.")
    urgency_label, score = {
        "low": ("düşük", 10),
        "medium": ("orta", 25),
        "high": ("yüksek", 50),
    }[job.urgency]
    reasons = [f"{urgency_label} öncelik: +{score}"]
    hours = (job.sla_due - now).total_seconds() / 3600
    if hours < 0:
        overdue_points = min(140, 80 + math.ceil(abs(hours)) * 5)
        score += overdue_points
        reasons.append(f"SLA {math.ceil(abs(hours))} saat gecikti: +{overdue_points}")
    elif hours <= 2:
        score += 45
        reasons.append("SLA iki saat içinde: +45")
    elif hours <= 8:
        score += 25
        reasons.append("SLA sekiz saat içinde: +25")
    elif hours <= 24:
        score += 10
        reasons.append("SLA bugün: +10")
    else:
        reasons.append("SLA için 24 saatten fazla var: +0")
    return Priority(score, tuple(reasons))


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    if not all(math.isfinite(value) for value in (lat1, lon1, lat2, lon2)):
        raise ValueError("Koordinatlar sonlu olmalıdır.")
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def suggest_assignments(
    jobs: list[Job], technicians: list[Technician], now: datetime
) -> list[Suggestion]:
    remaining = {
        technician.id: technician.capacity_minutes - technician.committed_minutes
        for technician in technicians
    }
    locations = {
        technician.id: (technician.latitude, technician.longitude) for technician in technicians
    }
    ranked = sorted(
        (job for job in jobs if job.status == "open"),
        key=lambda job: (-priority_for(job, now).score, job.sla_due, job.id),
    )
    suggestions: list[Suggestion] = []
    for job in ranked:
        candidates: list[tuple[float, int, Technician]] = []
        for technician in technicians:
            if job.required_skill not in technician.skills:
                continue
            if remaining[technician.id] < job.duration_minutes:
                continue
            latitude, longitude = locations[technician.id]
            distance = distance_km(latitude, longitude, job.latitude, job.longitude)
            load_ratio = 1 - (remaining[technician.id] / technician.capacity_minutes)
            candidates.append((distance + load_ratio * 8, technician.id, technician))
        if not candidates:
            continue
        _, _, chosen = min(candidates, key=lambda item: (item[0], item[1]))
        latitude, longitude = locations[chosen.id]
        distance = distance_km(latitude, longitude, job.latitude, job.longitude)
        priority = priority_for(job, now)
        suggestions.append(
            Suggestion(
                job_id=job.id,
                technician_id=chosen.id,
                technician_name=chosen.name,
                priority_score=priority.score,
                distance_km=round(distance, 1),
                reasons=(
                    *priority.reasons,
                    f"Beceri eşleşti: {job.required_skill}",
                    f"Mesafe: {distance:.1f} km",
                ),
            )
        )
        remaining[chosen.id] -= job.duration_minutes
        locations[chosen.id] = (job.latitude, job.longitude)
    return suggestions
