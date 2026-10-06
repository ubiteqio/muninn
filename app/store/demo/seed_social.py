"""Give the demo library a family: reactions, comments with replies, and favourites.

Run after build_library.py, once the demo server has read the library. Signs in as the admin,
gives each family account a password it keeps in data/demo/users.json, and then acts as each
of them. Running it twice adds the comments twice; start from an empty demo database instead.

    python3 app/store/demo/seed_social.py [http://localhost:8800]
"""

import json
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_library import FOLDERS, _target_name

DEMO = Path("data/demo")
FAMILY = ("jonas", "lena", "oma", "opa")


class Client:
    def __init__(self, base: str, token: str = "") -> None:
        self.base = base.rstrip("/") + "/api/v1"
        self.token = token

    def call(self, method: str, path: str, body: object = None) -> dict:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, method=method)  # noqa: S310
        request.add_header("content-type", "application/json")
        if self.token:
            request.add_header("authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                raw = response.read()
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"{method} {path}: {error.code} {error.read()[:300]!r}") from error
        return json.loads(raw) if raw else {}

    def login(self, username: str, password: str) -> "Client":
        body = {"username": username, "password": password, "client": "native"}
        token = self.call("POST", "/auth/login", body)["access_token"]
        return Client(self.base.removesuffix("/api/v1"), token)


def photo(folder: int, title: str) -> str:
    """The library path of a photo, named the way build_library.py names it."""
    entry = FOLDERS[folder]
    return f"{entry.path}/{_target_name(entry, entry.files.index(title))}"


OSTSEE, ALLGAEU, WEIHNACHTEN, GEBURTSTAG, HERBST, SCHWEDEN, KATZEN, BRUNO, MATS = range(9)

SANDBURG = photo(OSTSEE, "Children playing at the beach.JPG")
STRANDKOERBE = photo(OSTSEE, "Strandkörbe in Kühlungsborn-3-.jpg")
SCHNEEMANN = photo(WEIHNACHTEN, "Enfants faisant un bonhomme de neige.JPG")
TORTE = photo(GEBURTSTAG, "Happy Birthday! (Unsplash).jpg")
HERBSTWALD = photo(HERBST, "Off-Trail Hike (6) (37010870044).jpg")
ENTEN = photo(HERBST, "Ducklings-Verulamium-Park-lake-20050514-005.jpg")
LAGERFEUER = photo(SCHWEDEN, "Stand by the fire (Unsplash).jpg")
KATZE = photo(KATZEN, "A kitten in the hand (Flickr).jpg")
BERGE = photo(ALLGAEU, "Allgäu alps autumn 2017-10-13.jpg")
BABY = photo(MATS, "Baby wearing hat and babygrow.jpg")

REACTIONS = {
    SANDBURG: {"anna": "heart", "oma": "moved", "opa": "heart", "jonas": "joy", "lena": "heart"},
    STRANDKOERBE: {"oma": "heart", "opa": "thumbs_up"},
    SCHNEEMANN: {"lena": "joy", "jonas": "heart", "oma": "heart"},
    TORTE: {"oma": "heart", "opa": "clap", "jonas": "fire", "anna": "heart"},
    HERBSTWALD: {"opa": "wow", "anna": "heart", "oma": "heart"},
    ENTEN: {"lena": "heart", "oma": "moved"},
    LAGERFEUER: {"jonas": "fire", "lena": "hang_loose", "anna": "heart"},
    KATZE: {"lena": "heart", "jonas": "heart", "oma": "heart", "opa": "joy", "anna": "heart"},
    BERGE: {"opa": "thumbs_up", "jonas": "wow"},
    BABY: {"oma": "moved", "opa": "heart", "lena": "heart", "jonas": "heart", "anna": "heart"},
}

#: (photo, author, text, replies as (author, text))
COMMENTS = (
    (
        SANDBURG,
        "oma",
        "Die Sandburg hat den ganzen Nachmittag gehalten! Weißt du das noch, Jonas?",
        (
            ("jonas", "Bis die Flut kam 😄 Lena hat den Graben gegraben."),
            ("anna", "Und abends gab es Fischbrötchen am Hafen."),
        ),
    ),
    (
        TORTE,
        "opa",
        "Sieben Kerzen und alle auf einmal ausgepustet. Respekt, Lena!",
        (("lena", "Die Torte hatte Oma gebacken ❤️"),),
    ),
    (
        HERBSTWALD,
        "anna",
        "Heute vor acht Jahren an der Müritz. Was für ein goldener Tag.",
        (("oma", "Da müssen wir wieder hin, wenn es bunt wird."),),
    ),
    (KATZE, "lena", "So klein war Mimi mal 🥹", (("opa", "Und jetzt regiert sie das Haus."),)),
    (
        BABY,
        "oma",
        "Willkommen, kleiner Mats! Die Mütze habe ich gestrickt.",
        (("anna", "Sie passt bis heute, fast."),),
    ),
    (LAGERFEUER, "jonas", "Bestes Stockbrot meines Lebens.", ()),
    (SCHNEEMANN, "opa", "Die Möhre kam aus meinem Garten.", ()),
)

FAVOURITES = {
    "oma": (SANDBURG, BABY, TORTE),
    "opa": (BERGE, HERBSTWALD),
    "anna": (SANDBURG, HERBSTWALD, KATZE, LAGERFEUER),
}


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8800"
    admin_password = (DEMO / "admin-password").read_text().strip()
    admin = Client(base).login("anna", admin_password)

    passwords = {"anna": admin_password}
    users = {u["username"]: u for u in admin.call("GET", "/admin/users")["items"]}
    for name in FAMILY:
        starting = admin.call("POST", f"/admin/users/{users[name]['id']}/password")
        chosen = secrets.token_hex(8)
        first = Client(base).login(name, starting["starting_password"])
        first.call(
            "POST",
            "/auth/password",
            {
                "current_password": starting["starting_password"],
                "new_password": chosen,
                "client": "native",
            },
        )
        passwords[name] = chosen
    stored = DEMO / "users.json"
    stored.write_text(json.dumps(passwords, indent=1))
    stored.chmod(0o600)
    clients = {name: Client(base).login(name, pw) for name, pw in passwords.items()}

    media: dict[str, str] = {}
    cursor = ""
    while True:
        page = admin.call("GET", f"/media?limit=200{'&cursor=' + cursor if cursor else ''}")
        media |= {m["origin"]["relative_path"]: m["id"] for m in page["items"]}
        cursor = page.get("next_cursor") or ""
        if not cursor:
            break

    for path, reactions in REACTIONS.items():
        for name, reaction in reactions.items():
            clients[name].call("POST", f"/media/{media[path]}/like", {"reaction": reaction})
    for path, author, text, replies in COMMENTS:
        root = clients[author].call("POST", f"/media/{media[path]}/comments", {"body": text})
        for reply_author, reply in replies:
            clients[reply_author].call(
                "POST", f"/media/{media[path]}/comments", {"body": reply, "parent_id": root["id"]}
            )
    for name, paths in FAVOURITES.items():
        for path in paths:
            clients[name].call("POST", "/favorites", {"media_id": media[path]})
    print(f"{sum(map(len, REACTIONS.values()))} reactions, {len(COMMENTS)} comment threads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
