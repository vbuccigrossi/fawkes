"""
Tests for the Architectures API endpoints.
"""

import pytest


class TestArchitecturesAPI:
    """Tests for /api/v1/architectures endpoints."""

    def test_list_architectures(self, client):
        """Test listing all supported architectures."""
        response = client.get("/api/v1/architectures/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        assert "total" in data
        # Should have common architectures
        arch_names = [a["name"] for a in data["data"]]
        assert "x86_64" in arch_names

    def test_list_architecture_families(self, client):
        """Test listing architecture families."""
        response = client.get("/api/v1/architectures/families")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "families" in data
        assert "data" in data
        # Should have x86 family
        assert "x86" in data["families"]

    def test_check_kvm_support(self, client):
        """Test KVM support check endpoint."""
        response = client.get("/api/v1/architectures/kvm/check")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        assert "kvm_available" in data["data"]
        assert "kvm_usable" in data["data"]

    def test_get_specific_architecture(self, client):
        """Test getting a specific architecture."""
        response = client.get("/api/v1/architectures/x86_64")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        arch = data["data"]
        assert arch["name"] == "x86_64"
        assert "qemu_binary" in arch
        assert "word_size" in arch

    def test_get_unknown_architecture(self, client):
        """Test getting an unknown architecture."""
        response = client.get("/api/v1/architectures/unknown_arch")
        assert response.status_code == 404

    def test_check_architecture_availability(self, client):
        """Test checking architecture QEMU availability."""
        response = client.get("/api/v1/architectures/x86_64/check")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        check = data["data"]
        assert "available" in check
        assert "qemu_binary" in check

    def test_architecture_data_structure(self, client):
        """Test that architecture data has correct structure."""
        response = client.get("/api/v1/architectures/")
        assert response.status_code == 200
        data = response.json()

        for arch in data["data"]:
            assert "name" in arch
            assert "display_name" in arch
            assert "qemu_binary" in arch
            assert "gdb_arch" in arch
            assert "word_size" in arch
            assert "endianness" in arch
            assert "family" in arch
            assert "available" in arch
            # Word size should be 32 or 64
            assert arch["word_size"] in [32, 64]
            # Endianness should be little or big
            assert arch["endianness"] in ["little", "big"]
