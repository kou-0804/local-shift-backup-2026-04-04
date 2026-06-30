import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><body><div id="root"></div>'
        '<script src="/assets/app.js"></script></body></html>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('spa')", encoding="utf-8")
    (dist / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    monkeypatch.setenv("SHIFT_FRONTEND_DIST", str(dist))
    # Import after env is set so config picks up the dist dir.
    import importlib
    import webapp.api.config as config
    importlib.reload(config)
    import webapp.api.main as main
    importlib.reload(main)
    yield TestClient(main.app)
    # Restore the unmounted app for the rest of the suite.
    importlib.reload(config)
    importlib.reload(main)


def test_root_serves_spa_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'id="root"' in r.text


def test_spa_query_route_serves_index(client):
    # ?view=masters is a client-side route — must still return index.html.
    r = client.get("/?view=masters")
    assert r.status_code == 200
    assert 'id="root"' in r.text


def test_unknown_spa_path_falls_back_to_index(client):
    r = client.get("/some/deep/client/route")
    assert r.status_code == 200
    assert 'id="root"' in r.text


def test_asset_is_served_with_js_mimetype(client):
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]


def test_root_level_static_file_is_served(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.content[:2] == b"\x00\x00"


def test_health_is_json_not_spa(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_unknown_api_route_is_404_json_not_index(client):
    # API namespace 404s must stay JSON 404 — they must NOT be swallowed by the
    # SPA fallback (otherwise the client can never detect a missing roster/job).
    r = client.get("/jobs/does-not-exist")
    assert r.status_code == 404
    assert 'id="root"' not in r.text
