"""The words on a page: written by the machine, from facts the library already holds.

The analyzer's own sentences are unusable in a book. "Zwei Männer und drei Jungen sitzen im Auto
und blicken in die Kamera" is a description of a photograph; a family album says "Zusammen im
Auto" and names the people. So the facts of a page go to the machine and a page text comes back.

What keeps it honest is not the prompt alone. Every draft is measured against a table of faults -
counting people, reading out the picture, inventing a landing, quoting the field names - the
machine picks among the drafts that survive, is asked whether its own text claims anything the
facts do not carry, and, for the one fault it will not let go of, gets a last narrow repair.
Nothing here knows which machine answers: that is the Writer, and the profile behind it.
"""

import asyncio
import re
from collections.abc import Sequence
from typing import Any

from muninn.ai.base import AiError, Writer

#: Counting people, or sorting them by kind. A family book does not say "zwei Jungen".
COUNTED_PEOPLE = (
    "zwei jungen", "drei jungen", "vier jungen", "zwei männer", "drei männer", "zwei frauen",
    "zwei kinder", "drei kinder", "vier kinder", "zwei personen", "drei personen",
    "mehrere personen", "die jungen", "die männer", "die frauen", "die kinder", "die gruppe",
    "eine gruppe", "der gruppe", "die familie", "familie im", "jemand", "eine person",
    "die person", "der junge", "ein junge", "der mann", "ein mann", "die erwachsenen",
    "ein mensch", "mensch mit", "die leute", "eine frau", "die frau", "kinder", "erwachsene",
    "zwei andere",
)  # fmt: skip

#: Any number in front of a word for people. The list above cannot hold every combination, and
#: "Vier Männer und ein Hund" is exactly what a book must not say.
HOW_MANY = re.compile(
    r"\b(zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|mehrere|einige|\d+)\s+"
    r"(männer|frauen|jungen|jungs|mädchen|kinder|personen|leute|erwachsene|menschen|gäste"
    r"|andere|weitere)\b"
)

#: An opening that counts what is in the picture instead of naming the moment.
COUNTING = (
    "zwei ", "drei ", "vier ", "fünf ", "sechs ", "sieben ", "acht ", "mehrere ",
    "ein moment", "eine aufnahme", "ein bild",
)  # fmt: skip

#: Words that only describe a pose or a gaze. A line built from these reads like a caption under
#: a stock photo: it says what the camera saw, not what was going on.
POSING = (
    "blickt", "blick aus", "schaut", "guckt", "posiert", "zeigt sich", "reflexion",
    "spiegelung", "nahaufnahme", "aufnahme von", "abgebildet", "im vordergrund",
    "im hintergrund", "befindet sich",
)  # fmt: skip

#: Kitsch, and only kitsch. Warmth is wanted - that somebody is glad, that an evening is easy.
FELT = (
    "magisch", "unvergess", "abenteuer", "erinnerungen fürs", "traumhaft", "idyllisch",
    "unbeschreiblich", "für die ewigkeit", "!",
)  # fmt: skip

#: The names of the fact fields, and the travel-agency words the machine reaches for when it
#: repeats them. Nobody in a family album says "Abschnitt" or "Transfer".
JARGON = (
    "abschnitt", "station", "reisegruppe", "tageszeit", "transfer", "rücktransport",
    "etappe", "aufenthalt", "fakten", "bildzeile", "beschreibung",
)  # fmt: skip

#: Moments of a flight nobody wrote down: the library knows there was an aeroplane, not whether
#: this was shortly before landing.
UNKNOWN_MOMENTS = ("landung", "gelandet", "abgeflogen", "beim start der maschine", "im steigflug")

#: Hedging. Either a careful name or nothing; "vermutlich" belongs in a report, not in a book.
HEDGING = ("vermutlich", "wahrscheinlich", "vielleicht", "womöglich")

