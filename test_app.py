from app import add, app


def test_add():
    assert add(2, 3) == 5


def test_health_endpoint():
    client = app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_index_endpoint():
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
