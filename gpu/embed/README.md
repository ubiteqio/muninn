# Muninn: der Einbettungsdienst

Vier Modelle hinter einer OpenAI-kompatiblen Adresse:

| Modell | Name in Muninn | Wofür |
| --- | --- | --- |
| SigLIP 2 (`google/siglip2-so400m-patch14-384`) | `siglip2` | Bilder **und** Suchsätze im selben Vektorraum, 1152 Dimensionen |
| BGE-M3 (`BAAI/bge-m3`) | `bge-m3` | Beschreibungen als Vektor der Bedeutung, 1024 Dimensionen |
| Whisper large-v3-turbo (`openai/whisper-large-v3-turbo`) | `whisper-large-v3-turbo` | Was in Videos gesagt wird |
| InsightFace `buffalo_l` | `buffalo_l` | Gesichter finden und als Vektor ablegen |

Der Dienst ist Teil von Muninns KI-Maschine: Er läuft neben dem beschreibenden Modell (vLLM) auf
dem Rechner mit der Grafikkarte. Muninn spricht ihn übers Netz an wie jeden anderen KI-Server.

## Starten

Nicht von hier aus, sondern mit dem ganzen Stapel im Ordner darüber — er baut diesen Dienst aus
dem Quelltext und startet ihn nach vLLM:

```bash
cd gpu
docker compose up -d --build
```

Einrichtung, Speicheraufteilung der Karte und die Profile in Muninn stehen in
[`gpu/README.md`](../README.md).

## Warum nicht alles in vLLM?

vLLM kann **BGE-M3** durchaus selbst anbieten:

```
vllm serve BAAI/bge-m3 --runner pooling   --hf-overrides '{"architectures": ["BgeM3EmbeddingModel"]}' --pooler-config.task embed
```

**SigLIP 2 kann es nicht** — als eigenständiges Bild-Text-Modell steht es nicht auf der Liste der
Pooling-Modelle, dafür gibt es bislang nur einen Wunsch im Projekt. Dazu kommt: Ein vLLM-Prozess
bedient genau ein Modell. Drei Modelle wären drei Prozesse, jeder mit eigenem Speicheranteil auf
derselben Karte.

Deshalb dieser Dienst: die übrigen Modelle in einem Prozess, wenige Gigabyte, dieselbe
Schnittstelle. Wer BGE-M3 lieber aus vLLM nimmt, trägt im Profil „Textvektoren" einfach dessen
Adresse ein — Muninn fragt beide gleich.

## Ausprobieren

```bash
curl -H "Authorization: Bearer $AI_API_KEY" http://localhost:8100/v1/models
curl -X POST http://localhost:8100/v1/embeddings \
  -H "Authorization: Bearer $AI_API_KEY" -H 'content-type: application/json' \
  -d '{"model":"bge-m3","input":["Oma am Strand"]}' | head -c 200
```

Ein Bild wird als Data-URL geschickt, genau wie es die OpenAI-API vorsieht:
`{"model":"siglip2","input":["data:image/jpeg;base64,..."]}`

## Entwicklung

Aus diesem Ordner (`gpu/embed`):

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy .
uv run uvicorn embed.main:create_app --factory --reload --port 8100
```

Die Tests laden keine Gewichte: Sie setzen einen Platzhalter an die Stelle der Modelle und prüfen
das, was der Dienst selbst tut — Antwortform, Stapelgrenze, Tür, und was aus einer Data-URL wird.
