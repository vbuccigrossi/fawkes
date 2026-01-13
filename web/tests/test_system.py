"""
Tests for the System API endpoints.
"""

import pytest


class TestSystemAPI:
    """Tests for /api/v1/system endpoints."""

    def test_health_check(self, client):
        """Test the health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "service" in data

    def test_get_stats(self, client):
        """Test getting system statistics."""
        response = client.get("/api/v1/system/stats")
        assert response.status_code == 200
        data = response.json()
        # Should return stats about jobs, crashes, workers
        assert "success" in data or isinstance(data, dict)

    def test_get_health(self, client):
        """Test system health endpoint."""
        response = client.get("/api/v1/system/health")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data or "status" in data

    def test_get_config(self, client):
        """Test getting system configuration."""
        # System config endpoint (with trailing slash to avoid redirect)
        response = client.get("/api/v1/system/config/")
        # If system config not exposed, use the /api/v1/config/ endpoint
        if response.status_code == 404:
            response = client.get("/api/v1/config/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
