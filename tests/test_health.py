def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_database_health(client):
    resp = client.get("/api/v1/database/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
