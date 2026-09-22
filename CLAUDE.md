# Muninn

Selbst gehostete Foto- und Videoverwaltung für rund 26 Jahre Medien auf einem NAS. Ordner werden Alben, KI macht alles durchsuchbar, angemeldete User liken, kommentieren und bekommen Push-Nachrichten.

Das verbindliche Konzept steht in `docs/konzept.md`. Lies vor jeder Aufgabe den passenden Abschnitt dort.

## Arbeitsweise

- Arbeite meilensteinweise nach „Umsetzungsreihenfolge“ in `docs/konzept.md`. Abgeschlossen sind
  1 (Fundament), 2 (Bibliothek) und 3 (App-Grundgerüst); aus Meilenstein 7 ist der Admin-Bereich mit
  Einstellungen und Benutzerverwaltung vorgezogen. Offen: **4 (KI und Suche)**. Aus 3 fehlen noch
  Deep Links — sie brauchen eine feste Domain, und die ist ein offener Punkt im Konzept.
- Lege bei größeren Aufgaben zuerst einen Plan vor und warte auf Freigabe.
- Weicht eine Lösung vom Konzept ab oder betrifft sie einen offenen Punkt: nachfragen statt raten.
- Nach jedem abgeschlossenen Schritt müssen Tests, Linter und Typprüfung grün sein: ein `./check.sh`
  deckt alles ab. Danach ein kleiner Commit (Conventional Commits, Englisch).
- Der Wissensgraph unter `graphify-out/` beantwortet Fragen zum Code schneller als Suchen im Quelltext.
  Nach Codeänderungen `graphify update .` (nur AST, keine API-Kosten); der Ordner gehört nicht ins Repository.

## Repository-Struktur

```
muninn/
├── CLAUDE.md
├── docs/
│   ├── konzept.md
│   └── design/            # Design-Vorlagen je Bildschirm (Referenz, kein Code)
├── server/                 # Python-Backend: API, Worker, Scheduler (ein Image)
│   ├── muninn/
│   │   ├── api/            # FastAPI-Router und Schemas
│   │   ├── core/           # Konfiguration, Auth, DB-Session, URL-Signierung
│   │   ├── models/         # SQLAlchemy-Modelle
│   │   ├── library/        # NAS-Scanner, Abgleich, Sicherheitsnetz, Wurzelordner
│   │   ├── albums/         # Albenbaum und Albeninhalt
│   │   ├── media/          # einzelnes Medium und seine Herkunft
│   │   ├── huginn/         # Pipeline-Stufen und Celery-Tasks
│   │   ├── ai/             # Analyzer- und Embedder-Provider
│   │   ├── search/         # Mímir: gekapselte Suche
│   │   ├── social/         # Likes, Kommentare, Favoriten
│   │   └── notify/         # Push, WebSocket, Bündelung
│   ├── migrations/         # Alembic
│   └── tests/
├── embed/                  # Embedding-Dienst (SigLIP 2, BGE-M3), eigener Stapel für den GPU-Rechner
├── gpu/                    # Docker-Stapel für die KI-Maschine: vLLM und embed zusammen
├── app/                    # React + Vite + Capacitor
│   ├── src/
│   │   ├── routes/         # TanStack Router
│   │   ├── features/       # albums, media, search, map, people, social, admin
│   │   ├── components/ui/  # shadcn/ui
│   │   ├── api/            # generierter Client, nicht von Hand ändern
│   │   ├── platform/       # Web- und Native-Adapter: push, token, share
│   │   └── i18n/
│   ├── ios/
│   └── android/
└── deploy/                 # docker-compose.yml, Caddyfile, postgres/Dockerfile, .env.example, setup.sh
```

Jede Domäne liegt unter demselben Namen in drei Dateien: `api/v1/<domain>.py` macht HTTP und
Berechtigungen, `api/schemas/<domain>.py` hält den Contract, `<domain>/service.py` die Logik und
den Datenbankzugriff. Nur der Service spricht mit der Datenbank.

## Stack

- **Server:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, Celery mit Redis, pyvips, exiftool, ffmpeg, InsightFace. Werkzeuge: uv, ruff, mypy (strict), pytest.
- **Datenbank:** PostgreSQL mit pgvector (ab 0.8), PostGIS, ltree und pg_trgm. Das ist die einzige Datenbank, es gibt kein Qdrant und keine zweite Datenhaltung.
- **App:** React mit TypeScript (strict), Vite, TanStack Router, Query und Virtual, Zustand, Tailwind CSS mit shadcn/ui, PhotoSwipe, MapLibre GL JS, i18next, Capacitor. Werkzeuge: pnpm, ESLint, Prettier, Vitest, Playwright.
- **Deployment:** Docker Compose mit Caddy.

## Harte Regeln

