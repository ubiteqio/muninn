# Muninn's web app: built once, then served as plain files.
#
# The same container is also the one address the family uses. It serves the app and passes
# everything under /api on to the server, so the browser talks to one origin - which is what
# makes the session cookie work and lets the app ask for /api/v1/... without being told where
# the server is.
ARG NODE_VERSION=22
ARG CADDY_VERSION=2

FROM node:${NODE_VERSION}-bookworm-slim AS build

WORKDIR /app

RUN corepack enable

# Dependencies first, so that a change to the source does not invalidate the dependency layer.
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

COPY . .
RUN pnpm build


FROM caddy:${CADDY_VERSION}-alpine

COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 9090

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget --quiet --spider http://127.0.0.1:9090/ || exit 1
