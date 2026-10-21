from fastapi.testclient import TestClient

from chakshu import __version__
from chakshu.main import create_app


def test_healthz_reports_ok_and_version():
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
