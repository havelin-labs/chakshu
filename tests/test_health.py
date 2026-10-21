from chakshu import __version__


async def test_healthz_reports_ok_and_version(client):
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


async def test_readyz_checks_the_database(client):
    response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
