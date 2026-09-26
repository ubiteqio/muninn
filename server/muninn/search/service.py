"""Storing vectors, and knowing which media still lack one.

The vectors live in one table per kind with the model as a column (migration 0011). The length
differs per model, so the column has none; what makes a search fast is a partial HNSW index per
model, cast to that model's length, and it is created here the first time a model's vectors
arrive - the only moment the length is known.
"""

import asyncio
import base64
import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.ai.base import AiError, Embedder
from muninn.models.media import Media, MediaStatus

#: Stage 4. Raise it when the way a picture is handed to the model changes; every medium is then
#: asked again, and until then the old vectors keep answering searches.
IMAGE_VECTOR_VERSION = 1

#: Stage 6. Raise it when the text handed to the word model changes.
CAPTION_VECTOR_VERSION = 1


class VectorKind(StrEnum):
    """What a vector stands for. The value is the table it lives in, and nothing else is."""

    IMAGE = "image_embeddings"
    CAPTION = "caption_embeddings"
    #: Many per medium, with their boxes: only ensure_index and the face functions use it.
    FACE = "faces"


class VectorError(Exception):
    """A vector that cannot be stored as it came."""


def _sql(template: str, kind: VectorKind) -> str:
    """The one place a table name goes into SQL - and it is the enum's value, never a caller's.

    Everything else a statement needs is bound as a parameter.
    """
    return template.replace("{table}", kind.value)


def _literal(vector: list[float]) -> str:
    """pgvector reads "[1.0,2.0]"; a bound string is safer than building SQL around numbers."""
    if not vector:
        raise VectorError("An empty vector stands for nothing.")
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


def index_name(kind: VectorKind, model: str, dimensions: int) -> str:
    """A short, stable name per model: identifiers end at 63 characters, model names do not."""
    digest = hashlib.blake2s(f"{kind.value}:{model}:{dimensions}".encode(), digest_size=6)
    return f"ix_{kind.value}_{digest.hexdigest()}"


#: Indexes this process has seen, so a stored vector costs no catalogue lookup after the first.
_known_indexes: set[str] = set()


