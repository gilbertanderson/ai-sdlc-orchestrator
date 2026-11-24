import time

from fastapi.testclient import TestClient

from sdlc_orchestrator.server import create_app


def _wait(client, run_id, status, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = client.get(f"/api/runs/{run_id}").json()
        if snap["status"] == status:
            return snap
        assert snap["status"] != "error", snap["error"]
        time.sleep(0.2)
    raise AssertionError(f"run never reached {status}")


def test_run_over_websocket():
    with TestClient(create_app()) as client:
        assert client.get("/api/health").json()["model"] == "offline-heuristics"
        run_id = client.post("/api/runs", json={"demo": True}).json()["id"]
        with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
            first = ws.receive_json()
            assert first["type"] == "snapshot"
            msg = first
            while not (msg["type"] == "status" and msg["status"] == "awaiting_review"):
                msg = ws.receive_json()
            assert msg["review"]["summary"]["title"]
            ws.send_json({"type": "review", "review": {"decision": "approve"}})
            while not (msg["type"] == "status" and msg["status"] == "done"):
                msg = ws.receive_json()
            assert msg["report"]["status"] == "approved"
        assert client.get("/api/runs").json()[0]["id"] == run_id


def test_review_over_http_and_validation():
    with TestClient(create_app()) as client:
        assert client.post("/api/runs", json={"repo": "/nope"}).status_code == 400
        run_id = client.post("/api/runs", json={"demo": True}).json()["id"]
        assert client.post(f"/api/runs/{run_id}/review", json={"decision": "maybe"}).status_code == 422
        _wait(client, run_id, "awaiting_review")
        assert client.post(f"/api/runs/{run_id}/review", json={"decision": "reject"}).status_code == 200
        snap = _wait(client, run_id, "done")
        assert snap["report"]["status"] == "rejected"
        assert client.post(f"/api/runs/{run_id}/review", json={}).status_code == 409
