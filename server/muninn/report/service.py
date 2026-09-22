"""The library at a glance - "Überblick", the same for everybody: counts and shares, never single
media.

Every figure is one aggregate over the tables Muninn keeps anyway. Media gone from the NAS and
copies hidden as duplicates are left out, so the numbers match what the albums show.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: The media the albums show.
_SHOWN = "m.status = 'active' AND m.duplicate_of IS NULL"


@dataclass(slots=True)
class Report:
    totals: dict[str, Any] = field(default_factory=dict)
    years: list[dict[str, Any]] = field(default_factory=list)
    pipeline: list[dict[str, Any]] = field(default_factory=list)
    content: dict[str, float] = field(default_factory=dict)
    tags: list[dict[str, Any]] = field(default_factory=list)
    scenes: list[dict[str, Any]] = field(default_factory=list)
    times_of_day: list[dict[str, Any]] = field(default_factory=list)
    people: dict[str, float] = field(default_factory=dict)
    persons: list[dict[str, Any]] = field(default_factory=list)
    places: dict[str, float] = field(default_factory=dict)
    countries: list[dict[str, Any]] = field(default_factory=list)
    towns: list[dict[str, Any]] = field(default_factory=list)
    date_sources: list[dict[str, Any]] = field(default_factory=list)
    cameras: list[dict[str, Any]] = field(default_factory=list)
    duplicates: dict[str, float] = field(default_factory=dict)
    social: dict[str, float] = field(default_factory=dict)


async def _one(session: AsyncSession, sql: str) -> dict[str, Any]:
    row = (await session.execute(text(sql))).mappings().one()
    return {key: (value if value is not None else 0) for key, value in row.items()}


async def _rows(session: AsyncSession, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in (await session.execute(text(sql))).mappings()]


async def build(session: AsyncSession) -> Report:
    report = Report()

    report.totals = await _one(
        session,
        f"""
        SELECT count(*) AS media,
               count(*) FILTER (WHERE m.kind = 'image') AS photos,
               count(*) FILTER (WHERE m.kind = 'video') AS videos,
               coalesce(sum(f.byte_size), 0) AS bytes,
               coalesce(sum(m.derived_bytes), 0) AS derived_bytes,
               coalesce(sum(m.duration_seconds), 0) AS video_seconds,
               (SELECT count(*) FROM albums WHERE is_source) AS albums,
               min(m.taken_at) AS first_taken,
               max(m.taken_at) AS last_taken
          FROM media m JOIN media_files f ON f.media_id = m.id AND f.role = 'primary'
         WHERE {_SHOWN}
        """,  # noqa: S608 - fixed SQL
    )
    for key in ("first_taken", "last_taken"):
        value = report.totals[key]
        report.totals[key] = value.isoformat() if value else None

    report.years = await _rows(
        session,
        f"""
        SELECT extract(year FROM m.taken_at)::int AS year,
               count(*) FILTER (WHERE m.kind = 'image') AS photos,
               count(*) FILTER (WHERE m.kind = 'video') AS videos
          FROM media m
         WHERE {_SHOWN} AND m.taken_at IS NOT NULL
         GROUP BY 1 ORDER BY 1
        """,  # noqa: S608
    )

    report.pipeline = await _pipeline(session)

    report.content = await _one(
        session,
        f"""
        SELECT (SELECT count(*) FROM video_frames v JOIN media m ON m.id = v.media_id
                 WHERE {_SHOWN}) AS frames,
               (SELECT count(*) FROM media_transcripts t JOIN media m ON m.id = t.media_id
                 WHERE {_SHOWN} AND jsonb_array_length(t.segments) > 0) AS videos_with_speech,
               (SELECT coalesce(sum((s->>'end')::float - (s->>'start')::float), 0)
                  FROM media_transcripts t JOIN media m ON m.id = t.media_id,
                       jsonb_array_elements(t.segments) s
                 WHERE {_SHOWN}) AS spoken_seconds,
               (SELECT count(*) FROM media_analyses a JOIN media m ON m.id = a.media_id
                 WHERE {_SHOWN} AND a.is_screenshot) AS screenshots,
               (SELECT count(*) FROM media_analyses a JOIN media m ON m.id = a.media_id
                 WHERE {_SHOWN} AND a.is_document) AS documents,
               (SELECT count(*) FROM media_analyses a JOIN media m ON m.id = a.media_id
                 WHERE {_SHOWN} AND a.ocr_text <> '') AS with_text
        """,  # noqa: S608
    )
    report.tags = await _rows(
        session,
        f"""
        SELECT tag, count(*) AS count
          FROM media_analyses a JOIN media m ON m.id = a.media_id, unnest(a.tags) tag
         WHERE {_SHOWN}
         GROUP BY tag ORDER BY count DESC, tag LIMIT 24
        """,  # noqa: S608
    )
    report.scenes = await _rows(
        session,
        f"""
        SELECT a.scene AS name, count(*) AS count
          FROM media_analyses a JOIN media m ON m.id = a.media_id
         WHERE {_SHOWN} AND a.scene <> ''
         GROUP BY 1 ORDER BY count DESC LIMIT 8
        """,  # noqa: S608
    )
    report.times_of_day = await _rows(
        session,
        f"""
        SELECT a.time_of_day AS name, count(*) AS count
          FROM media_analyses a JOIN media m ON m.id = a.media_id
         WHERE {_SHOWN}
         GROUP BY 1 ORDER BY count DESC
        """,  # noqa: S608
    )

    report.people = await _one(
        session,
        f"""
        SELECT count(*) AS faces,
               count(*) FILTER (WHERE f.person_id IS NOT NULL AND NOT coalesce(p.hidden, false))
                   AS named,
               count(*) FILTER (WHERE f.person_id IS NULL AND f.suggested_person_id IS NOT NULL)
                   AS suggested,
               count(*) FILTER (WHERE f.person_id IS NULL) AS unnamed,
               count(DISTINCT f.cluster) FILTER (WHERE f.person_id IS NULL) AS groups,
               (SELECT count(*) FROM persons WHERE NOT hidden) AS persons,
               count(DISTINCT f.media_id) AS media_with_faces
          FROM faces f JOIN media m ON m.id = f.media_id
          LEFT JOIN persons p ON p.id = f.person_id
         WHERE {_SHOWN}
        """,  # noqa: S608
    )
    report.persons = await _rows(
        session,
        f"""
        SELECT p.id, p.name, count(DISTINCT f.media_id) AS media,
               (SELECT c.id FROM faces c WHERE c.person_id = p.id
                 ORDER BY c.pixels * c.score DESC LIMIT 1) AS cover_id
          FROM persons p JOIN faces f ON f.person_id = p.id JOIN media m ON m.id = f.media_id
         WHERE {_SHOWN} AND NOT p.hidden
         GROUP BY p.id ORDER BY media DESC, p.name LIMIT 12
        """,  # noqa: S608
    )

    report.places = await _one(
        session,
        f"""
        SELECT count(*) FILTER (WHERE m.latitude IS NOT NULL) AS with_gps,
               count(*) FILTER (WHERE m.place_estimated) AS estimated,
               count(DISTINCT m.place_id) AS towns,
               count(DISTINCT pl.country_code) AS countries
          FROM media m LEFT JOIN places pl ON pl.id = m.place_id
         WHERE {_SHOWN}
        """,  # noqa: S608
    )
    report.countries = await _rows(
        session,
        f"""
        SELECT coalesce(pl.country, pl.country_code) AS name, count(*) AS count
          FROM media m JOIN places pl ON pl.id = m.place_id
         WHERE {_SHOWN}
         GROUP BY 1 ORDER BY count DESC LIMIT 8
        """,  # noqa: S608
    )
    report.towns = await _rows(
        session,
        f"""
        SELECT pl.name, pl.country, count(*) AS count
          FROM media m JOIN places pl ON pl.id = m.place_id
         WHERE {_SHOWN}
         GROUP BY pl.id ORDER BY count DESC LIMIT 8
        """,  # noqa: S608
    )

    report.date_sources = await _rows(
        session,
        f"""
        SELECT coalesce(m.taken_at_source::text, 'unknown') AS name, count(*) AS count
          FROM media m WHERE {_SHOWN} GROUP BY 1 ORDER BY count DESC
        """,  # noqa: S608
    )
    report.cameras = await _rows(
        session,
        f"""
        SELECT trim(coalesce(m.camera_make, '') || ' ' || m.camera_model) AS name,
               count(*) AS count
          FROM media m WHERE {_SHOWN} AND m.camera_model IS NOT NULL
         GROUP BY 1 ORDER BY count DESC LIMIT 8
        """,  # noqa: S608
    )

    report.duplicates = await _one(
        session,
        """
        SELECT (SELECT count(*) FROM duplicate_groups) AS groups,
               (SELECT count(*) FROM duplicate_groups WHERE kind = 'exact') AS exact,
               (SELECT count(*) FROM duplicate_groups WHERE kind = 'near') AS near,
               (SELECT count(*) FROM duplicate_groups WHERE kind = 'burst') AS burst,
               (SELECT count(*) FROM media WHERE duplicate_of IS NOT NULL) AS hidden
        """,
    )
    report.social = await _one(
        session,
        """
        SELECT (SELECT count(*) FROM likes WHERE media_id IS NOT NULL) AS reactions,
               (SELECT count(*) FROM comments WHERE deleted_at IS NULL) AS comments,
               (SELECT count(*) FROM favorites) AS favorites,
               (SELECT count(*) FROM users WHERE status = 'active') AS users
        """,
    )
    return report


async def _pipeline(session: AsyncSession) -> list[dict[str, Any]]:
    steps = await _one(
        session,
        f"""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE m.kind = 'video') AS videos,
               count(*) FILTER (WHERE m.metadata_version > 0) AS metadata,
               count(*) FILTER (WHERE m.thumbnail_path IS NOT NULL) AS previews,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM image_embeddings e
                                               WHERE e.media_id = m.id)) AS image_vectors,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM media_analyses a
                                               WHERE a.media_id = m.id)) AS descriptions,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM caption_embeddings c
                                               WHERE c.media_id = m.id)) AS caption_vectors,
               count(*) FILTER (WHERE m.kind = 'video' AND EXISTS (
                   SELECT 1 FROM media_transcripts t WHERE t.media_id = m.id)) AS transcripts,
               count(*) FILTER (WHERE m.face_version > 0) AS faces,
               count(*) FILTER (WHERE m.place_id IS NOT NULL) AS places
          FROM media m
         WHERE {_SHOWN}
        """,  # noqa: S608
    )
    total, videos = int(steps["total"]), int(steps["videos"])
    return [
        {"step": step, "done": int(steps[step]), "of": videos if step == "transcripts" else total}
        for step in (
            "metadata",
            "previews",
            "image_vectors",
            "descriptions",
            "caption_vectors",
            "transcripts",
            "faces",
        )
    ]
