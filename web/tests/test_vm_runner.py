"""
Tests for the VM Runner API endpoints.
"""

import pytest


class TestVMRunnerAPI:
    """Tests for /api/v1/vm-runner endpoints."""

    def test_list_running_vms(self, client):
        """Test listing running preparation VMs."""
        response = client.get("/api/v1/vm-runner/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        assert "count" in data
        assert isinstance(data["data"], list)

    def test_list_agents(self, client):
        """Test listing available crash agents."""
        response = client.get("/api/v1/vm-runner/agents/list")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        assert "agents_directory" in data
        agents = data["data"]
        assert isinstance(agents, list)
        # Should have at least Windows and Linux agents
        platforms = [a["platform"] for a in agents]
        assert "windows" in platforms
        assert "linux" in platforms

    def test_agent_data_structure(self, client):
        """Test that agent data has correct structure."""
        response = client.get("/api/v1/vm-runner/agents/list")
        assert response.status_code == 200
        data = response.json()

        for agent in data["data"]:
            assert "name" in agent
            assert "filename" in agent
            assert "platform" in agent
            assert "exists" in agent

    def test_get_nonexistent_vm(self, client):
        """Test getting a non-existent VM."""
        response = client.get("/api/v1/vm-runner/nonexistent_vm_id")
        assert response.status_code == 404

    def test_stop_nonexistent_vm(self, client):
        """Test stopping a non-existent VM."""
        response = client.post("/api/v1/vm-runner/nonexistent_vm_id/stop")
        assert response.status_code == 404

    def test_start_vm_invalid_config(self, client):
        """Test starting a VM with invalid config."""
        response = client.post(
            "/api/v1/vm-runner/start",
            json={"config_id": "nonexistent_config_id"}
        )
        assert response.status_code == 404

    def test_start_vm_missing_config(self, client):
        """Test starting a VM without config_id."""
        response = client.post("/api/v1/vm-runner/start", json={})
        assert response.status_code == 422

    def test_copy_agents_invalid_config(self, client):
        """Test copying agents to non-existent config."""
        # This should still succeed as it creates the shared folder
        response = client.post(
            "/api/v1/vm-runner/agents/copy/nonexistent_config",
            params={"target_os": "both"}
        )
        # Should succeed as it just creates directories and copies files
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "copied" in data["data"]

    def test_copy_agents_target_os_options(self, client):
        """Test copying agents with different target OS options."""
        for target_os in ["windows", "linux", "both"]:
            response = client.post(
                "/api/v1/vm-runner/agents/copy/test_target_os",
                params={"target_os": target_os}
            )
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "copied" in data["data"]

    def test_shared_folder_nonexistent_vm(self, client):
        """Test accessing shared folder for non-existent VM."""
        response = client.get("/api/v1/vm-runner/nonexistent/shared")
        assert response.status_code == 404

    def test_upload_to_nonexistent_vm(self, client):
        """Test uploading to non-existent VM shared folder."""
        files = {"file": ("test.txt", b"test content", "text/plain")}
        response = client.post(
            "/api/v1/vm-runner/nonexistent/upload",
            files=files,
            data={"subpath": "uploads"}
        )
        assert response.status_code == 404

    def test_delete_from_nonexistent_vm(self, client):
        """Test deleting from non-existent VM shared folder."""
        response = client.delete("/api/v1/vm-runner/nonexistent/shared/test.txt")
        assert response.status_code == 404

    def test_snapshot_nonexistent_vm(self, client):
        """Test creating snapshot for non-existent VM."""
        response = client.post(
            "/api/v1/vm-runner/nonexistent/snapshot",
            json={"vm_id": "nonexistent", "snapshot_name": "test"}
        )
        assert response.status_code == 404


class TestVMRunnerIntegration:
    """Integration tests for VM Runner (require actual VM configs)."""

    @pytest.fixture
    def test_config_id(self, client, sample_vm_config):
        """Create a test config for VM runner tests."""
        config = sample_vm_config.copy()
        config["name"] = "VM Runner Test Config"
        response = client.post("/api/v1/vm-configs/", json=config)
        if response.status_code not in [200, 201]:
            pytest.skip("Could not create test config")
        config_id = response.json()["data"]["id"]
        yield config_id
        # Cleanup
        client.delete(f"/api/v1/vm-configs/{config_id}")

    def test_copy_agents_to_real_config(self, client, test_config_id):
        """Test copying agents to a real config."""
        response = client.post(
            f"/api/v1/vm-runner/agents/copy/{test_config_id}",
            params={"target_os": "both"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True or len(data["data"]["copied"]) > 0
        # Should have copied README at minimum
        assert "README.md" in data["data"]["copied"]
