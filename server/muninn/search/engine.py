"""Mímir's search: four lists of candidates, one ranking.

A search asks four questions at once - which pictures look like the words (the picture model),
which descriptions mean the same (the word model), where the words themselves turn up (German
full text over captions, tags, text in pictures, the seconds of videos and what is said in them),
and which album or file is called something like it (trigrams, so typing errors still find).
Each question gives a ranked list; Reciprocal Rank Fusion turns the four into one: a medium near
the top of several lists beats one at the top of a single list. The filters sit inside every
question, so a narrow filter still gets enough candidates.

Only this module writes vector SQL. The table names come from VectorKind, the model names and
lengths are written in as literals because that is what lets PostgreSQL use the partial index
of that model; everything else is bound.
"""

import asyncio
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from muninn.ai import service as ai_service
from muninn.ai.base import AiError
from muninn.ai.health import STAGE_OF
from muninn.faces import people
from muninn.huginn import jobs
from muninn.models.ai import AiKind, AiProfile
from muninn.models.media import Media, MediaKind, MediaStatus
from muninn.places import service as places_service
from muninn.search.query import ParsedQuery, parse
from muninn.search.service import VectorKind, _literal, _sql

logger = logging.getLogger(__name__)

#: How many candidates each list contributes. RRF only needs the head of every list.
CANDIDATES = 200

#: The constant of Reciprocal Rank Fusion: 60 is what the paper found and everybody uses.
RRF_K = 60

#: How close a vector has to be to count at all, as cosine distance (0 is the same, 2 opposite).
#: Measured on 702 media of the library: BGE-M3 put every description that fitted a query at
#: 0.27 to 0.45 and the best of the unfitting ones at 0.53 and beyond ("Hund" in a library
#: without dogs). SigLIP orders pictures well but cannot say that none fits: two seahorses lay
#: at 0.907 for "Seepferdchen", and the best picture for "Hund" at 0.901. Its bound only keeps
#: the plainly unrelated out.
IMAGE_MAX_DISTANCE = 0.92
CAPTION_MAX_DISTANCE = 0.50

#: So the picture model does not decide alone for a medium that has a description: it moves up
#: what the description found too. Only a medium without a description yet can be found by its
#: picture alone - and only among this many of the nearest.
IMAGE_ALONE = 20

#: How long a search waits for the AI server to turn its words into vectors. The pipeline may
#: keep the card busy for minutes; somebody in front of a search field does not wait that long,
#: and gets what words and names find instead.
PROBE_TIMEOUT_SECONDS = 5

#: How alike a name has to be to count, as pg_trgm word similarity (0 to 1).
NAME_MIN_SIMILARITY = 0.5


@dataclass(frozen=True, slots=True)
class Filters:
    date_from: date | None = None
    date_until: date | None = None
    kind: MediaKind | None = None
    #: An album and everything below it, by its path.
    album_path: str | None = None
    camera: str | None = None
    #: Place names in lower case; a medium counts when its place carries one of them.
    place_keys: tuple[str, ...] = ()
    #: Persons who all have to be in the medium.
    person_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class Probe:
    """A vector to search with, and the model whose vectors it is compared to."""

    vector: list[float]
    model: str


@dataclass(frozen=True, slots=True)
class Hit:
    media_id: uuid.UUID
    score: float
    #: For a video, the second in which it matched - a frame or something said - when it did.
    moment: float | None = None