RULES = """Du schreibst die Seiten eines Fotobuchs für eine Familie, auf Deutsch. Du schreibst
für die Leute, die dabei waren: warm, persönlich, in ihrer Sprache. Kein Katalog, kein Protokoll.

Du bekommst die Fakten einer Seite und schlägst VIER Fassungen vor. Jede besteht aus:
- "headline": drei bis sechs Wörter. Der Moment, nicht der Bildinhalt.
- "story": ein bis zwei kurze Sätze. Was hier gerade geschieht, und was es für die Leute ist.
- "bildzeilen": zu jedem Bild aus "bilder" eine Zeile, in derselben Reihenfolge, je höchstens
  acht Wörter. Nenne die Leute beim Namen. Die "beschreibung" ist dein Material, nicht dein Text:
  aus "Ein Glas mit Eiswürfeln steht auf einem Tisch" wird "Kaltes Wasser gegen die Hitze".

So klingt es richtig:

Fakten: Flugzeug, Kopfhörer, Smartphone; personen: Matteo; abschnitt: Anreise
  headline: "Matteo und sein Handy"
  story: "Die Zeit bis zur Landung überbrücken."
  bildzeilen: ["Kopfhörer auf, die Stunden vergehen"]

Fakten: zwei Personen nebeneinander im Flugzeug, blicken in die Kamera; personen: Boris, Matteo
  headline: "Warten auf den Abflug"
  story: "Ein Blick in die Kamera, dann geht es los."
  bildzeilen: ["Angeschnallt und bereit", "Boris freut sich sichtlich"]

Fakten: Grill, Fleisch, Bierflasche; tageszeit: Abend; personen: Boris
  headline: "Der Grill ist an"
  story: "Boris wendet das Fleisch, das Bier wartet, der Abend kann kommen."
  bildzeilen: ["Rauch über der Kohle", "Boris hat alles im Blick"]

So klingt es falsch:
  "Zwei Jungen stehen vor einem Auto auf einem gepflasterten Parkplatz."
  "Drei Jungen sitzen an einem Esstisch und essen."
  "Ein Glas mit Wasser und Eiswürfeln steht auf einem Tisch mit floraler Tischdecke."
  "Junge blickt aus dem Fenster", "Bierglas im Freien", "Reflexion im Wasser"

Das sind Bildunterschriften aus einem Katalog: gezählt, vermessen, namenlos. In einem Fotobuch
steht, wer da ist und was los ist.

Was du darfst und sollst:
- Namen. Immer, wenn sie in "personen" oder in "bilder"/"personen" stehen. Namen aus "wohl" oder
  "vermutlich_dabei" in der Form "wohl Matteo" - und nie das Wort "vermutlich".
- Warm schreiben: dass jemand sich freut, dass es gemütlich wird, dass alle müde sind, wenn die
  Fakten das tragen. Ein Fotobuch darf zugewandt sein.
- Die Lage benennen, die sich aus den Fakten ergibt: warten, unterwegs sein, ankommen, die Zeit
  überbrücken, sich verabschieden. "abschnitt", "tageszeit", "davor" und "danach" sagen dir, wo
  ihr steht. "Nach dem Strand" ist besser als der Gegenstand im Bild. Aber nimm nur, was dort
  steht - erfinde kein Ziel und keine Landung dazu, und schreib die Feldnamen nicht ab.

Was du nicht darfst:
- Menschen zählen oder nach Art sortieren: kein "zwei Jungen", kein "drei Männer", keine
  "Gruppe", keine "Personen", kein "Familie im Auto". Entweder Namen oder gar keine Erwähnung.
- Orte, Namen, Uhrzeiten, Ziele oder Ereignisse erfinden, die nicht in den Fakten stehen.
- Kitsch: "magisch", "unvergesslich", "Abenteuer", "Erinnerungen fürs Leben", Ausrufezeichen.
- Die Uhrzeit wiederholen, die ohnehin auf der Seite steht, oder eine Überschrift aus
  "schon_benutzt".

Steht "hinweis" in den Fakten, dann war dein letzter Versuch nicht gut: behebe genau das.

Antworte nur mit JSON: {"fassungen": [{"headline": "...", "story": "...", "bildzeilen": ["..."]},
{...}, {...}, {...}]}"""

