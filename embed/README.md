# Muninn: der Einbettungsdienst

Zwei Modelle hinter einer OpenAI-kompatiblen Adresse:

| Modell | Name in Muninn | Wofür |
| --- | --- | --- |
| SigLIP 2 (`google/siglip2-so400m-patch14-384`) | `siglip2` | Bilder **und** Suchsätze im selben Vektorraum, 1152 Dimensionen |
| BGE-M3 (`BAAI/bge-m3`) | `bge-m3` | Beschreibungen als Vektor der Bedeutung, 1024 Dimensionen |

Der Dienst gehört auf die Maschine mit der Grafikkarte — dieselbe, auf der das beschreibende
Modell läuft. Muninn spricht ihn übers Netz an wie jeden anderen KI-Server.

## Starten

```bash
cd embed
docker compose up -d --build
```

Beim ersten Start lädt er die Gewichte (mehrere Gigabyte) in ein Volume. Danach steht er in
Sekunden. Ohne Grafikkarte: den Block `deploy` entfernen und `EMBED_DEVICE=cpu` setzen — dann
dauert ein Bild Sekunden statt Millisekunden.

Auf der Karte hält er die Gewichte in halber Genauigkeit: zusammen rund 3 GB statt 6. Das ist
Platz, den das beschreibende Modell daneben braucht — läuft vLLM mit
`--gpu-memory-utilization 0.90`, bleibt für diesen Dienst nichts übrig. Etwa `0.80` lässt beiden
Luft.

## Warum nicht alles in vLLM?

vLLM kann **BGE-M3** durchaus selbst anbieten:

```
vllm serve BAAI/bge-m3 --runner pooling   --hf-overrides '{"architectures": ["BgeM3EmbeddingModel"]}' --pooler-config.task embed
```

**SigLIP 2 kann es nicht** — als eigenständiges Bild-Text-Modell steht es nicht auf der Liste der
Pooling-Modelle, dafür gibt es bislang nur einen Wunsch im Projekt. Dazu kommt: Ein vLLM-Prozess
bedient genau ein Modell. Drei Modelle wären drei Prozesse, jeder mit eigenem Speicheranteil auf
derselben Karte.

Deshalb dieser Dienst: zwei Modelle in einem Prozess, wenige Gigabyte, dieselbe Schnittstelle.
Wer BGE-M3 lieber aus vLLM nimmt, trägt im Profil „Textvektoren" einfach dessen Adresse ein —
Muninn fragt beide gleich.

## In Muninn eintragen

Unter **Admin → KI**, je ein Profil:

| Schnittstelle | Basis-URL | Modell |
| --- | --- | --- |
| Bildvektoren | `http://<diese Maschine>:8100/v1` | `siglip2` |
| Textvektoren | `http://<diese Maschine>:8100/v1` | `bge-m3` |

Ist `EMBED_API_KEY` gesetzt, gehört derselbe Schlüssel in beide Profile.

## Ausprobieren

```bash
curl http://localhost:8100/v1/models
curl -X POST http://localhost:8100/v1/embeddings \
  -H 'content-type: application/json' \
  -d '{"model":"bge-m3","input":["Oma am Strand"]}' | head -c 200
```

Ein Bild wird als Data-URL geschickt, genau wie es die OpenAI-API vorsieht:
`{"model":"siglip2","input":["data:image/jpeg;base64,..."]}`

## Entwicklung

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy .
uv run uvicorn embed.main:create_app --factory --reload --port 8100
```

Die Tests laden keine Gewichte: Sie setzen einen Platzhalter an die Stelle der Modelle und prüfen
das, was der Dienst selbst tut — Antwortform, Stapelgrenze, Tür, und was aus einer Data-URL wird.