def _filter_sql(filters: Filters) -> tuple[str, dict[str, Any]]:
    """The conditions on "m" (media) and "a" (albums) every list shares."""
    conditions = ["m.status = :active", "m.duplicate_of IS NULL"]
    params: dict[str, Any] = {"active": MediaStatus.ACTIVE.value}
    if filters.date_from is not None:
        conditions.append("m.taken_at >= :date_from")
        params["date_from"] = filters.date_from
    if filters.date_until is not None:
        conditions.append("m.taken_at < :date_until")
        params["date_until"] = filters.date_until
    if filters.kind is not None:
        conditions.append("m.kind = :kind")
        params["kind"] = filters.kind.value
    if filters.album_path is not None:
        conditions.append(
            "(a.relative_path = :album OR starts_with(a.relative_path, :album_below))"
        )
        params["album"] = filters.album_path
        params["album_below"] = f"{filters.album_path}/"
    if filters.camera is not None:
        conditions.append("m.camera_model = :camera")
        params["camera"] = filters.camera
    if filters.place_keys:
        conditions.append(
            "m.place_id IN (SELECT id FROM places WHERE keys && CAST(:place_keys AS text[]))"
        )
        params["place_keys"] = list(filters.place_keys)
    if filters.person_ids:
        # Everybody named has to be in it: "Oma Lena" are the photos of both.
        conditions.append(
            "(SELECT count(DISTINCT pf.person_id) FROM faces pf WHERE pf.media_id = m.id"
            " AND pf.person_id = ANY(CAST(:persons AS uuid[]))) = :person_count"
        )
        params["persons"] = list(filters.person_ids)
        params["person_count"] = len(filters.person_ids)
    return " AND ".join(conditions), params


def _quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _vector_list(kind: VectorKind, probe: Probe, name: str, max_distance: float, where: str) -> str:
    """The nearest vectors of one model, as ranks. Model and length as literals: see above."""
    dimensions = len(probe.vector)
    cast = f"e.embedding::halfvec({dimensions})"
    return _sql(
        f"""
        {name} AS (
            SELECT media_id, row_number() OVER (ORDER BY distance) AS rank, NULL::float AS moment,
                   '{name}' AS source
              FROM (
                SELECT e.media_id, {cast} <=> CAST(:{name}_vector AS halfvec({dimensions}))
                           AS distance
                  FROM {{table}} e
                  JOIN media m ON m.id = e.media_id
                  JOIN albums a ON a.id = m.album_id
                 WHERE e.model = {_quoted(probe.model)} AND e.dimensions = {dimensions}
                   AND {where}
                 ORDER BY {cast} <=> CAST(:{name}_vector AS halfvec({dimensions}))
                 LIMIT {CANDIDATES}
              ) nearest
             WHERE distance <= {float(max_distance)}
        )""",  # noqa: S608 - name, cast and model are ours; the filter is fixed pieces
        kind,
    )


_WORDS = """
    words AS (
        SELECT media_id, row_number() OVER (ORDER BY weight DESC) AS rank, moment,
               'words' AS source
          FROM (
            SELECT DISTINCT ON (media_id) media_id, weight, moment
              FROM (
                SELECT x.media_id, ts_rank(x.search_tsv, q.query) AS weight, NULL::float AS moment
                  FROM media_analyses x, q
                 WHERE x.search_tsv @@ q.query
                UNION ALL
                SELECT x.media_id, ts_rank(x.search_tsv, q.query) * 0.9, x.second::float
                  FROM video_frames x, q
                 WHERE x.search_tsv @@ q.query
                UNION ALL
                -- What the file says about itself: camera, model, lens. Word for word.
                SELECT x.id, ts_rank(x.metadata_tsv, q.plain) * 0.5, NULL::float
                  FROM media x, q
                 WHERE x.metadata_tsv @@ q.plain
                UNION ALL
                SELECT x.media_id, ts_rank(x.search_tsv, q.query) * 0.9,
                       (SELECT (part ->> 'start')::float
                          FROM jsonb_array_elements(x.segments) AS part
                         WHERE to_tsvector('german', part ->> 'text') @@ q.query
                         LIMIT 1)
                  FROM media_transcripts x, q
                 WHERE x.search_tsv @@ q.query
              ) found
              JOIN media m ON m.id = found.media_id
              JOIN albums a ON a.id = m.album_id
             WHERE {where}
             ORDER BY media_id, weight DESC, moment NULLS LAST
          ) best
         ORDER BY weight DESC
         LIMIT {candidates}
    )"""

