# Third-party notices

Muninn's own code is licensed under the MIT License, see [`LICENSE`](LICENSE). The parts below are
not Muninn's own work and keep their own licenses. Whoever passes Muninn on passes these notices
on with it.

## Included in this repository

| File | What | License |
| --- | --- | --- |
| `app/src/assets/fonts/material-symbols-rounded-subset.woff2` | A subset of [Material Symbols Rounded](https://github.com/google/material-design-icons) by Google, cut down by `app/scripts/subset-icons.py` | Apache License 2.0, full text in [`app/src/assets/fonts/LICENSE-material-symbols.txt`](app/src/assets/fonts/LICENSE-material-symbols.txt) |

## Downloaded when Muninn is built or run

These are not part of the repository. The build, the package managers or the running services
fetch them, and their terms apply to whoever runs Muninn.

| What | Where it is used | License or terms |
| --- | --- | --- |
| Libraries installed by `uv` and `pnpm` | Server, embedding service and app | Each under its own license, see the lock files `server/uv.lock`, `embed/uv.lock` and `app/pnpm-lock.yaml` |
| [Inter](https://rsms.me/inter/) typeface, via `@fontsource-variable/inter` | Bundled into the built app | SIL Open Font License 1.1 |
| [GeoNames](https://www.geonames.org/) place data | Built into the server image (`server/Dockerfile`) | Creative Commons Attribution 4.0; the app credits GeoNames where it shows places |
| Map tiles from [OpenFreeMap](https://openfreemap.org/), with map data from [OpenStreetMap](https://www.openstreetmap.org/copyright) | The map, loaded by the browser or phone | OpenStreetMap data under the Open Database License; the map shows the attribution |
| Qwen3-VL-8B-Instruct | Describes pictures, on the GPU machine (`gpu/`) | Apache License 2.0 |
| SigLIP 2 (`google/siglip2-so400m-patch14-384`) | Picture vectors, embedding service | Apache License 2.0 |
| BGE-M3 (`BAAI/bge-m3`) | Text vectors, embedding service | MIT License |
| Whisper large-v3-turbo (`openai/whisper-large-v3-turbo`) | Speech in videos, embedding service | MIT License |
| InsightFace `buffalo_l` | Face recognition, embedding service | **Non-commercial research use only.** Fine for a family's own photos; commercial use needs a license from InsightFace, or face recognition switched off (`EMBED_FACE_MODEL_NAME=`) |

The model licenses above are as published by their authors at the time of writing; check the
model's page before relying on them. Any model can be swapped in the admin area and in
`gpu/.env`.
