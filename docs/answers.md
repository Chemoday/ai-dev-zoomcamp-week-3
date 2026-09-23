# Homework 3 answers

Task: [`homework.md`](homework.md). How each answer was checked: [`homework-plan.md`](homework-plan.md).

| # | Question | Answer | Why |
|---|----------|--------|-----|
| 1 | Which description matches the project's architecture? | **Agents claim tasks from a DB through an HTTP API.** | There is no broker. Tasks are rows in SQLite (later PostgreSQL), and workers poll `POST /api/v1/tasks/claim`. |
| 2 | Which task status does the sender see after the recipient submits its result? | **`completed`** | The integration test (`tests/integration/test_task_flow.py`) asserts it. While the task is claimed, the sender sees `processing`. |
| 3 | Which Docker option publishes a container's port to your machine? | **`-p`** | `-p 8000:8000` publishes the port. `--expose` / `EXPOSE` only documents it. |
| 4 | Which hostname should the API use to connect to the `postgres` service in Docker Compose? | **`postgres`** | The service name is its DNS name on the compose network. `localhost` would be the API container itself. |
| 5 | Which Kubernetes resource keeps the requested number of application replicas running and manages updates? | **Deployment** | `k8s/20-app.yaml`: 2 replicas, rolling updates with readiness/liveness probes. PostgreSQL is a StatefulSet with a PVC. |
| 6 | What should happen if a test fails in the workflow? | **Keep the existing version running and stop the deployment.** | `build-deploy` has `needs: test`. With a deliberately failing test it never started, and the cluster kept serving `Agent Relay v2` on the same image. |

## Links

- Repository: <https://github.com/Chemoday/ai-dev-zoomcamp-week-3>
- PRs: [#1](https://github.com/Chemoday/ai-dev-zoomcamp-week-3/pull/1) Q2,
  [#2](https://github.com/Chemoday/ai-dev-zoomcamp-week-3/pull/2) Q3,
  [#3](https://github.com/Chemoday/ai-dev-zoomcamp-week-3/pull/3) Q4,
  [#4](https://github.com/Chemoday/ai-dev-zoomcamp-week-3/pull/4) Q5,
  [#5](https://github.com/Chemoday/ai-dev-zoomcamp-week-3/pull/5) Q6
- Green GitHub Actions run of the Q6 workflow: <https://github.com/Chemoday/ai-dev-zoomcamp-week-3/actions/runs/35862504762>
