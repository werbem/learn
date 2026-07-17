"""Integration tests for the FastAPI application."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthAPI:
    async def test_health_check(self, client: AsyncClient) -> None:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


class TestReportsAPI:
    async def test_create_report(self, client: AsyncClient) -> None:
        body = {
            "our_company": "公司A",
            "competitor_company": "公司B",
            "product": "产品X",
            "objective": "product_improvement",
        }
        resp = await client.post("/api/reports", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    async def test_create_report_invalid_input(self, client: AsyncClient) -> None:
        body = {
            "our_company": "",
            "competitor_company": "B",
            "product": "C",
            "objective": "invalid",
        }
        resp = await client.post("/api/reports", json=body)
        assert resp.status_code == 422

    async def test_get_report_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/reports/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    async def test_full_workflow(self, client: AsyncClient) -> None:
        """End-to-end: create → wait → retrieve."""
        body = {
            "our_company": "公司A",
            "competitor_company": "公司B",
            "product": "产品X",
            "objective": "feature_benchmark",
        }
        create_resp = await client.post("/api/reports", json=body)
        assert create_resp.status_code == 200
        task_id = create_resp.json()["task_id"]

        # Check progress
        progress_resp = await client.get(f"/api/tasks/{task_id}/progress")
        assert progress_resp.status_code == 200

        # Get final report
        report_resp = await client.get(f"/api/reports/{task_id}")
        assert report_resp.status_code == 200
        data = report_resp.json()
        assert data["our_company"] == "公司A"
        assert data["competitor_company"] == "公司B"
        assert data["product"] == "产品X"