JUDGE = """Du wählst die Beschriftung für eine Fotobuchseite.

Du bekommst die Fakten der Seite und mehrere Fassungen. Nimm die, die den Moment nennt, statt
das Bild abzulesen: "Zum Flughafen" ist besser als "Zwei Personen am Fenster", "Nach dem Strand"
besser als "Bierglas im Freien". Eine Fassung, die einen Gegenstand aufzählt, wohin jemand
schaut oder wie jemand steht, verliert. Namen schlagen namenlose Fassungen. Eine Fassung, die
Menschen zählt ("zwei Jungen", "vier Männer", "die Gruppe"), verliert immer.

Genauigkeit geht vor Stil: eine Fassung, die etwas behauptet, was nicht in den Fakten steht -
eine Landung, ein Transfer, eine Uhrzeit, ein Ziel -, verliert gegen eine schlichtere, die
stimmt. Schiefes Deutsch verliert gegen einen einfachen Satz, der stimmt.

Antworte nur mit JSON: {"beste": <Nummer>}"""

CHECK = """Du prüfst eine Fotobuchseite gegen ihre Fakten.

Nenne jede Aussage im Text, die nicht in den Fakten steht: ein Ereignis (eine Landung, ein
Aufbruch), ein Ziel, eine Tätigkeit, eine Uhrzeit, ein Wetter, ein Name, eine Zahl. Was aus den
Fakten folgt, ist in Ordnung: wer dabei ist, wo es ist, was davor und danach war, und dass es
morgens oder abends war. Ein warmer Ton ist kein Fehler.

Antworte nur mit JSON: {"erfunden": ["...", "..."]} - leer, wenn alles gedeckt ist."""

MEND = """Du besserst eine einzige Zeile eines Fotobuchs aus, auf Deutsch.

Du bekommst die Zeile, was an ihr falsch ist, und die Namen der Leute. Schreib sie neu - so kurz
wie sie war, im selben warmen Ton, ohne den Fehler zu wiederholen. Erfinde nichts dazu. Wenn du
die Leute nicht beim Namen nennen kannst, schreib den Satz so, dass er von dem handelt, was
geschieht, und nicht von denen, die dabei sind.

Antworte nur mit JSON: {"headline": "...", "story": "..."}"""

#: How often one page may be asked again before the best of what came back is kept.
ROUNDS = 3


