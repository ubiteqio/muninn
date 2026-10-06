# Demo library for the App Store screenshots

Screenshots in a public store listing must never show the family's own archive. They are taken
from a second, separate Muninn on the development machine that holds a small invented archive:
about 80 CC0 and public-domain photos from Wikimedia Commons in nine folders, with invented names
(Anna, Jonas, Lena, Oma Helga, Opa Klaus).

Everything it needs lives under `data/demo/`, which git ignores: the photos, the previews, the
`.env` for the demo stack and its admin password. The photos are not in the repository; the
script below fetches them again.

## Build it

```bash
# 1. The photos: downloaded once, metadata replaced by an invented date, place and camera.
#    Writes data/demo/library and data/demo/CREDITS.tsv (where each photo came from).
python3 app/store/demo/build_library.py

# 2. A second stack beside the real one: its own project name, database, ports and folders.
#    data/demo/demo.env is written by hand from deploy/.env.example with:
#      MUNINN_WEB_PORT=9190, MUNINN_API_PORT=8800,
#      MUNINN_LIBRARY_HOST_PATH=<repo>/data/demo/library,
#      MUNINN_DERIVED_HOST_PATH=<repo>/data/demo/derived,
#      TZ=Europe/Berlin and fresh secrets.
docker compose -p muninn-demo --env-file data/demo/demo.env -f deploy/docker-compose.yml up -d --build

# 3. An admin, then in the admin area at http://localhost:9190: the AI profiles (with their
#    key), the library root as published folder, and the family accounts.
docker compose -p muninn-demo --env-file data/demo/demo.env -f deploy/docker-compose.yml \
    exec api python -m muninn.cli create-admin --username anna --name Anna

# Away again, with its database:
docker compose -p muninn-demo --env-file data/demo/demo.env -f deploy/docker-compose.yml down -v
```

"Heute vor X Jahren" needs a folder whose date is today in an earlier year. The folder
`2018-10 Herbst an der Müritz` is dated 7 October; for screenshots on another day, change its
start date in `build_library.py` and build again.
