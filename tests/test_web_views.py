def test_backend_root_is_not_a_web_route(client):
    response = client.get("/")

    assert response.status_code == 404
