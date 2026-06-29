# tests/test_api.py
from fastapi.testclient import TestClient
from webapp.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
