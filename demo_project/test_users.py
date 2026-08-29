from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_create_user():
    # Bug: client sends "username" but the API model requires "email"
    response = client.post(
        "/users", json={"username": "test@example.com", "password": "secret123"}
    )
    assert response.status_code == 200
