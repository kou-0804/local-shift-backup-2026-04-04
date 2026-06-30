"""P4a: mount_spa same-origin serving + API-aware SPA fallback.

Built on an ISOLATED throwaway FastAPI app (not webapp.api.main) so the test
never reloads the real app module — reloading would swap main.app's identity
and desync the module-bound `app`/`get_db` references the rest of the suite
imported at collection time. We exercise mount_spa directly with a couple of
stand-in API routes that mirror the real namespace (/health JSON, /jobs 404).
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from webapp.api.static import mount_spa


@pytest.fixture()
def client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><body><div id="root"></div>'
        '<script src="/assets/app.js"></script></body></html>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('spa')", encoding="utf-8")
    (dist / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str):
        # Stand-in: any id is "missing" -> a genuine JSON 404 that the SPA
        # fallback must NOT swallow.
        raise HTTPException(status_code=404, detail="job not found")

    assert mount_spa(app, str(dist)) is True
    return TestClient(app)


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


def test_deep_api_path_with_no_route_404s_via_guard(client):
    # A path under an API prefix that matches no explicit route hits the catch-all,
    # whose API_PREFIXES guard 404s it instead of returning the SPA shell.
    r = client.get("/jobs/deep/extra/segments")
    assert r.status_code == 404
    assert 'id="root"' not in r.text


def test_mount_spa_noop_without_dist(tmp_path):
    app = FastAPI()
    assert mount_spa(app, None) is False
    assert mount_spa(app, str(tmp_path / "missing")) is False
