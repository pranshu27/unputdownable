"""Health endpoint tests."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_ok():
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "Track A Agentic RAG"
    # Qdrant is down on this machine, but the app must still report healthy.
    assert body["qdrant"] in {"connected", "unavailable"}
