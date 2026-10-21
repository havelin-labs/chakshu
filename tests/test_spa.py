import httpx
import pytest
from fastapi import FastAPI

from chakshu.api.spa import mount_spa


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    return tmp_path


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        return await client.get(path)


async def test_client_routes_fall_back_to_index(dist):
    app = FastAPI()
    assert mount_spa(app, dist)

    assert (await _get(app, "/reviewers/payments")).text == "<div id=root></div>"
    assert (await _get(app, "/favicon.svg")).text == "<svg/>"
    assert (await _get(app, "/assets/app.js")).status_code == 200


async def test_api_paths_are_not_swallowed(dist):
    app = FastAPI()
    mount_spa(app, dist)

    assert (await _get(app, "/api/unknown")).status_code == 404
    assert (await _get(app, "/webhooks/github")).status_code in {404, 405}


async def test_paths_outside_dist_are_not_served(dist):
    app = FastAPI()
    mount_spa(app, dist)

    assert (await _get(app, "/../pyproject.toml")).text == "<div id=root></div>"


def test_missing_build_mounts_nothing(tmp_path):
    assert mount_spa(FastAPI(), tmp_path) is False
