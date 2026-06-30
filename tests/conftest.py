"""Shared test fixtures.

P4b adds role gates to /jobs, /rosters, /masters. The existing ~143 tests call
those endpoints without logging in, so by default we override ``current_user``
to return an admin — i.e. the legacy suite runs authenticated as admin. Tests
that exercise REAL auth (401/403 behaviour) opt out with ``@pytest.mark.real_auth``.
"""
import pytest

import webapp.api.main as main
from webapp.api.auth.deps import current_user

_ADMIN = {"id": 0, "login_id": "test-admin", "name": "test",
          "role": "admin", "disabled": False}


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_auth: run with the real auth dependency (no admin override)")


@pytest.fixture(autouse=True)
def _auth_as_admin(request):
    if request.node.get_closest_marker("real_auth"):
        yield
        return
    main.app.dependency_overrides[current_user] = lambda: dict(_ADMIN)
    try:
        yield
    finally:
        main.app.dependency_overrides.pop(current_user, None)
