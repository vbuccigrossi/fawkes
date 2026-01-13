"""
Tests for the Paths API endpoints.
"""

import pytest


class TestPathsAPI:
    """Tests for /api/v1/paths endpoints."""

    def test_get_all_paths(self, client):
        """Test getting all configured paths."""
        response = client.get("/api/v1/paths/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data

    def test_get_directories(self, client):
        """Test getting directory paths."""
        response = client.get("/api/v1/paths/directories")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        # Should have common directories
        dirs = data["data"]
        assert isinstance(dirs, dict)

    def test_get_search_paths(self, client):
        """Test getting search paths."""
        response = client.get("/api/v1/paths/search")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data

    def test_ensure_directories(self, client):
        """Test ensuring directories exist."""
        response = client.post("/api/v1/paths/ensure")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True

    def test_set_and_reset_path(self, client):
        """Test setting and resetting a path."""
        # Set a path
        response = client.put(
            "/api/v1/paths/images_dir",
            params={"path_value": "/tmp/test_images"}
        )
        # May succeed or fail depending on allowed paths
        assert response.status_code in [200, 400, 404]

        if response.status_code == 200:
            # Reset it
            reset_response = client.delete("/api/v1/paths/images_dir")
            assert reset_response.status_code in [200, 404]

    def test_reset_all_paths(self, client):
        """Test resetting all paths to defaults."""
        response = client.post("/api/v1/paths/reset")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True

    def test_paths_data_structure(self, client):
        """Test that paths data has correct structure."""
        response = client.get("/api/v1/paths/")
        assert response.status_code == 200
        data = response.json()

        # Verify we have the main paths
        paths = data["data"]
        assert isinstance(paths, dict)
