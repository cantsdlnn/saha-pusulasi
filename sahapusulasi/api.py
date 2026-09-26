from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi import Path as ApiPath
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .database import Database
from .domain import priority_for, suggest_assignments, utc_now

STATIC_DIR = Path(__file__).parent / "static"


class AssignmentRequest(BaseModel):
    technician_id: int = Field(gt=0)
    expected_version: int = Field(ge=0)
    actor: str = Field(default="planlayıcı", min_length=2, max_length=60)


def create_app(database_path: Path | None = None) -> FastAPI:
    selected_path = database_path or Path(os.getenv("SAHA_DB", "instance/saha-pusulasi.db"))
    database = Database(selected_path)
    app = FastAPI(
        title="Saha Pusulası",
        version="1.0.0",
        description="Açıklanabilir saha işi önceliklendirme ve insan onaylı atama demonstrasyonu.",
    )
    app.state.database = database

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    def dashboard_payload() -> dict[str, object]:
        now = utc_now()
        jobs = database.jobs()
        technicians = database.technicians()
        ranked_jobs = sorted(
            jobs,
            key=lambda job: (-priority_for(job, now).score, job.sla_due, job.id),
        )
        return {
            "generated_at": now.isoformat(),
            "jobs": [
                {
                    **asdict(job),
                    "sla_due": job.sla_due.isoformat(),
                    "priority": asdict(priority_for(job, now)),
                }
                for job in ranked_jobs
            ],
            "technicians": [asdict(technician) for technician in technicians],
            "audit": database.audit_events(),
        }

    @app.get("/api/dashboard")
    def dashboard() -> dict[str, object]:
        return dashboard_payload()

    @app.post("/api/plan")
    def plan() -> dict[str, object]:
        suggestions = suggest_assignments(database.jobs(), database.technicians(), utc_now())
        return {"suggestions": [asdict(suggestion) for suggestion in suggestions]}

    @app.post("/api/jobs/{job_id}/assign")
    def assign(
        job_id: Annotated[int, ApiPath(gt=0)], payload: AssignmentRequest
    ) -> dict[str, object]:
        try:
            database.assign(job_id, payload.technician_id, payload.expected_version, payload.actor)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return dashboard_payload()

    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
