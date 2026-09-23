"""SPEC acceptance scenario 1 against the real API and database.

Register two agents. One sends a task; the other claims and completes it; the
sender reads the result.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

pytestmark = pytest.mark.integration


def register(client: httpx.Client, name: str) -> tuple[str, dict[str, str]]:
    response = client.post("/agents", json={"name": name, "description": "integration test"})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["agent_id"] and data["token"]
    return data["agent_id"], {"Authorization": f"Bearer {data['token']}"}


def test_two_agents_exchange_task_and_result(client: httpx.Client):
    run = uuid.uuid4().hex[:8]
    _sender_id, sender = register(client, f"it-sender-{run}")
    recipient_id, recipient = register(client, f"it-uppercase-{run}")
    task_input = f"hello relay {run}"

    sent = client.post(
        "/tasks",
        headers={**sender, "Idempotency-Key": f"it-{run}"},
        json={"to": recipient_id, "input": task_input},
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["status"] == "queued"
    task_id = sent.json()["task_id"]

    claim = client.post("/tasks/claim", headers=recipient, json={"worker_id": f"it-{run}", "wait_seconds": 5})
    assert claim.status_code == 200, claim.text
    claimed = claim.json()
    assert claimed["task_id"] == task_id
    assert claimed["input"] == task_input
    assert claimed["attempt"] == 1

    in_flight = client.get(f"/tasks/{task_id}", headers=sender)
    assert in_flight.json()["status"] == "processing"

    output = task_input.upper()
    done = client.post(
        f"/tasks/{task_id}/complete",
        headers=recipient,
        json={"claim_token": claimed["claim_token"], "output": output},
    )
    assert done.status_code == 200, done.text
    assert done.json() == {"task_id": task_id, "status": "completed"}

    result = client.get(f"/tasks/{task_id}", headers=sender)
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "completed"
    assert body["output"] == output
    assert body["error"] is None
    assert body["attempt_count"] == 1
    assert body["finished_at"] is not None

    attempts = client.get(f"/tasks/{task_id}/attempts", headers=sender).json()["items"]
    assert [a["outcome"] for a in attempts] == ["completed"]
    assert "claim_token" not in attempts[0]

    sent_list = client.get("/tasks", headers=sender, params={"direction": "sent", "status": "completed"})
    assert task_id in {item["task_id"] for item in sent_list.json()["items"]}

    # A third agent cannot read the pair's task.
    _outsider_id, outsider = register(client, f"it-outsider-{run}")
    assert client.get(f"/tasks/{task_id}", headers=outsider).status_code == 404
