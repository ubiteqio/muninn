# Muninn's database image: PostgreSQL with PostGIS and pgvector.
#
# The official postgis/postgis images are amd64 only, so Muninn builds on the multi-arch
# postgres image instead and adds the extensions from the PGDG repository it already carries.
# ltree, pg_trgm and citext are part of postgresql-contrib and need no extra package.
ARG POSTGRES_MAJOR=17

FROM postgres:${POSTGRES_MAJOR}-bookworm

ARG POSTGRES_MAJOR
ARG POSTGIS_MAJOR=3
# pgvector is pinned: every deployment must get the same version, and Muninn needs 0.8 or newer.
ARG PGVECTOR_VERSION=v0.8.1

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        "postgresql-${POSTGRES_MAJOR}-postgis-${POSTGIS_MAJOR}" \
        "postgresql-${POSTGRES_MAJOR}-postgis-${POSTGIS_MAJOR}-scripts"; \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        "postgresql-server-dev-${POSTGRES_MAJOR}"; \
    git clone --branch "${PGVECTOR_VERSION}" --depth 1 \
        https://github.com/pgvector/pgvector.git /tmp/pgvector; \
    make -C /tmp/pgvector OPTFLAGS=""; \
    make -C /tmp/pgvector install; \
    rm -rf /tmp/pgvector; \
    apt-get purge -y --auto-remove \
        build-essential git "postgresql-server-dev-${POSTGRES_MAJOR}"; \
    rm -rf /var/lib/apt/lists/*
