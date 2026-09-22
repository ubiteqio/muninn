# Muninn

Self-hosted photo and video library for a family archive of about 26 years on a NAS. Folders
become albums, AI makes everything searchable, and signed-in family members react, comment and
get notified. What Muninn does and how it is built is described in [`README.md`](README.md).

## How to work here

- For larger tasks, present a plan first and wait for approval.
- After every finished step, tests, linters and type checks must pass: `./check.sh` covers all of
  them. Then make a small commit (Conventional Commits, in English).
- Personal, machine-specific instructions can go into `CLAUDE.local.md`, which is ignored by git.

**State:** the library, search, the app for web, iOS and Android, the social layer (reactions,
comments, notifications), the map, duplicates, memories, faces and the admin area are built.
Open are push notifications to phones, deep links and HTTPS (both need a fixed domain), and the
items under "On the roadmap" in the README.

## Repository layout

```
muninn/
├── docs/design/            # design templates per screen (reference, not code)
├── server/                 # Python backend: API, workers, scheduler (one image)
│   ├── muninn/
│   │   ├── api/            # FastAPI routers (v1/) and schemas
│   │   ├── core/           # configuration, auth, DB session, URL signing
│   │   ├── models/         # SQLAlchemy models
│   │   ├── library/        # NAS scanner, sync, safety net, published folders
│   │   ├── albums/         # album tree and album content
│   │   ├── media/          # a single medium and where it came from
│   │   ├── huginn/         # pipeline stages and Celery tasks
│   │   ├── ai/             # AI profiles and the Analyzer/Embedder/... protocols
│   │   ├── analysis/       # descriptions of pictures and video frames
│   │   ├── search/         # the search, and all vector SQL
│   │   ├── faces/          # face detection results, persons, suggestions
│   │   ├── places/         # GeoNames places, album places, the map
│   │   ├── duplicates/     # fingerprints and duplicate groups
│   │   ├── memories/       # "Heute vor X Jahren"
│   │   ├── social/         # reactions, comments, favorites
│   │   ├── notify/         # notifications, WebSocket, bundling
│   │   ├── report/         # the "Überblick" figures
│   │   ├── settings/       # settings the admin changes at runtime
│   │   └── users/          # accounts
│   ├── migrations/         # Alembic
│   └── tests/
├── embed/                  # embedding service (SigLIP 2, BGE-M3, Whisper, InsightFace)
├── gpu/                    # Docker stack for the AI machine: vLLM and embed together
├── app/                    # React + Vite + Capacitor
│   ├── src/
│   │   ├── routes/         # TanStack Router
│   │   ├── features/       # one folder per screen or domain
│   │   ├── components/     # ui/ (shadcn/ui), layout/, muninn/
│   │   ├── api/            # generated client, never edit by hand
│   │   ├── platform/       # web and native adapters: server address, tokens, splash
│   │   └── i18n/
│   ├── scripts/            # icon font subset, app icons and splash screens
│   ├── ios/
│   └── android/
└── deploy/                 # docker-compose.yml, postgres/Dockerfile, .env.example, setup.sh
```

Every domain uses the same name in three files: `api/v1/<domain>.py` handles HTTP and
permissions, `api/schemas/<domain>.py` holds the contract, and `<domain>/service.py` the logic and
the database access. Only the service talks to the database.

## Stack

- **Server:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, Celery with
  Redis, pyvips, exiftool, ffmpeg. Tools: uv, ruff, mypy (strict), pytest.
- **Database:** PostgreSQL with pgvector (0.8 or later), PostGIS, ltree and pg_trgm. It is the
  only database: no Qdrant, no second data store.
- **AI machine:** vLLM (Qwen3-VL) and the embedding service (SigLIP 2, BGE-M3, Whisper,
  InsightFace), reached over OpenAI-style HTTP.
- **App:** React with TypeScript (strict), Vite, TanStack Router, Query and Virtual, Zustand,
  Tailwind CSS with shadcn/ui, PhotoSwipe, MapLibre GL JS, i18next, Capacitor. Tools: pnpm,
  ESLint, Prettier, Vitest, Playwright.
- **Deployment:** Docker Compose with Caddy.

## Hard rules

