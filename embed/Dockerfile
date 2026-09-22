# Muninn's embedding service.
#
# Two models, one address. The image carries no weights: they are fetched on first start and
# kept in a volume, so a new version of this service does not mean downloading gigabytes again.
ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.9.13

FROM python:${PYTHON_VERSION}-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    # Where the weights land. Mount a volume here.
    HF_HOME=/data/models \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, and without BuildKit cache mounts: this has to build on a NAS too,
# where Docker often comes without the buildx plugin.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY embed ./embed

RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=10s --start-period=900s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health')"

CMD ["uvicorn", "embed.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100"]
