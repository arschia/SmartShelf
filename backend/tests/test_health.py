def test_health_check(client):
    """Test that the /api/health endpoint returns 200 and {'status': 'ok'}."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
