# Muninn's server image. API, Huginn worker and scheduler share it and differ only in the command.
ARG PYTHON_VERSION=3.13
ARG UV_VERSION=0.9.13

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, so that a code change does not invalidate the dependency layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY pyproject.toml uv.lock README.md* ./
COPY muninn ./muninn

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


# The places of the world from GeoNames (CC BY 4.0), boiled down to one small file: a German
# name for every place with at least 1,000 inhabitants, its region and country, and the words
# it is searched by. Fetched here once, so where a photo was taken never has to be asked about.
FROM builder AS places

RUN set -eux; \
    mkdir /tmp/geonames; \
    cd /tmp/geonames; \
    for file in cities1000.zip alternateNamesV2.zip admin1CodesASCII.txt countryInfo.txt; do \
        python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" \
            "https://download.geonames.org/export/dump/$file" "$file"; \
    done; \
    python -m zipfile -e cities1000.zip .; \
    python -m zipfile -e alternateNamesV2.zip .; \
    /app/.venv/bin/python -m muninn.places.gazetteer /tmp/geonames /tmp/places.tsv.gz; \
    rm -rf /tmp/geonames


FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# exiftool reads the tags of 26 years of cameras, ffmpeg/ffprobe do the same for videos and
# transcode them, and libvips makes the previews. Debian's libvips brings the HEIF decoder that
# iPhone pictures need, which the bundled build of the wheel does not.
RUN set -eux; \
    apt-get update; \
    apt-get install --yes --no-install-recommends \
        libimage-exiftool-perl ffmpeg libvips42; \
    rm -rf /var/lib/apt/lists/*; \
    groupadd --gid 1000 muninn; \
    useradd --uid 1000 --gid 1000 --create-home muninn; \
    mkdir -p /library /data/derived; \
    chown -R muninn:muninn /data

WORKDIR /app

COPY --from=builder --chown=muninn:muninn /app /app
COPY --from=places /tmp/places.tsv.gz /opt/muninn/places.tsv.gz
COPY --chown=muninn:muninn alembic.ini docker-entrypoint.sh ./
COPY --chown=muninn:muninn migrations ./migrations

USER muninn

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "muninn.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