1. Originale unter `/library` sind read-only. Niemals schreiben, verschieben oder löschen.
2. Das Scanner-Sicherheitsnetz nie umgehen und immer mit Tests absichern: eine nicht eingehängte Freigabe (Geräteprüfung) und ein Ordner, der sich nicht auflisten lässt, löschen nie etwas. Auf dem NAS gelöschte Dateien und Ordner verschwinden dagegen ohne Bestätigung aus den Alben; die Pause vor vielen Löschungen ist eine Einstellung und steht standardmäßig auf aus (0).
3. Ein Medium wird über feste ID und BLAKE3-Hash identifiziert. Likes, Kommentare und Gesichter hängen an der ID, nie am Pfad.
4. KI nur über die Schnittstellen `Analyzer` und `Embedder` (OpenAI-kompatibel) ansprechen. Keine Modellnamen oder URLs im Code, alles kommt aus der Konfiguration.
5. Vektorsuche nur im Modul `server/muninn/search`. Kein Vektor-SQL außerhalb davon.
6. Jede Pipeline-Stufe ist idempotent und speichert ihre Version.
7. Schemaänderungen nur per Alembic-Migration.
8. API unter `/api/v1`, Fehler als Problem Details (RFC 9457), Listen mit Cursor-Paginierung. Nach API-Änderungen den TypeScript-Client neu generieren.
9. Medien-URLs sind signiert. Die native App nutzt keine Cookies, nur Tokens im Header.
10. Code, Bezeichner, Kommentare und Commits auf Englisch. UI-Texte nur über i18next, Deutsch zuerst.
11. Keine Secrets im Repository. Konfiguration über `.env`, Vorlage in `deploy/.env.example`.

## Befehle

```bash
# Tests, Linter und Typprüfung für Server, App und Einbettungsdienst, parallel.
# Das ist das Tor vor jedem Commit.
./check.sh
./check.sh fast     # ohne die Tests, die den PostgreSQL-Container brauchen
./check.sh server   # nur eine Seite
./check.sh app
./check.sh embed

# Erstinstallation: Konfiguration, Schlüssel, Start, erster Admin
./deploy/setup.sh

# macOS: die NAS-Freigabe dauerhaft einhängen. Ohne sie starten api, worker und scheduler nicht,
# weil Docker eine verschwundene Bind-Einhängung nicht anlegen darf. Das Skript ist allgemein
# gehalten und kennt Muninn nicht; es hängt Freigaben ein, mehr nicht.
cp deploy/macos/tnas-mount.sh ~/bin/ && cp deploy/macos/local.tnas.mount.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/local.tnas.mount.plist   # Werte in der plist anpassen

# Gesamtsystem (aus deploy/, liest deploy/.env)
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f api
docker compose -f deploy/docker-compose.yml down

# Admin anlegen (fragt das Passwort ab)
docker compose -f deploy/docker-compose.yml exec api python -m muninn.cli create-admin \
    --username admin --name Admin

# Entwicklung: Datenbanken lokal erreichbar, und der Web-Container liefert die Quelle mit
# Hot Reload statt eines gebauten Bündels. Ohne diesen Aufsatz zeigt :9090 den Stand des
# letzten Image-Baus.
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml up -d

# Zurück auf das gebaute Bündel (und nach App-Änderungen neu bauen):
docker compose -f deploy/docker-compose.yml up -d --build web

# Server (aus server/)
cd server && uv sync
cd server && uv run pytest
# Die Migrationstests brauchen das lokale Datenbank-Image:
docker compose -f deploy/docker-compose.yml build postgres
cd server && uv run ruff check . && uv run ruff format --check . && uv run mypy .
cd server && uv run uvicorn muninn.main:create_app --factory --reload
cd server && uv run alembic upgrade head

# Einbettungsdienst (aus embed/) — gehört auf die Maschine mit der Grafikkarte
cd embed && uv sync && uv run pytest
cd embed && uv run uvicorn embed.main:create_app --factory --reload --port 8100
cd embed && docker compose up -d --build     # eigener Stapel, nicht Teil von deploy/

# App (aus app/)
cd app && pnpm install
cd app && pnpm dev
cd app && pnpm test
cd app && pnpm lint && pnpm typecheck
cd app && pnpm build
cd app && pnpm cap:sync    # Web-Build in iOS und Android übernehmen
cd app && pnpm exec cap open ios      # Xcode
cd app && pnpm exec cap open android  # Android Studio
# Ohne Oberfläche bauen. Gradle braucht das JDK von Android Studio; das System-Java ist zu alt:
cd app/ios/App && xcodebuild -project App.xcodeproj -scheme App -sdk iphonesimulator build
cd app/android && JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" ./gradlew assembleDebug
# Icon-Schrift auf die benutzten Icons kürzen (nach neuen Icons ausführen):
cd app && uv run --with "fonttools[woff]" scripts/subset-icons.py
```

Die OpenAPI-Beschreibung liegt unter `/api/v1/openapi.json`, die Oberfläche dazu unter `/api/v1/docs`.
Für Docker gibt es `/health` und `/ready` außerhalb von `/api/v1`.

## Namen

Huginn ist der Indexierungs-Worker, Mímir die Suche, Yggdrasil der Albenbaum, Midgard die Karte, Walhall die Favoriten und Hliðskjálf der Admin-Bereich. Im Code heißt nur der Worker `huginn`; alle anderen Module tragen sachliche Namen. Die Namen gelten nur in Code und Dokumentation: In der Oberfläche steht kein mythologischer Name, auch nicht
als Titel. Einzige Ausnahme ist der Produktname Muninn. Titel und Bedienelemente sind klares Deutsch.