_NAMES = """
    names AS (
        SELECT media_id, row_number() OVER (ORDER BY likeness DESC) AS rank, NULL::float AS moment,
               'names' AS source
          FROM (
            SELECT m.id AS media_id,
                   greatest(word_similarity(:text, a.relative_path),
                            max(word_similarity(:text, f.filename))) AS likeness
              FROM media m
              JOIN albums a ON a.id = m.album_id
              JOIN media_files f ON f.media_id = m.id
             WHERE {where}
               AND (:text <% a.relative_path OR :text <% f.filename)
             GROUP BY m.id, a.relative_path
          ) alike
         WHERE likeness >= {min_similarity}
         ORDER BY likeness DESC
         LIMIT {candidates}
    )"""


async def search(
    session: AsyncSession,
    *,
    words: str,
    filters: Filters,
    image: Probe | None = None,
    caption: Probe | None = None,
) -> list[Hit]:
    """Every medium that answers the search, best first. Empty words: everything in the filters,
    newest first - a search for "2012" is a walk through that year."""
    where, params = _filter_sql(filters)

    if not words:
        rows = await session.execute(
            text(
                f"""
                SELECT m.id FROM media m JOIN albums a ON a.id = m.album_id
                 WHERE {where}
                 ORDER BY coalesce(m.taken_at, m.created_at) DESC, m.id
                 LIMIT {CANDIDATES * 4}
                """  # noqa: S608 - the filter is built from fixed pieces, values are bound
            ),
            params,
        )
        return [Hit(media_id=row[0], score=0.0) for row in rows]

    lists: list[str] = [
        "q AS (SELECT websearch_to_tsquery('german', :text) AS query,"
        " websearch_to_tsquery('simple', :text) AS plain)"
    ]
    names: list[str] = []
    params["text"] = words

    if image is not None and image.vector:
        lists.append(_vector_list(VectorKind.IMAGE, image, "pictures", IMAGE_MAX_DISTANCE, where))
        params["pictures_vector"] = _literal(image.vector)
        names.append("pictures")
    if caption is not None and caption.vector:
        lists.append(
            _vector_list(VectorKind.CAPTION, caption, "meanings", CAPTION_MAX_DISTANCE, where)
        )
        params["meanings_vector"] = _literal(caption.vector)
        names.append("meanings")
    lists.append(_WORDS.format(where=where, candidates=CANDIDATES))
    names.append("words")
    lists.append(
        _NAMES.format(where=where, candidates=CANDIDATES, min_similarity=NAME_MIN_SIMILARITY)
    )
    names.append("names")

    union = " UNION ALL ".join(
        f"SELECT media_id, rank, moment, source FROM {name}"  # noqa: S608 - fixed list names
        for name in names
    )
    statement = f"""
        WITH {", ".join(lists)},
        ranked AS ({union}),
        confirmed AS (
            SELECT r.* FROM ranked r
             WHERE r.source <> 'pictures'
                OR EXISTS (SELECT 1 FROM ranked o
                            WHERE o.media_id = r.media_id AND o.source <> 'pictures')
                OR (r.rank <= {IMAGE_ALONE}
                    AND NOT EXISTS (SELECT 1 FROM media_analyses x WHERE x.media_id = r.media_id))
        )
        SELECT media_id,
               sum(1.0 / ({RRF_K} + rank)) AS score,
               (array_agg(moment ORDER BY rank) FILTER (WHERE moment IS NOT NULL))[1] AS moment
          FROM confirmed
         GROUP BY media_id
         ORDER BY score DESC, media_id
    """  # noqa: S608 - pieces are fixed or come from VectorKind; every value is bound

    # The index returns only as many rows as it searched; 200 candidates need a search that wide,
    # and a narrow filter needs the index to keep looking instead of stopping short.
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {CANDIDATES}"))
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    # The <% operator filters with its own threshold, 0.6 unless told otherwise - stricter than
    # the one the names are judged by, and "Italen" for "Italien" is 0.57.
    await session.execute(
        text(f"SET LOCAL pg_trgm.word_similarity_threshold = {float(NAME_MIN_SIMILARITY)}")
    )
    rows = await session.execute(text(statement), params)
    return [Hit(media_id=row.media_id, score=float(row.score), moment=row.moment) for row in rows]