async def ensure_index(
    session: AsyncSession, kind: VectorKind, model: str, dimensions: int
) -> None:
    """The HNSW index for one model, by cosine, created once.

    The first vectors of a new model arrive in parallel. Two transactions that both create the
    index and then insert wait for each other's table locks, which PostgreSQL ends as a deadlock.
    So whoever comes first takes a lock named after the index for the rest of its transaction,
    and everyone after it finds the index there and only inserts.

    An index statement takes no parameters, so the model name is written in as a literal - with
    its quotes doubled, which is all a PostgreSQL string literal needs. The length is an int by
    the time it gets here.
    """
    if not 0 < dimensions <= 4000:
        raise VectorError(f"{dimensions} dimensions do not fit a half-precision index.")

    name = index_name(kind, model, dimensions)
    if name in _known_indexes:
        return

    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": name})
    exists = await session.scalar(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": name})
    if not exists:
        quoted = model.replace("'", "''")
        await session.execute(
            text(
                f"CREATE INDEX {name} "
                f"ON {kind.value} "
                f"USING hnsw ((embedding::halfvec({int(dimensions)})) halfvec_cosine_ops) "
                # The length as well: a model swapped behind the same name may answer with
                # vectors of another length, and those cannot be cast to this index's.
                f"WHERE model = '{quoted}' AND dimensions = {int(dimensions)}"
            )
        )
        # Only remembered once it exists for everyone, not while this transaction could still
        # roll it back.
        return

    _known_indexes.add(name)


async def store(
    session: AsyncSession,
    kind: VectorKind,
    *,
    media_id: uuid.UUID,
    model: str,
    version: int,
    vector: list[float],
) -> None:
    """Keep a medium's vector for this model, replacing an older one.

    Idempotent: the same medium and model twice is one row, the newer one. The caller commits,
    so a vector and whatever else the stage wrote land together or not at all.
    """
    await ensure_index(session, kind, model, len(vector))
    await session.execute(
        text(
            _sql(
                """
            INSERT INTO {table} (media_id, model, version, dimensions, embedding)
            VALUES (:media_id, :model, :version, :dimensions, CAST(:embedding AS halfvec))
            ON CONFLICT (media_id, model) DO UPDATE
               SET version = EXCLUDED.version,
                   dimensions = EXCLUDED.dimensions,
                   embedding = EXCLUDED.embedding,
                   created_at = now()
            """,
                kind,
            )
        ),
        {
            "media_id": media_id,
            "model": model,
            "version": version,
            "dimensions": len(vector),
            "embedding": _literal(vector),
        },
    )


async def forget(session: AsyncSession, kind: VectorKind, media_id: uuid.UUID) -> None:
    """Drop every vector of this kind for a medium, so the stage that makes them runs again.

    A caption vector stands for one caption; when stage 5 writes a new one, the old vector
    would keep answering searches for words that are no longer there.
    """
    await session.execute(
        text(_sql("DELETE FROM {table} WHERE media_id = :media_id", kind)),
        {"media_id": media_id},
    )


async def has_vector(session: AsyncSession, kind: VectorKind, media_id: uuid.UUID) -> bool:
    """Whether this medium has a vector of this kind at all - for the admin's view of a medium."""
    found = await session.scalar(
        text(_sql("SELECT 1 FROM {table} WHERE media_id = :media_id LIMIT 1", kind)),
        {"media_id": media_id},
    )
    return found is not None


async def media_without(
    session: AsyncSession, kind: VectorKind, *, model: str, version: int, limit: int = 200
) -> list[uuid.UUID]:
    """Media that could have a vector for this model and have none - or one from an older stage.

    Only media with a thumbnail: that is what the picture model reads, and until stage 3 has made
    it there is nothing to look at. Newest first, the way the concept asks for the second wave.
    """
    rows = await session.execute(
        text(
            _sql(
                """
            SELECT m.id
              FROM media m
             WHERE m.status = :active
               AND m.thumbnail_path IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM {table} e
                    WHERE e.media_id = m.id AND e.model = :model AND e.version >= :version
               )
             ORDER BY coalesce(m.taken_at, m.created_at) DESC, m.id
             LIMIT :limit
            """,
                kind,
            )
        ),
        {"active": MediaStatus.ACTIVE.value, "model": model, "version": version, "limit": limit},
    )
    return [row[0] for row in rows]


async def count_without(
    session: AsyncSession, kind: VectorKind, *, model: str, version: int
) -> int:
    """How many are still missing, for the engine room."""
    count = await session.scalar(
        text(
            _sql(
                """
            SELECT count(*)
              FROM media m
             WHERE m.status = :active
               AND m.thumbnail_path IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM {table} e
                    WHERE e.media_id = m.id AND e.model = :model AND e.version >= :version
               )
            """,
                kind,
            )
        ),
        {"active": MediaStatus.ACTIVE.value, "model": model, "version": version},
    )
    return int(count or 0)


async def apply_image_vector(
    session: AsyncSession,
    media_id: uuid.UUID,
    *,
    embedder: Embedder,
    model: str,
    derived_root: Path,
) -> bool:
    """Stage 4 for one medium: the picture model looks at its thumbnail.

    The thumbnail and not the original: it is on the SSD rather than the NAS, it is already a
    still for videos, and at 400 pixels it is more than SigLIP's 384 ever look at. Returns
    whether a vector was stored; a medium that has one, or has nothing to look at, is skipped.
    """
    media = await session.get(Media, media_id)
    if media is None or media.status is not MediaStatus.ACTIVE or media.thumbnail_path is None:
        return False

    stored = await session.scalar(
        text(
            _sql(
                "SELECT version FROM {table} WHERE media_id = :media_id AND model = :model",
                VectorKind.IMAGE,
            )
        ),
        {"media_id": media_id, "model": model},
    )
    if stored is not None and stored >= IMAGE_VECTOR_VERSION:
        return False

    try:
        picture = await asyncio.to_thread((derived_root / media.thumbnail_path).read_bytes)
    except FileNotFoundError:
        # Stage 3 will make it again; until then there is nothing to look at.
        return False

    (vector,) = await embedder.embed([_data_url(picture, media.thumbnail_path)])
    if not vector:
        raise AiError(f"{model} answered with an empty vector.")

    await store(
        session,
        VectorKind.IMAGE,
        media_id=media_id,
        model=model,
        version=IMAGE_VECTOR_VERSION,
        vector=vector,
    )
    await session.commit()
    return True


_MIME_TYPES = {".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _data_url(picture: bytes, name: str) -> str:
    """How the OpenAI embeddings API spells a picture."""
    mime = _MIME_TYPES.get(Path(name).suffix.lower(), "image/webp")
    return f"data:{mime};base64,{base64.b64encode(picture).decode('ascii')}"


_CAPTIONS_WITHOUT = """
    FROM media m
    JOIN media_analyses a ON a.media_id = m.id
   WHERE m.status = :active
     AND NOT EXISTS (
         SELECT 1 FROM {table} e
          WHERE e.media_id = m.id AND e.model = :model AND e.version >= :version
     )
"""


async def captions_without(
    session: AsyncSession, *, model: str, version: int = CAPTION_VECTOR_VERSION, limit: int = 200
) -> list[uuid.UUID]:
    """Media that have a caption and no vector of it from this word model, newest first."""
    rows = await session.execute(
        text(
            _sql(
                "SELECT m.id"
                + _CAPTIONS_WITHOUT
                + " ORDER BY coalesce(m.taken_at, m.created_at) DESC, m.id LIMIT :limit",
                VectorKind.CAPTION,
            )
        ),
        {"active": MediaStatus.ACTIVE.value, "model": model, "version": version, "limit": limit},
    )
    return [row[0] for row in rows]


async def count_captions_without(
    session: AsyncSession, *, model: str, version: int = CAPTION_VECTOR_VERSION
) -> int:
    count = await session.scalar(
        text(_sql("SELECT count(*)" + _CAPTIONS_WITHOUT, VectorKind.CAPTION)),
        {"active": MediaStatus.ACTIVE.value, "model": model, "version": version},
    )
    return int(count or 0)


async def apply_caption_vector(
    session: AsyncSession, media_id: uuid.UUID, *, embedder: Embedder, model: str
) -> bool:
    """Stage 6 for one medium: the meaning of its caption and tags as a vector.

    Returns whether a vector was stored. Nothing to do without a caption, or with a vector
    from this model and version already there.
    """
    row = (
        await session.execute(
            text(
                _sql(
                    """
                SELECT a.caption, a.tags, e.version
                  FROM media_analyses a
                  LEFT JOIN {table} e ON e.media_id = a.media_id AND e.model = :model
                 WHERE a.media_id = :media_id
                """,
                    VectorKind.CAPTION,
                )
            ),
            {"media_id": media_id, "model": model},
        )
    ).first()
    if row is None:
        return False
    caption, tags, stored = row
    if stored is not None and stored >= CAPTION_VECTOR_VERSION:
        return False

    (vector,) = await embedder.embed([caption_text(caption, list(tags or []))])
    if not vector:
        raise AiError(f"{model} answered with an empty vector.")

    await store(
        session,
        VectorKind.CAPTION,
        media_id=media_id,
        model=model,
        version=CAPTION_VECTOR_VERSION,
        vector=vector,
    )
    await session.commit()
    return True


def caption_text(caption: str, tags: list[str]) -> str:
    """What the word model reads: the caption, and the tags as the words it should weigh."""
    if not tags:
        return caption
    return f"{caption} Stichwörter: {', '.join(tags)}."


async def burst_pairs(
    session: AsyncSession, *, model: str, window_seconds: int, max_distance: float
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Photos taken within a few seconds of each other whose pictures are nearly the same: the
    shots of a burst. Only exact capture times count - a date from a folder name puts a whole
    day on midnight - and only pictures, not videos."""
    rows = await session.execute(
        text(
            _sql(
                """
                WITH timed AS (
                    SELECT id, taken_at FROM media
                     WHERE status = 'active' AND kind = 'image' AND taken_at IS NOT NULL
                       AND taken_at_source IN ('exif', 'gps')
                )
                SELECT a.id AS first, b.id AS second
                  FROM timed a
                  JOIN LATERAL (
                        SELECT id FROM media n
                         WHERE n.taken_at BETWEEN a.taken_at AND a.taken_at
                               + make_interval(secs => CAST(:window AS float))
                           AND (n.taken_at > a.taken_at OR n.id > a.id)
                           AND n.status = 'active' AND n.kind = 'image'
                           AND n.taken_at_source IN ('exif', 'gps')
                       ) b ON true
                  JOIN {table} ea ON ea.media_id = a.id AND ea.model = :model
                  JOIN {table} eb ON eb.media_id = b.id AND eb.model = :model
                 WHERE ea.dimensions = eb.dimensions
                   AND ea.embedding <=> eb.embedding <= :max_distance
                """,
                VectorKind.IMAGE,
            )
        ),
        {"model": model, "window": window_seconds, "max_distance": max_distance},
    )
    return [(row.first, row.second) for row in rows]


async def near_pairs(
    session: AsyncSession, *, album_id: uuid.UUID, model: str, max_distance: float
) -> list[tuple[uuid.UUID, uuid.UUID, float]]:
    """Which media of one album look alike, and how alike - for the chapters of the Smarts.

    Every pair of one album, once, and only those below the distance. An album of a few thousand
    is a few million comparisons of halfvecs, which PostgreSQL does in about a second and which
    nobody waits for: this runs in a worker, not in a request.
    """
    rows = await session.execute(
        text(
            _sql(
                """
                WITH pool AS (
                    SELECT e.media_id, e.embedding::halfvec AS v
                      FROM {table} e JOIN media m ON m.id = e.media_id
                     WHERE m.album_id = :album AND m.status = 'active'
                       AND m.duplicate_of IS NULL AND e.model = :model
                )
                SELECT a.media_id AS first, b.media_id AS second, (a.v <=> b.v) AS distance
                  FROM pool a JOIN pool b ON a.media_id < b.media_id
                 WHERE a.v <=> b.v <= :max_distance
                """,
                VectorKind.IMAGE,
            )
        ),
        {"album": album_id, "model": model, "max_distance": max_distance},
    )
    return [(row.first, row.second, float(row.distance)) for row in rows]


# --- faces ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FaceToStore:
    box: tuple[float, float, float, float]
    score: float
    pixels: int
    second: float | None
    embedding: list[float]
    aspect: float = 1.0


async def store_faces(
    session: AsyncSession, media_id: uuid.UUID, *, model: str, faces: list[FaceToStore]
) -> list[uuid.UUID]:
    """Replace a medium's faces with these. The caller commits. Returns the new faces' ids.

    Who the old faces were is not carried over by position - a changed picture may hold other
    people - but their persons find them again: the new faces are assigned afresh.
    """
    await session.execute(
        text("DELETE FROM faces WHERE media_id = :media_id"), {"media_id": media_id}
    )
    ids: list[uuid.UUID] = []
    for face in faces:
        await ensure_index(session, VectorKind.FACE, model, len(face.embedding))
        face_id = uuid.uuid4()
        await session.execute(
            text(
                """
                INSERT INTO faces (id, media_id, box_left, box_top, box_right, box_bottom, score,
                                   pixels, second, aspect, model, dimensions, embedding)
                VALUES (:id, :media_id, :left, :top, :right, :bottom, :score, :pixels, :second,
                        :aspect, :model, :dimensions, CAST(:embedding AS halfvec))
                """
            ),
            {
                "id": face_id,
                "media_id": media_id,
                "left": face.box[0],
                "top": face.box[1],
                "right": face.box[2],
                "bottom": face.box[3],
                "score": face.score,
                "pixels": face.pixels,
                "second": face.second,
                "aspect": face.aspect,
                "model": model,
                "dimensions": len(face.embedding),
                "embedding": _literal(face.embedding),
            },
        )
        ids.append(face_id)
    return ids


@dataclass(frozen=True, slots=True)
class FaceNeighbor:
    face_id: uuid.UUID
    person_id: uuid.UUID | None
    cluster: int | None
    distance: float
    #: "user" for a face somebody confirmed, "auto" for one Muninn gave its person.
    assigned_by: str | None = None


async def face_neighbors(
    session: AsyncSession,
    face_id: uuid.UUID,
    *,
    named: bool,
    max_distance: float,
    limit: int = 10,
    confirmed: bool = False,
    min_pixels: int = 0,
    min_score: float = 0.0,
    suggested_for: uuid.UUID | None = None,
) -> list[FaceNeighbor]:
    """The faces nearest to this one - of named persons, or without a person - nearest first.

    `confirmed` keeps to the faces that may vouch for a name: what somebody assigned by hand,
    and what Muninn assigned itself and marked trusted. Asked apart, not filtered afterwards:
    copies and bursts of a photo fill the ten nearest with Muninn's own guesses, and the
    confirmed face that should decide would never be among them.

    `suggested_for` keeps to the faces that are an open question about that one person, which is
    what answering several of them at once is about.

    `min_pixels` and `min_score` are the caller's bar for a face good enough to be listened to.
    A small or unsure face is kept and can still be given a name, but its vector says too little
    to group anybody or to vouch for them, and those are the faces that glue unrelated groups
    together. A decision somebody made by hand is never held to this bar: the person is right
    whatever the picture is like.

    Only faces of the same model count: another model's vectors live in another space.
    """
    stored = await session.execute(
        text("SELECT embedding::text AS vector, dimensions, model FROM faces WHERE id = :id"),
        {"id": face_id},
    )
    row = stored.first()
    if row is None:
        return []
    dimensions = int(row.dimensions)
    cast = f"f.embedding::halfvec({dimensions})"
    probe = f"CAST(:vector AS halfvec({dimensions}))"
    which = "f.person_id IS NOT NULL" if named else "f.person_id IS NULL"
    good = _good_enough(min_pixels, min_score)
    if confirmed:
        trusted = f"f.trusted AND {good}" if good else "f.trusted"
        which += f" AND (f.assigned_by = 'user' OR ({trusted}))"
    elif good:
        which += f" AND {good}"
    if suggested_for is not None:
        which += " AND f.suggested_person_id = :suggested_for"
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {max(40, limit * 4)}"))
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    rows = await session.execute(
        text(
            f"""
            SELECT id, person_id, cluster, assigned_by, distance FROM (
                SELECT f.id, f.person_id, f.cluster, f.assigned_by,
                       {cast} <=> {probe} AS distance
                  FROM faces f
                 WHERE f.model = {_quoted(row.model)} AND f.dimensions = {dimensions}
                   AND f.id <> :id AND {which}
                 ORDER BY {cast} <=> {probe}
                 LIMIT {int(limit)}
            ) nearest
             WHERE distance <= :max_distance
             ORDER BY distance
            """  # noqa: S608 - the cast, the model literal and the condition are ours
        ),
        {
            "vector": row.vector,
            "id": face_id,
            "max_distance": max_distance,
            "suggested_for": suggested_for,
        },
    )
    return [
        FaceNeighbor(
            face_id=r.id,
            person_id=r.person_id,
            cluster=r.cluster,
            distance=float(r.distance),
            assigned_by=r.assigned_by,
        )
        for r in rows
    ]


async def distance_to_clusters(
    session: AsyncSession, face_id: uuid.UUID, clusters: Sequence[int]
) -> dict[int, float]:
    """How far this face lies from the middle of each of those groups.

    The middle is the average of the group's faces. Asking it, rather than whichever single face
    happens to be nearest, is what keeps one face between two groups from tying them together.
    """
    if not clusters:
        return {}
    stored = await session.execute(
        text("SELECT embedding::text AS vector, dimensions, model FROM faces WHERE id = :id"),
        {"id": face_id},
    )
    row = stored.first()
    if row is None:
        return {}
    dimensions = int(row.dimensions)
    wanted = ", ".join(str(int(cluster)) for cluster in clusters)
    rows = await session.execute(
        text(
            f"""
            SELECT cluster,
                   avg(embedding::vector({dimensions}))
                       <=> CAST(:vector AS vector({dimensions})) AS distance
              FROM faces
             WHERE cluster IN ({wanted})
               AND model = {_quoted(row.model)} AND dimensions = {dimensions}
             GROUP BY cluster
            """  # noqa: S608 - the cast, the model literal and the group numbers are ours
        ),
        {"vector": row.vector},
    )
    return {int(r.cluster): float(r.distance) for r in rows}


async def gap_between_clusters(session: AsyncSession, first: int, second: int) -> float:
    """How far the middles of two groups lie apart. 1.0 - unrelated - when one has no faces."""
    found = await session.scalar(
        text(
            f"""
            WITH centers AS (
                SELECT cluster, avg(embedding::vector) AS center
                  FROM faces
                 WHERE cluster IN ({int(first)}, {int(second)})
                 GROUP BY cluster
            )
            SELECT (SELECT center FROM centers WHERE cluster = {int(first)})
                   <=> (SELECT center FROM centers WHERE cluster = {int(second)})
            """  # noqa: S608 - both group numbers are ours
        )
    )
    return float(found) if found is not None else 1.0


@dataclass(frozen=True, slots=True)
class PersonVectors:
    """The vectors that speak for a person, and the space they live in."""

    model: str
    dimensions: int
    vectors: list[list[float]]


async def vouching_vectors(session: AsyncSession, person_id: uuid.UUID) -> PersonVectors | None:
    """The vectors of the faces that may speak for this person: confirmed, or trusted and good.

    None when there are none, or when they are not all of one model - a person whose faces were
    found by two models has no one space to be averaged in.
    """
    rows = await session.execute(
        text(
            """
            SELECT embedding::text AS vector, dimensions, model
              FROM faces
             WHERE person_id = :person_id
               AND (assigned_by = 'user' OR trusted)
             ORDER BY id
            """
        ),
        {"person_id": person_id},
    )
    found = list(rows)
    if not found:
        return None
    models = {(r.model, int(r.dimensions)) for r in found}
    if len(models) != 1:
        return None
    (model, dimensions) = models.pop()
    return PersonVectors(
        model=model,
        dimensions=dimensions,
        vectors=[[float(part) for part in r.vector.strip("[]").split(",")] for r in found],
    )


async def store_prototypes(
    session: AsyncSession,
    person_id: uuid.UUID,
    *,
    model: str,
    centers: list[tuple[list[float], int]],
) -> None:
    """Replace what stands for this person. The caller commits."""
    await session.execute(
        text("DELETE FROM person_prototypes WHERE person_id = :person_id"),
        {"person_id": person_id},
    )
    for center, faces in centers:
        await session.execute(
            text(
                """
                INSERT INTO person_prototypes (id, person_id, model, dimensions, center, faces)
                VALUES (:id, :person_id, :model, :dimensions, CAST(:center AS halfvec), :faces)
                """
            ),
            {
                "id": uuid.uuid4(),
                "person_id": person_id,
                "model": model,
                "dimensions": len(center),
                "center": _literal(center),
                "faces": faces,
            },
        )


@dataclass(frozen=True, slots=True)
class PrototypeNeighbor:
    person_id: uuid.UUID
    distance: float
    faces: int


async def prototype_neighbors(
    session: AsyncSession, face_id: uuid.UUID, *, max_distance: float, limit: int = 5
) -> list[PrototypeNeighbor]:
    """The persons whose middles lie nearest this face, nearest first.

    One middle per way a person looked, so a face of somebody at two is asked against the middle
    of their other baby photos and not against the average of a lifetime.
    """
    stored = await session.execute(
        text("SELECT embedding::text AS vector, dimensions, model FROM faces WHERE id = :id"),
        {"id": face_id},
    )
    row = stored.first()
    if row is None:
        return []
    dimensions = int(row.dimensions)
    rows = await session.execute(
        text(
            f"""
            SELECT person_id, faces, center::halfvec({dimensions})
                   <=> CAST(:vector AS halfvec({dimensions})) AS distance
              FROM person_prototypes
             WHERE model = {_quoted(row.model)} AND dimensions = {dimensions}
             ORDER BY distance
             LIMIT {int(limit)}
            """  # noqa: S608 - the cast and the model literal are ours
        ),
        {"vector": row.vector},
    )
    return [
        PrototypeNeighbor(person_id=r.person_id, distance=float(r.distance), faces=int(r.faces))
        for r in rows
        if float(r.distance) <= max_distance
    ]


def _good_enough(min_pixels: int, min_score: float) -> str:
    """The caller's quality bar as SQL, or nothing when it does not care."""
    parts = []
    if min_pixels > 0:
        parts.append(f"f.pixels >= {int(min_pixels)}")
    if min_score > 0:
        parts.append(f"f.score >= {float(min_score)}")
    return " AND ".join(parts)


def _quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
