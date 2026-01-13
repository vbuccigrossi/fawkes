"""
Tests for the VM Configs API endpoints.
"""

import pytest
import uuid


class TestVMConfigsAPI:
    """Tests for /api/v1/vm-configs endpoints."""

    def test_list_configs(self, client):
        """Test listing all VM configurations."""
        response = client.get("/api/v1/vm-configs/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        assert "count" in data

    def test_list_tags(self, client):
        """Test listing all VM config tags."""
        response = client.get("/api/v1/vm-configs/tags")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_create_config(self, client, sample_vm_config):
        """Test creating a new VM configuration."""
        config = sample_vm_config.copy()
        config["name"] = f"Test Config {uuid.uuid4().hex[:8]}"

        response = client.post("/api/v1/vm-configs/", json=config)
        assert response.status_code in [200, 201]
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        assert "id" in data["data"]

        # Store config ID for cleanup
        return data["data"]["id"]

    def test_get_config(self, client, sample_vm_config):
        """Test getting a specific VM configuration."""
        # First create a config
        config = sample_vm_config.copy()
        config["name"] = f"Test Get Config {uuid.uuid4().hex[:8]}"
        create_response = client.post("/api/v1/vm-configs/", json=config)

        if create_response.status_code not in [200, 201]:
            pytest.skip("Could not create config for test")

        config_id = create_response.json()["data"]["id"]

        # Now get it
        response = client.get(f"/api/v1/vm-configs/{config_id}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["name"] == config["name"]

        # Cleanup
        client.delete(f"/api/v1/vm-configs/{config_id}")

    def test_get_nonexistent_config(self, client):
        """Test getting a non-existent configuration."""
        response = client.get("/api/v1/vm-configs/nonexistent123")
        assert response.status_code == 404

    def test_update_config(self, client, sample_vm_config):
        """Test updating a VM configuration."""
        # First create a config
        config = sample_vm_config.copy()
        config["name"] = f"Test Update Config {uuid.uuid4().hex[:8]}"
        create_response = client.post("/api/v1/vm-configs/", json=config)

        if create_response.status_code not in [200, 201]:
            pytest.skip("Could not create config for test")

        config_id = create_response.json()["data"]["id"]

        # Update it
        update_data = {"name": "Updated Config Name", "memory": "4G"}
        response = client.put(f"/api/v1/vm-configs/{config_id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        # API returns updated_fields list, not actual values
        assert "name" in data["data"]["updated_fields"]
        assert "memory" in data["data"]["updated_fields"]

        # Cleanup
        client.delete(f"/api/v1/vm-configs/{config_id}")

    def test_delete_config(self, client, sample_vm_config):
        """Test deleting a VM configuration."""
        # First create a config
        config = sample_vm_config.copy()
        config["name"] = f"Test Delete Config {uuid.uuid4().hex[:8]}"
        create_response = client.post("/api/v1/vm-configs/", json=config)

        if create_response.status_code not in [200, 201]:
            pytest.skip("Could not create config for test")

        config_id = create_response.json()["data"]["id"]

        # Delete it
        response = client.delete(f"/api/v1/vm-configs/{config_id}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True

        # Verify it's gone
        get_response = client.get(f"/api/v1/vm-configs/{config_id}")
        assert get_response.status_code == 404

    def test_duplicate_config(self, client, sample_vm_config):
        """Test duplicating a VM configuration."""
        # First create a config
        config = sample_vm_config.copy()
        config["name"] = f"Test Dup Config {uuid.uuid4().hex[:8]}"
        create_response = client.post("/api/v1/vm-configs/", json=config)

        if create_response.status_code not in [200, 201]:
            pytest.skip("Could not create config for test")

        config_id = create_response.json()["data"]["id"]

        # Duplicate it
        response = client.post(
            f"/api/v1/vm-configs/{config_id}/duplicate",
            params={"new_name": "Duplicated Config"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        dup_id = data["data"]["id"]
        assert dup_id != config_id
        assert data["data"]["name"] == "Duplicated Config"

        # Cleanup both
        client.delete(f"/api/v1/vm-configs/{config_id}")
        client.delete(f"/api/v1/vm-configs/{dup_id}")

    def test_filter_by_tag(self, client, sample_vm_config):
        """Test filtering configs by tag."""
        # Create config with specific tag
        config = sample_vm_config.copy()
        config["name"] = f"Test Tag Filter {uuid.uuid4().hex[:8]}"
        config["tags"] = ["unique-test-tag-12345"]
        create_response = client.post("/api/v1/vm-configs/", json=config)

        if create_response.status_code not in [200, 201]:
            pytest.skip("Could not create config for test")

        config_id = create_response.json()["data"]["id"]

        # Filter by tag
        response = client.get("/api/v1/vm-configs/", params={"tag": "unique-test-tag-12345"})
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        # Should find at least the one we created
        assert len(data["data"]) >= 1
        assert any(c["id"] == config_id for c in data["data"])

        # Cleanup
        client.delete(f"/api/v1/vm-configs/{config_id}")

    def test_config_validation(self, client):
        """Test that invalid configs are rejected."""
        # Missing required fields
        invalid_config = {"description": "Missing name and disk_image"}
        response = client.post("/api/v1/vm-configs/", json=invalid_config)
        assert response.status_code == 422

    def test_config_data_structure(self, client, sample_vm_config):
        """Test that config data has correct structure."""
        config = sample_vm_config.copy()
        config["name"] = f"Test Structure {uuid.uuid4().hex[:8]}"
        create_response = client.post("/api/v1/vm-configs/", json=config)

        if create_response.status_code not in [200, 201]:
            pytest.skip("Could not create config for test")

        config_id = create_response.json()["data"]["id"]

        # Get and verify structure
        response = client.get(f"/api/v1/vm-configs/{config_id}")
        assert response.status_code == 200
        data = response.json()["data"]

        expected_fields = ["id", "name", "disk_image", "arch", "memory", "cpu_cores"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

        # Cleanup
        client.delete(f"/api/v1/vm-configs/{config_id}")
