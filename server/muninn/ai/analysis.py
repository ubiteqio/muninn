"""What stage 5 asks the describing model, and the shape its answer must have.

The prompt and the schema belong to Muninn, not to a provider: any OpenAI-compatible model gets
the same question and has to fill in the same form.
"""

import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator

#: How much of the text in a picture is kept. A poster, a receipt or a page of a book holds far
#: more; copying all of it ran the answer past its length, the JSON stayed open, and the picture
#: was never described. Headings, names and places are what a search needs.
OCR_MAX_CHARACTERS = 800


class Analysis(BaseModel):
    """The answer about one picture, as the concept describes it. German throughout."""

    @field_validator("ocr_text", mode="before")
    @classmethod
    def _shortened(cls, value: object) -> object:
        """Too much text is cut, not refused: the rest of the answer is still good."""
        if isinstance(value, str) and len(value) > OCR_MAX_CHARACTERS:
            return value[:OCR_MAX_CHARACTERS].rstrip()
        return value

    caption: str = Field(min_length=1, max_length=600)
    tags: list[str] = Field(max_length=20)
    scene: str = Field(max_length=60)
    ocr_text: str = Field(max_length=OCR_MAX_CHARACTERS)
    people_count: int = Field(ge=0, le=500)
    time_of_day: Literal["tag", "abend", "nacht", "innen", "unbekannt"]
    is_screenshot: bool
    is_document: bool
    quality: Literal["gut", "mittel", "schlecht"]

    def cleaned(self) -> "Analysis":
        """Tags in lower case, without repeats and without blanks - the model is not always tidy."""
        seen: list[str] = []
        for tag in self.tags:
            word = tag.strip().lower()
            if word and word not in seen:
                seen.append(word)
        return self.model_copy(
            update={
                "caption": self.caption.strip(),
                "tags": seen,
                "scene": self.scene.strip().lower(),
                "ocr_text": self.ocr_text.strip(),
            }
        )


def analysis_schema() -> dict[str, object]:
    """The JSON schema the server is asked to hold the model to."""
    return Analysis.model_json_schema()


SYSTEM_PROMPT = (
    "Du beschreibst Fotos aus einem privaten Familienarchiv für eine Suchfunktion. "
    "Beschreibe nur, was im Bild wirklich zu sehen ist. Rate keine Namen, keine Orte und keine "
    "Anlässe, die man nicht sieht. Antworte ausschließlich auf Deutsch und nur mit dem "
    "verlangten JSON."
)

INSTRUCTIONS = """Fülle diese Felder aus:
- caption: ein bis zwei sachliche Sätze darüber, was zu sehen ist.
- tags: 3 bis 12 einzelne deutsche Stichwörter in Kleinschreibung (Motive, Gegenstände, Tiere, \
Umgebung, Jahreszeit), keine Sätze.
- scene: ein Wort für die Umgebung, z. B. strand, wohnzimmer, stadt, wald, straße, restaurant.
- ocr_text: gut lesbarer Text im Bild, genau so geschrieben, höchstens 500 Zeichen. Bei viel
  Text (Plakat, Beleg, Buchseite) nur das Wichtigste: Überschriften, Namen, Orte, Daten. Sonst leer.
- people_count: wie viele Menschen zu sehen sind.
- time_of_day: tag, abend, nacht, innen oder unbekannt.
- is_screenshot: true, wenn es ein Bildschirmfoto ist.
- is_document: true, wenn es vor allem ein Dokument, Beleg oder Schild abbildet.
- quality: gut, mittel oder schlecht (Unschärfe, Belichtung)."""


def user_prompt(context: str) -> str:
    """The question for one picture. The context helps, but must not be described as seen."""
    if not context:
        return INSTRUCTIONS
    return f"Bekannt, aber nicht unbedingt im Bild: {context}\n\n{INSTRUCTIONS}"


#: The summary is plain text; the photo prompt's "only JSON" would make the model wrap it.
SUMMARY_SYSTEM_PROMPT = (
    "Du fasst Videos aus einem privaten Familienarchiv für eine Suchfunktion zusammen. "
    "Du bekommst, was in jeder Sekunde des Videos zu sehen ist, und schreibst daraus eine "
    "kurze Beschreibung des ganzen Videos. Antworte ausschließlich auf Deutsch und in "
    "normalem Fließtext, ohne JSON, ohne Aufzählung und ohne Überschrift."
)

SUMMARY_PROMPT = (
    "Hier sind Beschreibungen von Standbildern aus einem Video, eine pro Sekunde, in zeitlicher "
    "Reihenfolge. Beschreibe in höchstens zwei kurzen, sachlichen Sätzen auf Deutsch, was in dem "
    "Video zu sehen ist und was darin geschieht. Sprich vom Video, nicht von Bildern, Standbildern "
    "oder Szenen, und erwähne weder Unschärfe noch Helligkeit. Erfinde nichts dazu. Antworte nur "
    "mit den Sätzen, ohne Einleitung."
)


def summary_prompt(
    moments: list[tuple[int, str]],
    context: str,
    spoken: list[tuple[float, str]] | None = None,
) -> str:
    """The frame descriptions as the model reads them, one line per second that was looked at,
    and below them what is said in the video, when anything is."""
    lines = "\n".join(f"Sekunde {second}: {caption}" for second, caption in moments)
    hint = f"Bekannt, aber nicht unbedingt im Video: {context}\n\n" if context else ""
    words = ""
    if spoken:
        said = "\n".join(f"Sekunde {round(start)}: „{text}“" for start, text in spoken)
        words = (
            "\n\nGesprochen wird im Video (automatisch mitgeschrieben, kann Fehler enthalten):\n"
            f"{said}"
        )
    return f"{hint}{SUMMARY_PROMPT}\n\n{lines}{words}"


def frame_context(context: str, second: int, duration: float | None) -> str:
    """The hint for one frame: what is known about the video, and where in it this frame is."""
    where = (
        f"Standbild aus einem Video bei Sekunde {second} von {round(duration)}"
        if duration
        else f"Standbild aus einem Video bei Sekunde {second}"
    )
    return f"{context}, {where}" if context else where


def plain_summary(answer: str) -> str:
    """The summary as sentences, even when the model wrapped them in JSON after all."""
    text = answer.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    if not text.startswith(("{", "[")):
        return text
    try:
        parsed = json.loads(text)
    except ValueError:
        return text
    return " ".join(_strings_in(parsed)).strip() or text


def _strings_in(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings_in(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings_in(item)]
    return []
