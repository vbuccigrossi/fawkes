"""
Tests for the ISOs and Images API endpoints.
"""

import pytest
import io


class TestISOsAPI:
    """Tests for /api/v1/isos endpoints."""

    def test_list_isos(self, client):
        """Test listing all ISOs."""
        response = client.get("/api/v1/isos/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_get_storage_info(self, client):
        """Test getting ISO storage info."""
        response = client.get("/api/v1/isos/storage/info")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data

    def test_get_nonexistent_iso(self, client):
        """Test getting a non-existent ISO."""
        response = client.get("/api/v1/isos/nonexistent.iso")
        assert response.status_code == 404

    def test_delete_nonexistent_iso(self, client):
        """Test deleting a non-existent ISO."""
        response = client.delete("/api/v1/isos/nonexistent.iso")
        assert response.status_code == 404


class TestImagesAPI:
    """Tests for /api/v1/images endpoints."""

    def test_list_images(self, client):
        """Test listing all disk images."""
        response = client.get("/api/v1/images/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_get_storage_info(self, client):
        """Test getting image storage info."""
        response = client.get("/api/v1/images/storage/info")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data

    def test_create_image(self, client, test_temp_dir):
        """Test creating a new disk image."""
        response = client.post(
            "/api/v1/images/create",
            json={
                "name": "test-image",
                "size": "1G",
                "format": "qcow2"
            }
        )
        # Should succeed or fail if qemu-img not available
        assert response.status_code in [200, 201, 500]

        if response.status_code in [200, 201]:
            data = response.json()
            assert data.get("success") is True
            # Try to clean up
            if "path" in data.get("data", {}):
                client.delete("/api/v1/images/", params={"path": data["data"]["path"]})

    def test_create_image_missing_fields(self, client):
        """Test creating an image with missing fields."""
        response = client.post(
            "/api/v1/images/create",
            json={"name": "test"}  # Missing size
        )
        # 422 for validation error, 409 for conflict (if image exists), 200 if defaults provided
        assert response.status_code in [200, 409, 422]

    def test_get_image_info(self, client):
        """Test getting image info."""
        response = client.get(
            "/api/v1/images/info",
            params={"path": "/nonexistent/path.qcow2"}
        )
        # Should fail for nonexistent path
        assert response.status_code in [404, 500]

    def test_delete_nonexistent_image(self, client):
        """Test deleting a non-existent image."""
        response = client.delete(
            "/api/v1/images/",
            params={"path": "/nonexistent/image.qcow2"}
        )
        assert response.status_code in [404, 500]

    def test_image_list_structure(self, client):
        """Test that image list has correct structure."""
        response = client.get("/api/v1/images/")
        assert response.status_code == 200
        data = response.json()

        for image in data["data"]:
            # Images should have basic info
            assert "path" in image or "filename" in image or "name" in image
