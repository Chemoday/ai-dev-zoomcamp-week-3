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
| `kind`    | Q5–Q6      | v0.33 installed to `~/.local/bin`; needs cgroup v2 (see blocker) |
| `kubectl` | Q5–Q6      | v1.37 installed to `~/.local/bin`  |
| `act`     | Q6         | missing → install to `~/.local/bin` |

### Blocker: kind on old WSL (cgroup v1)

`kind create cluster` failed: node PID 1 exits with *Failed to mount cgroup v1
hierarchy* (inbox WSL, kernel 5.10.16, Docker on cgroup v1). Fix chosen:
`wsl --update`, `C:\Users\Alex\.wslconfig` → `kernelCommandLine = cgroup_no_v1=all`,
`wsl --shutdown`, then `sudo service docker start` and verify
`docker info` reports cgroup v2.

### Blocker: PR creation

Fine-grained token lacks *Pull requests: write* (and *Actions: write* for Q6);
branches are pushed, PRs to be opened once the permission is added.

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

- [~] Install kind + kubectl (done); blocked on cgroup v2 for `kind create cluster --name agent-relay`
- [ ] `k8s/` manifests:
  - `namespace.yaml`
  - `postgres.yaml`: Secret, StatefulSet with `volumeClaimTemplates` (persistent
    storage), readiness `pg_isready`, headless/ClusterIP Service `postgres`
  - `app.yaml`: ConfigMap, Deployment (2 replicas, readiness `/ready`,
    liveness `/health`, resource requests), Service `agent-relay`
- [ ] `kind load docker-image agent-relay:local`, `kubectl apply -f k8s/`
- [ ] Pods ready; `kubectl port-forward svc/agent-relay 8000:80`; integration test + dashboard
- [ ] Answer: **Deployment**

## Q6. CI/CD with act

- [ ] `.github/workflows/ci.yml`:
  - `test` job: PostgreSQL service container, `uv run pytest` (starter tests on
    PostgreSQL), start API against PostgreSQL, run integration test
  - `build-deploy` job (`needs: test`): build image tagged with unique
    `${{ github.sha }}-${{ github.run_number }}`-style tag, `kind load`,
    `kubectl set image`, `kubectl rollout status` (with timeout), smoke check
- [ ] Configure act: Docker socket passthrough, kind kubeconfig reachable from
      the job container (kind network / internal kubeconfig), `.actrc`
- [ ] Run workflow with act → green, deployed
- [ ] Change dashboard heading to `Agent Relay v2`, rerun → new heading served by the cluster
- [ ] Break a test on purpose → confirm deploy job is skipped and old version keeps running
- [ ] Answer: **Keep the existing version running and stop the deployment**

## Docs & submission

- [ ] README section: run locally / Docker / Compose / kind / act
- [ ] Answers summary in `docs/answers.md`
- [ ] Submit on the course platform; optional learning-in-public post
