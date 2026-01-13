"""
Tests for the Jobs, Crashes, and Workers API endpoints.
"""

import pytest


class TestJobsAPI:
    """Tests for /api/v1/jobs endpoints."""

    def test_list_jobs(self, client):
        """Test listing all jobs."""
        response = client.get("/api/v1/jobs/")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data or isinstance(data, list)

    def test_get_nonexistent_job(self, client):
        """Test getting a non-existent job."""
        response = client.get("/api/v1/jobs/nonexistent-job-id")
        # 404 for not found, 422 if API requires valid UUID format
        assert response.status_code in [404, 422]

    def test_create_job_missing_fields(self, client):
        """Test creating a job with missing fields."""
        response = client.post("/api/v1/jobs/", json={})
        assert response.status_code == 422

    def test_start_nonexistent_job(self, client):
        """Test starting a non-existent job."""
        response = client.post("/api/v1/jobs/nonexistent/start")
        # 404 for not found, 422 if API requires valid UUID format
        assert response.status_code in [404, 422]

    def test_stop_nonexistent_job(self, client):
        """Test stopping a non-existent job."""
        response = client.post("/api/v1/jobs/nonexistent/stop")
        # 404 for not found, 422 if API requires valid UUID format
        assert response.status_code in [404, 422]

    def test_pause_nonexistent_job(self, client):
        """Test pausing a non-existent job."""
        response = client.post("/api/v1/jobs/nonexistent/pause")
        # 404 for not found, 422 if API requires valid UUID format
        assert response.status_code in [404, 422]

    def test_delete_nonexistent_job(self, client):
        """Test deleting a non-existent job."""
        response = client.delete("/api/v1/jobs/nonexistent")
        # 404 for not found, 422 if API requires valid UUID format
        assert response.status_code in [404, 422]


class TestCrashesAPI:
    """Tests for /api/v1/crashes endpoints."""

    def test_list_crashes(self, client):
        """Test listing all crashes."""
        response = client.get("/api/v1/crashes/")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data or isinstance(data, list)

    def test_get_crash_summary(self, client):
        """Test getting crash summary statistics."""
        response = client.get("/api/v1/crashes/stats/summary")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_get_nonexistent_crash(self, client):
        """Test getting a non-existent crash."""
        response = client.get("/api/v1/crashes/nonexistent-crash-id")
        # 404 for not found, 422 if API requires valid UUID format
        assert response.status_code in [404, 422]

    def test_list_crashes_with_filters(self, client):
        """Test listing crashes with filters."""
        response = client.get(
            "/api/v1/crashes/",
            params={"limit": 10, "offset": 0}
        )
        assert response.status_code == 200

    def test_download_nonexistent_testcase(self, client):
        """Test downloading testcase for non-existent crash."""
        response = client.get("/api/v1/crashes/nonexistent/testcase")
        # 404 for not found, 422 if API requires valid UUID format
        assert response.status_code in [404, 422]

    def test_reproduce_nonexistent_crash(self, client):
        """Test reproducing a non-existent crash."""
        response = client.post("/api/v1/crashes/nonexistent/reproduce")
        # 404 for not found, 422 if API requires valid UUID format
        assert response.status_code in [404, 422]


class TestWorkersAPI:
    """Tests for /api/v1/workers endpoints."""

    def test_list_workers(self, client):
        """Test listing all workers."""
        response = client.get("/api/v1/workers/")
        # 200 for success, 400 if workers require coordinator mode
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            data = response.json()
            assert "data" in data or isinstance(data, list)

    def test_get_nonexistent_worker(self, client):
        """Test getting a non-existent worker."""
        response = client.get("/api/v1/workers/nonexistent-worker-id")
        # 404 for not found, 422 if API requires valid UUID format, 400 for coordinator mode
        assert response.status_code in [400, 404, 422]

    def test_add_worker_missing_fields(self, client):
        """Test adding a worker with missing fields."""
        response = client.post("/api/v1/workers/", json={})
        # 422 for validation error, 400 for coordinator mode
        assert response.status_code in [400, 422]

    def test_remove_nonexistent_worker(self, client):
        """Test removing a non-existent worker."""
        response = client.delete("/api/v1/workers/nonexistent")
        # 404 for not found, 422 if API requires valid UUID format, 400 for coordinator mode
        assert response.status_code in [400, 404, 422]

    def test_assign_worker_nonexistent(self, client):
        """Test assigning a non-existent worker."""
        response = client.post(
            "/api/v1/workers/nonexistent/assign",
            json={"job_id": "some-job"}
        )
        # 404 for not found, 422 if API requires valid UUID format, 400 for coordinator mode
        assert response.status_code in [400, 404, 422]
