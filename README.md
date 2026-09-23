# Agent Relay

Agent Relay is a small FastAPI service for registering agents, delivering one
task at a time, and recording results. The local starter is self-contained:
SQLite persists the queue and attempts, while workers execute tasks on their own
machines. The included worker deterministically returns `input.upper()`.

## Run it

```bash
uv sync
uv run uvicorn main:app --reload
```

Open <http://127.0.0.1:8000/> for the token-based local dashboard. The default
database is `./agent-relay.db`; set `RELAY_DATABASE_URL` to use another SQLite
file. `GET /health` is a liveness check and `GET /ready` verifies database
connectivity and schema (it queries the real tables, so a wiped volume
reports not-ready instead of passing with zero tables).

Register two identities and send a task:

```bash
alice=$(curl -sS -X POST http://127.0.0.1:8000/api/v1/agents \
  -H 'content-type: application/json' -d '{"name":"alice"}')
bob=$(curl -sS -X POST http://127.0.0.1:8000/api/v1/agents \
  -H 'content-type: application/json' -d '{"name":"uppercase"}')
```

The response contains each agent's secret `token` once. Keep it outside source
control. Use `Authorization: Bearer <token>` for all subsequent API calls;
registration is the only unauthenticated endpoint. For a shared installation,
set `RELAY_ENROLLMENT_SECRET` and send it as `X-Enrollment-Secret` when
registering.

## Run the deterministic worker

The worker can register itself and save credentials in a mode-0600 JSON file:

```bash
uv run python main.py worker \
  --base-url http://127.0.0.1:8000 \
  --name uppercase \
  --credentials ./uppercase-credentials.json \
  --worker-id laptop-1
```

For failure/redelivery demonstrations, make local execution intentionally slow
and stop the process after one completion:

```bash
uv run python main.py worker --credentials ./uppercase-credentials.json \
  --slow-seconds 75 --worker-id slow-laptop
```

The worker heartbeats during long work. Killing it leaves the claim leased;
after the 60-second lease expires, another worker can claim the task with a new
token and incremented attempt number. `RELAY_LEASE_SECONDS` and
`RELAY_MAX_ATTEMPTS` are configurable server settings.

An existing credential can also be supplied explicitly (the token is not
written to disk):

```bash
uv run python main.py worker --agent-id agent_123 --token agt_… --worker-id laptop-2
```

## Storage and delivery behavior

`database.py` contains SQLAlchemy models, SQLite WAL setup, and the isolated
`BEGIN IMMEDIATE` transaction helper. `storage.py` contains task/claim/recovery
operations; routes and request models are kept in `main.py` and `schemas.py`.
On SQLite, writer transactions are serialized to make concurrent claims safe
across processes. On PostgreSQL (any `postgresql+psycopg://` URL) claims use
`SELECT ... FOR UPDATE SKIP LOCKED`, and the other lifecycle writes lock their rows
with `FOR UPDATE`. The HTTP protocol and lifecycle in `SPEC.md` are the same
for both.

Claims are at-least-once and leased for 60 seconds by default. Heartbeats extend
an active lease. A completion or failure must include the recipient's bearer
token and claim token. Repeating the exact terminal request with that claim
token is idempotent; a stale token or different result receives `409`.

## Verify

The test suite covers the main protocol, sender/recipient access boundaries,
hashed claim-token behavior, idempotent terminal retries, concurrent claims,
lease expiry before and after recovery, pagination/error shape, and dashboard
asset serving:

```bash
uv run pytest -q
```

Tests default to a scratch database at `/tmp/agent-relay-test.db` so they
don't reset your dev server's `./agent-relay.db`. The fixture drops and
recreates all tables on whatever `RELAY_DATABASE_URL` points at, so stop
the dev server first or set `RELAY_DATABASE_URL` to a scratch file before
running tests against another database.

Set `RELAY_DATABASE_URL` to a PostgreSQL URL to run the same suite against
PostgreSQL. The HTTP integration test in `tests/integration/` talks to a running
API at `RELAY_BASE_URL` (default `http://127.0.0.1:8000`). It is skipped
when nothing is listening there, and it fails if `RELAY_BASE_URL` is set but
unreachable:

```bash
RELAY_BASE_URL=http://127.0.0.1:8000 uv run pytest -q -m integration
```

## Deploy

Each option below ends with the integration test passing against the deployed API.

### Docker

```bash
docker build -t agent-relay:local .
docker run -p 8000:8000 -v agent-relay-data:/app/data agent-relay:local
```

The image runs as a non-root user with SQLite in the `/app/data` volume. `-p`
publishes the port; `EXPOSE` alone does not.

### Docker Compose (API + PostgreSQL)

```bash
docker compose up --build
docker compose exec postgres psql -U relay -d relay -c 'select status, count(*) from tasks group by status'
```

The API reaches the database at `postgres:5432`: a compose service name is its
hostname on the compose network. Data lives in the `postgres-data` volume and
survives `docker compose down` (not `down -v`).

### Kubernetes (kind)

```bash
kind create cluster --name agent-relay
kind load docker-image agent-relay:local --name agent-relay
kubectl apply -f k8s/
kubectl -n agent-relay rollout status deployment/agent-relay
kubectl -n agent-relay port-forward svc/agent-relay 8080:80
```

`k8s/` contains a namespace, PostgreSQL as a StatefulSet with a persistent
volume claim, and the API as a two-replica Deployment. The Deployment has
`/ready` and `/health` probes and an init container that waits for PostgreSQL.
kind needs cgroup v2; on WSL, update WSL first if `docker info` reports cgroup v1.

### CI/CD (GitHub Actions, locally with act)

```bash
act push
```

`.github/workflows/ci.yml` runs the starter tests and the integration test
against a PostgreSQL service container. Only if they pass, it builds
`agent-relay:<sha7>-<timestamp>`, loads it into the `agent-relay` kind cluster,
deploys it, and waits for the rollout. A failing test skips the deploy job, and
the cluster keeps running the previous version. `.actrc` pins the runner image;
act passes the Docker socket through and uses the host network, so the job reaches
the local kind cluster. On GitHub, the deploy job creates a temporary kind
cluster instead.
