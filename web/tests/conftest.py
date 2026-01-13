"""
Pytest configuration and fixtures for Fawkes Web UI tests.
"""

import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from starlette.testclient import TestClient
from api.main import app


@pytest.fixture(scope="session")
def test_temp_dir():
    """Create a temporary directory for test files."""
    temp_dir = tempfile.mkdtemp(prefix="fawkes_test_")
    yield temp_dir
    # Cleanup after all tests
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth_token(client):
    """Get an authentication token for protected endpoints."""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    # Return None if login fails (some tests may not need auth)
    return None


@pytest.fixture
def auth_headers(auth_token):
    """Create authorization headers."""
    if auth_token:
        return {"Authorization": f"Bearer {auth_token}"}
    return {}


@pytest.fixture
def sample_vm_config():
    """Create a sample VM configuration for testing."""
    return {
        "name": "Test VM Config",
        "description": "A test VM configuration",
        "disk_image": "/tmp/test-disk.qcow2",
        "arch": "x86_64",
        "memory": "2G",
        "cpu_cores": 2,
        "tags": ["test", "unit-test"]
    }
