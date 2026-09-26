from pathlib import Path

from fastapi.testclient import TestClient

from sahapusulasi.api import create_app


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "test.db"))


def test_dashboard_and_plan_are_explainable(tmp_path: Path):
    test_client = client(tmp_path)
    dashboard = test_client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.headers["cache-control"] == "no-store"
    assert dashboard.headers["x-frame-options"] == "DENY"
    assert len(dashboard.json()["jobs"]) == 5
    assert dashboard.json()["jobs"][0]["priority"]["reasons"]

    plan = test_client.post("/api/plan")
    assert plan.status_code == 200
    assert len(plan.json()["suggestions"]) >= 3
    assert plan.json()["suggestions"][0]["reasons"]


def test_assignment_updates_version_capacity_and_audit(tmp_path: Path):
    test_client = client(tmp_path)
    suggestion = test_client.post("/api/plan").json()["suggestions"][0]
    before = test_client.get("/api/dashboard").json()
    selected = next(job for job in before["jobs"] if job["id"] == suggestion["job_id"])
    response = test_client.post(
        f"/api/jobs/{selected['id']}/assign",
        json={
            "technician_id": suggestion["technician_id"],
            "expected_version": selected["version"],
            "actor": "test planlayıcı",
        },
    )
    assert response.status_code == 200
    updated = next(job for job in response.json()["jobs"] if job["id"] == selected["id"])
    assert updated["status"] == "assigned"
    assert updated["version"] == selected["version"] + 1
    assert response.json()["audit"][0]["actor"] == "test planlayıcı"

    stale = test_client.post(
        f"/api/jobs/{selected['id']}/assign",
        json={
            "technician_id": suggestion["technician_id"],
            "expected_version": selected["version"],
            "actor": "test",
        },
    )
    assert stale.status_code == 409


def test_assignment_rejects_missing_job_technician_and_skill(tmp_path: Path):
    test_client = client(tmp_path)
    assert (
        test_client.post(
            "/api/jobs/999/assign",
            json={"technician_id": 1, "expected_version": 0, "actor": "test"},
        ).status_code
        == 404
    )
    assert (
        test_client.post(
            "/api/jobs/1/assign",
            json={"technician_id": 999, "expected_version": 0, "actor": "test"},
        ).status_code
        == 404
    )
    incompatible = test_client.post(
        "/api/jobs/2/assign", json={"technician_id": 1, "expected_version": 0, "actor": "test"}
    )
    assert incompatible.status_code == 422


def test_index_and_health(tmp_path: Path):
    test_client = client(tmp_path)
    assert test_client.get("/api/health").json() == {"status": "ok"}
    assert "Saha" in test_client.get("/").text