1. Originals under `/library` are read-only. Never write, move or delete them.
2. Never bypass the scanner's safety net, and always cover it with tests: a share that is not
   mounted (device check) and a folder that cannot be listed never delete anything. Files and
   folders deleted on the NAS do disappear from the albums without confirmation; the pause before
   many deletions is a setting and off (0) by default.
3. A medium is identified by its fixed ID and BLAKE3 hash. Reactions, comments and faces hang on
   the ID, never on the path.
4. AI is reached only through the protocols in `server/muninn/ai` (`Analyzer`, `Embedder`,
   `Transcriber`, `FaceDetector`; OpenAI-compatible). No model names or URLs in code: everything
   comes from configuration.
5. Vector search only in `server/muninn/search`. No vector SQL anywhere else.
6. Every pipeline stage is idempotent and stores its version.
7. Schema changes only through Alembic migrations.
8. API under `/api/v1`, errors as Problem Details (RFC 9457), lists with cursor pagination. After
   API changes, regenerate the TypeScript client.
9. Media URLs are signed. The native app uses no cookies, only tokens in the header.
10. Code, identifiers, comments and commits in English. UI texts only through i18next, German
    first.
11. No secrets in the repository. Configuration through `.env` files; the templates are
    `deploy/.env.example` and `gpu/.env.example`.

## Commands

```bash
# Tests, linters and type checks for server, app and embedding service, in parallel.
# This is the gate before every commit.
./check.sh
./check.sh fast     # without the tests that need the PostgreSQL container
./check.sh server   # one part only
./check.sh app
./check.sh embed

# First installation: configuration, secrets, start, first admin
./deploy/setup.sh

# The whole stack (reads deploy/.env)
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f api
docker compose -f deploy/docker-compose.yml down

# Create an admin (asks for the password)
docker compose -f deploy/docker-compose.yml exec api python -m muninn.cli create-admin \
    --username admin --name Admin

# Development: databases reachable locally, and the web container serves the source with hot
# reload instead of a built bundle. Without this overlay, :9090 shows the last image build.
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml up -d

# Back to the built bundle (and rebuild after app changes):
docker compose -f deploy/docker-compose.yml up -d --build web

# Server (from server/)
cd server && uv sync
cd server && uv run pytest
# The migration tests need the local database image:
docker compose -f deploy/docker-compose.yml build postgres
cd server && uv run ruff check . && uv run ruff format --check . && uv run mypy .
cd server && uv run uvicorn muninn.main:create_app --factory --reload
cd server && uv run alembic upgrade head

# Embedding service (from embed/), belongs on the machine with the graphics card
cd embed && uv sync && uv run pytest
cd embed && uv run uvicorn embed.main:create_app --factory --reload --port 8100
cd gpu && docker compose up -d        # vLLM and the embedding service together

# App (from app/)
cd app && pnpm install
cd app && pnpm dev
cd app && pnpm test
cd app && pnpm lint && pnpm typecheck
cd app && pnpm build
cd app && pnpm gen:api     # regenerate the API client from a running server
cd app && pnpm cap:sync    # copy the web build into iOS and Android
cd app && pnpm exec cap open ios      # Xcode
cd app && pnpm exec cap open android  # Android Studio
# Build without the IDEs. Gradle needs Android Studio's JDK; the system Java is too old:
cd app/ios/App && xcodebuild -project App.xcodeproj -scheme App -sdk iphonesimulator build
cd app/android && JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" ./gradlew assembleDebug
# Cut the icon font down to the icons in use (after adding an icon):
cd app && uv run --with "fonttools[woff]" scripts/subset-icons.py
# App icons and splash screens for iOS, Android and the web, from public/muninn-mark.png:
cd app && uv run --with pillow scripts/make-icons.py
```

The OpenAPI description is at `/api/v1/openapi.json`, its UI at `/api/v1/docs`. For Docker there
are `/health` and `/ready` outside `/api/v1`.

## Names

Huginn is the indexing worker, Mímir the search, Yggdrasil the album tree, Midgard the map, Walhall
the favorites and Hliðskjálf the admin area. In code only the worker is called `huginn`; every
other module has a plain name. The names are for code and documentation only: the interface shows
no mythological name, not even as a title. The one exception is the product name Muninn. Titles
and controls are plain German.
