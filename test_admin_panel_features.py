# Tests for admin panel features including authentication, permissions, and audit logging
import pytest
from unittest.mock import patch
from app.models import AdminUser
from app.auth import create_test_token

@pytest.fixture
def admin_user():
    return AdminUser(username="test_admin", permissions=["admin"])

@pytest.fixture
def admin_token(admin_user):
    return create_test_token(admin_user)

def test_admin_login(admin_user):
    with patch("app.auth.authenticate_admin") as mock_auth:
        mock_auth.return_value = admin_user
        response = client.post("/admin/login", json={"username": "test_admin"})
        assert response.status_code == 200
        assert "token" in response.json()

def test_admin_permissions(admin_token):
    with patch("app.auth.verify_admin_token") as mock_verify:
        mock_verify.return_value = {"permissions": ["admin"]}
        response = client.get("/admin/permissions", headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
        assert "admin" in response.json()["permissions"]

def test_modify_permissions(admin_token):
    with patch("app.auth.verify_admin_token") as mock_verify:
        mock_verify.return_value = {"permissions": ["admin"]}
        response = client.post("/admin/permissions/modify", 
                             headers={"Authorization": f"Bearer {admin_token}"},
                             json={"user": "target_user", "permissions": ["read"]})
        assert response.status_code == 200

def test_audit_log_access(admin_token):
    with patch("app.auth.verify_admin_token") as mock_verify:
        mock_verify.return_value = {"permissions": ["admin"]}
        response = client.get("/admin/audit", headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)
