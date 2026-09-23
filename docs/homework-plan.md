# Homework 3 plan: Test, Containerize, and Deploy Agent Relay

Source of the task: [`docs/homework.md`](homework.md). Starter code:
[alexeygrigorev/agent-relay](https://github.com/alexeygrigorev/agent-relay)
(imported with its history; kept as the `upstream` remote).

Status legend: `[ ]` todo, `[x]` done, `[~]` in progress / blocked.

## 0. Repository setup

- [x] Init git, base `main` on the starter history, add `origin`
      (`Chemoday/ai-dev-zoomcamp-week-3`) and `upstream` (starter) remotes
- [x] Ignore local Claude Code state (`settings.local.json`, lock file)
- [x] Commit course docs, this plan, and the git-ops skill; push to `origin/main`

## Environment / tooling

| Tool      | Needed for | State at start                     |
|-----------|------------|------------------------------------|
| `uv`      | Q1–Q2      | installed (0.12)                   |
| `docker`  | Q3–Q6      | native docker-ce 24 in WSL (no systemd); start with `sudo service docker start` |
| `kind`    | Q5–Q6      | v0.33 installed to `~/.local/bin`; works after WSL upgrade (cgroup v2) |
| `kubectl` | Q5–Q6      | v1.37 installed to `~/.local/bin`  |
| `act`     | Q6         | v0.2.89 installed to `~/.local/bin`; runner image pinned in `.actrc` |

### Resolved: kind on old WSL (cgroup v1)

`kind create cluster` failed: node PID 1 exits with *Failed to mount cgroup v1
hierarchy* (inbox WSL, kernel 5.10.16, Docker on cgroup v1). Fix chosen:
`wsl --update`, `C:\Users\Alex\.wslconfig` → `kernelCommandLine = cgroup_no_v1=all`,
`wsl --shutdown`, then `sudo service docker start` and verify
`docker info` reports cgroup v2. **Done:** kernel 6.18, Docker on cgroup v2,
`kind create cluster --name agent-relay` succeeds.

### Resolved: PR creation

The fine-grained token has full repo permissions, but GitHub GraphQL rejects it
(`gh pr create` → *Resource not accessible by personal access token*). PRs are
created and merged through REST (`gh api …/pulls`, `…/pulls/N/merge`). Q2–Q5
were merged as PRs #1–#4 with merge commits (rebase-merge would rewrite the
stacked branches).

## Q1. Understand the project

- [x] `uv sync`, run `uv run pytest -q` (starter tests) — 4 passed
- [x] Run `uv run uvicorn main:app`, open dashboard, run the uppercase worker
- [x] Answer: architecture is **agents claim tasks from a DB through an HTTP API**
      (no broker; tasks are rows in SQLite, workers long-poll `POST /tasks/claim`)

## Q2. Register agents + integration test

- [x] Walk through SPEC acceptance scenario 1 with curl against the live server
      (register sender + recipient, send task, claim, complete, sender reads result)
- [~] Check the task in the dashboard (manual: paste an agent token into the dashboard)
- [x] `tests/integration/test_task_flow.py`: talks HTTP (httpx) to a real running
      API at `RELAY_BASE_URL` (default `http://127.0.0.1:8000`) — no TestClient,
      no DB mocking; skipped cleanly when no server is reachable so plain
      `pytest` still works; register a `integration` pytest marker
- [x] Also assert attempts history (`outcome == completed`) and auth boundary
      (third agent gets 404)
- [x] Answer: sender sees **`completed`** (it sees `processing` while the task is claimed)

## Q3. Dockerfile

- [x] Multi-stage `Dockerfile` using `uv` (deps layer cached from `uv.lock`,
      non-root user, `uvicorn main:app --host 0.0.0.0 --port 8000`),
      `HEALTHCHECK` on `/health`, plus `.dockerignore`
- [x] `docker build -t agent-relay:local .` (210 MB, runs as uid 10001)
- [x] `docker run -p 8000:8000 -v agent-relay-data:/app/data agent-relay:local`, integration test passes
- [x] Answer: **`-p`** (`--expose` only documents the port; it does not publish it)

## Q4. PostgreSQL + Docker Compose

