# syntax=docker/dockerfile:1

# ---- build stage: resolve the locked dependencies into /app/.venv ----
FROM python:3.11-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
# Dependencies first so code edits do not invalidate this layer.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY *.py dashboard.html ./

# ---- runtime stage: only the venv and the app, no uv, non-root ----
FROM python:3.11-slim AS runtime

RUN useradd --system --uid 10001 --home-dir /app relay
WORKDIR /app
COPY --from=build --chown=relay:relay /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    RELAY_DATABASE_URL=sqlite:////app/data/agent-relay.db
RUN mkdir -p /app/data && chown relay:relay /app/data
VOLUME ["/app/data"]

USER relay
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status != 200)"]

# --host 0.0.0.0: uvicorn defaults to 127.0.0.1, which is unreachable through -p.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
