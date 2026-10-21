async def _csrf(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/session")).json()["csrf_token"]}


async def test_portal_endpoints_need_sign_in(client):
    for path in ("/api/runs", "/api/repos", "/api/reviewers"):
        assert (await client.get(path)).status_code == 401


async def test_settings_need_an_admin(client):
    assert (await client.get("/api/settings")).status_code == 401
    body = {"default_model": "sonnet", "max_usd_per_review": 2, "reviewers_repo": "chakshu-reviewers"}
    assert (await client.put("/api/settings", json=body, headers=await _csrf(client))).status_code == 401
