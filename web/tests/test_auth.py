"""
Tests for the Authentication API endpoints.
"""

import pytest


class TestAuthAPI:
    """Tests for /api/v1/auth endpoints."""

    def test_login_valid_credentials(self, client):
        """Test login with valid credentials."""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        # API returns access_token not token
        assert "access_token" in data or "token" in data
        assert data.get("success") is True or "access_token" in data or "token" in data

    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials."""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "invalid", "password": "wrongpassword"}
        )
        assert response.status_code in [401, 403]

    def test_login_missing_username(self, client):
        """Test login with missing username."""
        response = client.post(
            "/api/v1/auth/login",
            json={"password": "admin"}
        )
        assert response.status_code == 422

    def test_login_missing_password(self, client):
        """Test login with missing password."""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin"}
        )
        assert response.status_code == 422

    def test_get_me_authenticated(self, client, auth_headers):
        """Test getting current user info when authenticated."""
        if not auth_headers:
            pytest.skip("No auth token available")
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "username" in data or "user" in data or "data" in data

    def test_get_me_unauthenticated(self, client):
        """Test getting current user info without authentication."""
        response = client.get("/api/v1/auth/me")
        assert response.status_code in [401, 403]

    def test_logout(self, client, auth_headers):
        """Test logout endpoint."""
        if not auth_headers:
            pytest.skip("No auth token available")
        response = client.post("/api/v1/auth/logout", headers=auth_headers)
        # Logout should succeed even if it's a no-op
        assert response.status_code in [200, 204]