def faults(written: dict[str, Any], facts: dict[str, Any]) -> list[tuple[int, str]]:
    """What is wrong with a draft: how much it costs, and what to tell the machine about it.

    One table, used twice - to pick the best of the drafts that came back, and to say why the
    best of them is still not good enough. The two were drifting apart as separate functions.
    """
    headline = str(written.get("headline") or "").strip()
    story = str(written.get("story") or "").strip()
    if not headline or not story:
        return [(99, "Überschrift und Satz fehlen.")]

    lines = [str(line) for line in written.get("bildzeilen") or []]
    everything = " ".join([headline, story, *lines]).lower()
    low = headline.lower()
    sentences = " ".join([story.lower(), *[line.lower() for line in lines]])
    names = list(facts.get("personen") or [])
    known = names or [
        str(name) for shown in facts.get("bilder") or [] for name in shown.get("personen") or []
    ]
    found: list[tuple[int, str]] = []

    counted = [word for word in COUNTED_PEOPLE if word in everything]
    if match := HOW_MANY.search(everything):
        counted.insert(0, match.group(0))
    if counted:
        instead = f"({', '.join(known)})" if known else "oder lass die Leute weg"
        found.append(
            (6, f"'{counted[0]}' zählt Menschen oder sortiert sie. Schreib die Namen {instead}.")
        )
    if any(text.lower().startswith(word) for word in COUNTING for text in [headline, *lines]):
        found.append(
            (4, "Eine Zeile zählt auf, statt den Moment zu nennen. Kein 'zwei', kein 'drei'.")
        )
    if any(word in low for word in POSING):
        found.append(
            (
                4,
                "Die Überschrift beschreibt nur eine Haltung oder einen Blick. Sag stattdessen, "
                "was hier gerade läuft - notfalls nur Tageszeit und Lage, etwa 'Letzter Abend'.",
            )
        )
    if any(word in sentences for word in POSING):
        found.append((2, "Auch die Sätze sagen nur, wohin jemand schaut oder was zu sehen ist."))
    if known and not any(name.lower() in everything for name in known):
        found.append((4, f"{', '.join(known)} ist dabei und kommt nicht vor. Nenne den Namen."))
    if any(word in everything for word in FELT):
        found.append((5, "Kitsch und Ausrufezeichen gehören nicht hinein."))
    if any(word in everything for word in JARGON):
        found.append(
            (
                4,
                "Schreib wie ein Mensch, nicht wie ein Reiseplan: kein 'Abschnitt', "
                "keine 'Station', kein 'Transfer'.",
            )
        )
    if unknown := [word for word in UNKNOWN_MOMENTS if word in everything]:
        found.append(
            (
                5,
                f"'{unknown[0]}' steht nicht in den Fakten - dass ein Flugzeug dabei ist, sagt "
                "nichts über den Moment im Flug.",
            )
        )
    if any(word in everything for word in HEDGING):
        found.append(
            (6, "Schreib keine Vermutung ins Buch. Entweder 'wohl <Name>' oder gar nicht.")
        )
    if len(headline.split()) > 7:
        found.append((2, "Die Überschrift ist zu lang: drei bis sechs Wörter."))
    if low in {str(used).lower() for used in facts.get("schon_benutzt") or ()}:
        found.append((3, "Diese Überschrift steht schon auf einer anderen Seite."))
    wanted = len(facts.get("bilder") or [])
    if wanted and len(lines) != wanted:
        found.append((4, f"Es braucht genau {wanted} Bildzeilen, in der Reihenfolge der Bilder."))
    if any(len(line.split()) > 9 for line in lines):
        found.append((2, "Eine Bildzeile ist zu lang: höchstens acht Wörter."))
    return found


def scored(written: dict[str, Any], facts: dict[str, Any]) -> int:
    """How badly a draft reads - the lower the better."""
    return sum(cost for cost, _ in faults(written, facts))


def weak(written: dict[str, Any], facts: dict[str, Any]) -> str:
    """The worst thing about a draft, in a sentence the machine can act on."""
    found = sorted(faults(written, facts), reverse=True)
    return found[0][1] if found else ""


def tidy(draft: dict[str, Any]) -> dict[str, Any]:
    """One draft, with everything a page uses and nothing else."""
    return {
        "headline": str(draft.get("headline") or "").strip(),
        "story": str(draft.get("story") or "").strip(),
        "bildzeilen": [str(line).strip() for line in draft.get("bildzeilen") or []],
    }


async def ask(writer: Writer, facts: dict[str, Any]) -> dict[str, Any]:
    """Four drafts, the plainly wrong ones thrown out, and the machine's pick of the rest."""
    answered = await writer.write(facts, rules=RULES, temperature=0.8, most=700)
    drafts = [
        tidy(one) for one in (answered.get("fassungen") or [answered]) if isinstance(one, dict)
    ]
    if not drafts:
        raise AiError("Der Text kam ohne eine einzige Fassung zurück.")
    least = min(scored(one, facts) for one in drafts)
    return await choose(writer, facts, [one for one in drafts if scored(one, facts) == least])


