def test_home_dashboard_page_renders(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Backfill Native Lite" in response.text
    assert "Support-layer dashboard" in response.text