- [x] Port the storage seam to PostgreSQL while keeping SQLite working:
  - `database.py`: dialect-aware engine; `immediate_transaction()` becomes a
    plain transaction on PostgreSQL
  - `storage.py`: claim uses `SELECT ... FOR UPDATE SKIP LOCKED`; heartbeat /
    terminal / recovery lock their rows with `FOR UPDATE`; idempotent task
    creation handles the unique-constraint race
  - Starter test suite passes against **both** SQLite and PostgreSQL (5/5 each,
    incl. a new concurrent-idempotency test that reproduces the PG race)
- [x] `compose.yaml`: services `postgres` (named volume, `pg_isready`
      healthcheck) and `api` (`RELAY_DATABASE_URL=postgresql+psycopg://…@postgres:5432/…`,
      `depends_on: condition: service_healthy`)
- [x] `docker compose up --build`, run integration test (1 passed)
- [x] Prove data is in PostgreSQL (`docker compose exec postgres psql … -c 'select … from tasks'`)
- [x] Answer: **`postgres`** (the service name is its DNS name on the compose network;
      `localhost` would be the API container itself). Data survives `down`/`up`.

## Q5. Kubernetes with kind

- [x] Install kind + kubectl; `kind create cluster --name agent-relay`
- [x] `k8s/` manifests (applied in file-name order):
  - `00-namespace.yaml`
  - `10-postgres.yaml`: Secret, headless Service `postgres`, StatefulSet with
    `volumeClaimTemplates` (1Gi PVC), `pg_isready` readiness/liveness
  - `20-app.yaml`: ConfigMap, Deployment (2 replicas, `wait-for-postgres`
    initContainer, readiness `/ready`, liveness `/health`, requests/limits,
    `maxUnavailable: 0` rolling update), ClusterIP Service `agent-relay` (80 → 8000)
- [x] `kind load docker-image agent-relay:local --name agent-relay`, `kubectl apply -f k8s/`
- [x] Pods ready with 0 restarts (without the initContainer the API crash-looped
      3× while PostgreSQL started)
- [x] `kubectl -n agent-relay port-forward svc/agent-relay 8080:80`; integration test
      passes, dashboard served; task row visible via `psql` in `postgres-0`
- [x] Data survives deleting `postgres-0` (PVC re-attached)
- [x] Answer: **Deployment**

## Q6. CI/CD with act

- [x] `.github/workflows/ci.yml`:
  - `test` job (in a job container, so the `postgres` service resolves by name):
    starter tests on PostgreSQL (`-m "not integration"`), then uvicorn against
    PostgreSQL and the integration test with an explicit `RELAY_BASE_URL`
  - `build-deploy` job (`needs: test`): installs kind/kubectl, reuses the local
    cluster (creates one on GitHub), builds `agent-relay:<sha7>-<utc timestamp>`
    (the sha alone repeats for uncommitted edits under act), `kind load`,
    renders the tag into `k8s/20-app.yaml` and applies it (a single rollout),
    `rollout status --timeout=180s` (undo on failure), smoke check via port-forward
- [x] act config: `.actrc` pins `catthehacker/ubuntu:act-latest`. act mounts the
      Docker socket and uses host networking, so the external kind kubeconfig
      (`127.0.0.1:<port>`) works as-is.
- [x] `act push`: both jobs green, deployed `agent-relay:5191460-…`
- [x] Heading → `Agent Relay v2`, rerun: green, cluster serves `<h1>Agent Relay v2</h1>`
      (checked through a separate port-forward, 2/2 pods on the new tag, 0 restarts)
- [x] Deliberately failing test (plus a `v3-SHOULD-NOT-DEPLOY` heading, both
      uncommitted): `test` failed, `build-deploy` never started, cluster
      still serves v2 on the same image (edits reverted)
- [x] Answer: **Keep the existing version running and stop the deployment**

## Docs & submission

- [x] README `## Deploy` section: Docker / Compose / kind / act (plus PostgreSQL and integration-test notes)
- [x] Answers summary in `docs/answers.md`
- [x] Q6 workflow also green on GitHub Actions (after starting uvicorn from `.venv`, not `uv run`)
- [ ] Submit on the course platform; optional learning-in-public post