async def similar(
    session: AsyncSession, media_id: uuid.UUID, *, model: str, filters: Filters | None = None
) -> list[Hit]:
    """Media whose picture vector lies nearest to this one's, the medium itself left out."""
    stored = await session.execute(
        text(
            _sql(
                "SELECT embedding::text AS vector, dimensions FROM {table} "
                "WHERE media_id = :media_id AND model = :model",
                VectorKind.IMAGE,
            )
        ),
        {"media_id": media_id, "model": model},
    )
    row = stored.first()
    if row is None:
        return []

    where, params = _filter_sql(filters or Filters())
    dimensions = int(row.dimensions)
    cast = f"e.embedding::halfvec({dimensions})"
    params |= {"vector": row.vector, "media_id": media_id}
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {CANDIDATES}"))
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    rows = await session.execute(
        text(
            _sql(
                f"""
                SELECT e.media_id, {cast} <=> CAST(:vector AS halfvec({dimensions})) AS distance
                  FROM {{table}} e
                  JOIN media m ON m.id = e.media_id
                  JOIN albums a ON a.id = m.album_id
                 WHERE e.model = {_quoted(model)} AND e.dimensions = {dimensions}
                   AND e.media_id <> :media_id AND {where}
                 ORDER BY {cast} <=> CAST(:vector AS halfvec({dimensions}))
                 LIMIT {CANDIDATES}
                """,  # noqa: S608 - cast and model are ours; values are bound
                VectorKind.IMAGE,
            )
        ),
        params,
    )
    return [Hit(media_id=r.media_id, score=1.0 - float(r.distance)) for r in rows]


def page_of(hits: Sequence[Hit], *, offset: int, limit: int) -> tuple[list[Hit], int | None]:
    """One page of an already ranked list, and where the next one starts."""
    chunk = list(hits[offset : offset + limit])
    following = offset + limit if offset + limit < len(hits) else None
    return chunk, following


# --- a whole search, from the words typed to one page of media -----------------------------


@dataclass(frozen=True, slots=True)
class Abilities:
    """What a search can look into, by the models in use - not whether their machine answers."""

    #: A picture model: words find what pictures show, and a picture finds others like it.
    pictures: bool
    #: A word model: descriptions are found by what they mean, not only by their words.
    meanings: bool
    #: Whether the machine behind them answers at this moment. False while it rests after not
    #: answering, so the app can offer the plain search rather than promise more than it can do.
    ready: bool


async def _resting(redis: Redis, kind: AiKind) -> bool:
    """Whether this model is being left alone because its machine did not answer.

    The same pause the worker sets and the engine room shows, so a search, the pipeline and the
    admin area all agree about a machine that is away.
    """
    found: Any = await redis.exists(jobs.pause_key(STAGE_OF[kind]))
    return int(found) == 1


async def abilities(session: AsyncSession, redis: Redis) -> Abilities:
    pictures = await ai_service.active_profile(session, AiKind.IMAGE_EMBEDDER)
    meanings = await ai_service.active_profile(session, AiKind.TEXT_EMBEDDER)
    ready = (pictures is not None and not await _resting(redis, AiKind.IMAGE_EMBEDDER)) or (
        meanings is not None and not await _resting(redis, AiKind.TEXT_EMBEDDER)
    )
    return Abilities(pictures=pictures is not None, meanings=meanings is not None, ready=ready)


@dataclass(frozen=True, slots=True)
class Found:
    hits: list[Hit]
    media: dict[uuid.UUID, Media]
    next_offset: int | None
    understood: ParsedQuery
    #: True when the AI server could not be asked, so only words and names were searched.
    degraded: bool


