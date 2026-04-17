FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY main.py swagger-latest.yaml ./

FROM python:3.14-slim-bookworm

WORKDIR /app

RUN addgroup --gid 1000 appgroup && \
    adduser --uid 1000 --gid 1000 --disabled-password appuser

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/main.py /app/main.py
COPY --from=builder /app/swagger-latest.yaml /app/swagger-latest.yaml

USER appuser
RUN mkdir -p /home/appuser/.cache && chmod 755 /home/appuser/.cache

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV MCP_TRANSPORT=sse
ENV UV_CACHE_DIR=/home/appuser/.cache

EXPOSE 8000

ENTRYPOINT ["python", "main.py"]