async def choose(
    writer: Writer, facts: dict[str, Any], drafts: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Which of the drafts goes into the book. On any doubt, the first one.

    What reads like a caption and what names a moment is a question about language, and the
    machine answers it better than a word list does - it just cannot be trusted to obey it while
    it is being inventive. So it writes first and chooses afterwards.
    """
    if len(drafts) < 2:
        return dict(drafts[0])

    listed = "\n".join(
        f'{at + 1}. "{one["headline"]}" - {one["story"]} [{" | ".join(one["bildzeilen"])}]'
        for at, one in enumerate(drafts)
    )
    answered = await writer.write(
        {"fakten": facts, "fassungen": listed}, rules=JUDGE, temperature=0, most=30
    )
    picked = str(answered.get("beste") or "").strip()
    at = int(picked) - 1 if picked.isdigit() else 0
    return dict(drafts[at]) if 0 <= at < len(drafts) else dict(drafts[0])


async def checked(writer: Writer, facts: dict[str, Any], written: dict[str, Any]) -> str:
    """What the draft claims and the facts do not, as a sentence for the next attempt."""
    answered = await writer.write(
        {
            "fakten": facts,
            "text": f'"{written["headline"]}" - {written["story"]} '
            f"[{' | '.join(written['bildzeilen'])}]",
        },
        rules=CHECK,
        temperature=0,
        most=200,
    )
    made_up = [str(one).strip() for one in answered.get("erfunden") or [] if str(one).strip()][:3]
    if not made_up:
        return ""
    return (
        "Das steht nicht in den Fakten: "
        + "; ".join(made_up)
        + ". Lass es weg oder schreib nur, was gedeckt ist."
    )


async def mend(writer: Writer, facts: dict[str, Any], written: dict[str, Any]) -> dict[str, Any]:
    """One narrow repair for the fault a page will not shake off.

    Asking for four whole pages again produces the same sentence four more times; asking only for
    the one line, with only the one rule, gets it right.
    """
    complaint = weak(written, facts)
    if not complaint:
        return written
    names = facts.get("personen") or [
        name for shown in facts.get("bilder") or [] for name in shown.get("personen") or []
    ]
    answered = await writer.write(
        {
            "headline": written["headline"],
            "story": written["story"],
            "falsch": complaint,
            "namen": sorted({str(name) for name in names}),
        },
        rules=MEND,
        temperature=0.3,
        most=150,
    )
    better = {
        **written,
        **{
            field: str(answered.get(field) or "").strip() or written[field]
            for field in ("headline", "story")
        },
    }
    return better if scored(better, facts) < scored(written, facts) else written


async def write_page(writer: Writer, facts: dict[str, Any]) -> dict[str, Any]:
    """The text of one page: up to three rounds, then a repair, then the best of everything."""
    written: dict[str, Any] | None = None
    asked = dict(facts)
    for _ in range(ROUNDS):
        draft = await ask(writer, asked)
        if written is None or scored(draft, facts) <= scored(written, facts):
            written = draft
        complaint = weak(written, facts) or await checked(writer, facts, written)
        if not complaint:
            return written
        asked = {**facts, "hinweis": complaint}
    if written is None:  # pragma: no cover - ask() either answers or raises
        raise AiError("Für diese Seite kam kein Text zurück.")
    return await mend(writer, facts, written)


def put(page: dict[str, Any], written: dict[str, Any]) -> None:
    """What the machine wrote goes onto the page, and its lines under the pictures."""
    for shown, line in zip(
        page.get("_pictures") or [], written.get("bildzeilen") or [], strict=False
    ):
        if line:
            shown["caption"] = line
    if written.get("headline") and written.get("story"):
        page["headline"] = written["headline"]
        page["story"] = written["story"]


async def write_pages(writer: Writer, pages: Sequence[dict[str, Any]], *, at_once: int = 2) -> int:
    """Every page that carries facts gets its prose. Returns how many were written.

    Written in parallel, up to what the profile allows, and then once more over the headlines
    that came back twice: the book reads worse for a repeat than for a plainer line, and no page
    can see its neighbours while they are all written at once.
    """
    limit = asyncio.Semaphore(max(1, at_once))
    speaking = [page for page in pages if page.get("facts")]
    done = 0

    async def one(page: dict[str, Any]) -> None:
        nonlocal done
        async with limit:
            written = await write_page(writer, dict(page["facts"]))
        put(page, written)
        done += 1

    await asyncio.gather(*(one(page) for page in speaking))

    seen: set[str] = set()
    for page in speaking:
        headline = str(page.get("headline") or "").strip().lower()
        if not headline or headline not in seen:
            seen.add(headline)
            continue
        facts = {**page["facts"], "schon_benutzt": sorted(seen)}
        written = await write_page(writer, facts)
        put(page, written)
        seen.add(str(page.get("headline") or "").strip().lower())

    return done