async def _probe(
    redis: Redis, kind: AiKind, profile: AiProfile | None, words: str
) -> tuple[Probe | None, bool]:
    """The words as a vector of this profile's model; nothing when there is no profile.

    A machine that did not answer a moment ago is not asked again: it is resting, and every
    search would otherwise wait out the timeout to learn what the last one already knew. A
    failed request is reported rather than raised - the search goes on without it - and puts the
    machine to rest, so the workers stop asking too.
    """
    if profile is None or not words:
        return None, False
    if await _resting(redis, kind):
        return None, True
    try:
        embedder = ai_service.embedder_for(profile, timeout_seconds=PROBE_TIMEOUT_SECONDS)
        (vector,) = await embedder.embed([words])
    except AiError as error:
        logger.warning("Search without %s: %s", profile.model, error)
        await redis.set(jobs.pause_key(STAGE_OF[kind]), "1", ex=jobs.AI_PAUSE_SECONDS)
        return None, True
    return Probe(vector=vector, model=profile.model), False


async def find(
    session: AsyncSession,
    redis: Redis,
    query: str,
    *,
    filters: Filters,
    by_date: bool = False,
    offset: int = 0,
    limit: int = 60,
) -> Found:
    understood = parse(query)
    persons = await people.persons_in(session, understood.text)
    places = await places_service.places_in(session, persons.text)
    understood = replace(understood, text=places.text, places=places.phrases, persons=persons.names)
    merged = Filters(
        date_from=filters.date_from or understood.date_from,
        date_until=filters.date_until or understood.date_until,
        kind=filters.kind or understood.kind,
        album_path=filters.album_path,
        camera=filters.camera,
        # What the words named, and what was chosen beside them: both narrow.
        place_keys=tuple(dict.fromkeys((*filters.place_keys, *places.keys))),
        person_ids=persons.person_ids,
    )

    pictures = await ai_service.active_profile(session, AiKind.IMAGE_EMBEDDER)
    meanings = await ai_service.active_profile(session, AiKind.TEXT_EMBEDDER)
    (image, image_failed), (caption, caption_failed) = await asyncio.gather(
        _probe(redis, AiKind.IMAGE_EMBEDDER, pictures, understood.text),
        _probe(redis, AiKind.TEXT_EMBEDDER, meanings, understood.text),
    )

    hits = await search(
        session, words=understood.text, filters=merged, image=image, caption=caption
    )
    if by_date and understood.text:
        hits = await _newest_first(session, hits)

    chunk, following = page_of(hits, offset=offset, limit=limit)
    return Found(
        hits=chunk,
        media=await _media_of(session, [hit.media_id for hit in chunk]),
        next_offset=following,
        understood=understood,
        degraded=image_failed or caption_failed,
    )


async def find_similar(
    session: AsyncSession, media_id: uuid.UUID, *, offset: int = 0, limit: int = 60
) -> Found:
    pictures = await ai_service.active_profile(session, AiKind.IMAGE_EMBEDDER)
    hits = await similar(session, media_id, model=pictures.model) if pictures is not None else []
    chunk, following = page_of(hits, offset=offset, limit=limit)
    return Found(
        hits=chunk,
        media=await _media_of(session, [hit.media_id for hit in chunk]),
        next_offset=following,
        understood=ParsedQuery(text=""),
        degraded=False,
    )


async def _newest_first(session: AsyncSession, hits: list[Hit]) -> list[Hit]:
    rows = await session.execute(
        select(Media.id, func.coalesce(Media.taken_at, Media.created_at)).where(
            Media.id.in_([hit.media_id for hit in hits])
        )
    )
    when = {row[0]: row[1] for row in rows}
    return sorted(hits, key=lambda hit: when[hit.media_id], reverse=True)


async def _media_of(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Media]:
    if not ids:
        return {}
    rows = await session.scalars(
        select(Media).where(Media.id.in_(ids)).options(selectinload(Media.files))
    )
    return {media.id: media for media in rows}
