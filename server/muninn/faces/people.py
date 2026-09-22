"""Who a face is: assigning it to a person, suggesting one, or grouping it with its likes.

Every new face asks its nearest faces that have a person already:

- very close (AUTO_DISTANCE): it is that person, without asking anybody,
- fairly close (SUGGEST_DISTANCE): "Ist das Lena?" - unless somebody already said no,
- otherwise it has no person, and joins the group of the unnamed faces nearest to it. Two
  groups that a face connects become one.

Distances are cosine distances of ArcFace vectors (0 the same, 1 unrelated). Measured on the
library: the same person in different photos lay at 0.19 to 0.40, different people at 0.7 and
beyond. The automatic mark went from 0.45 to 0.50 after the first suggestions, and back to 0.45
(similarity 55 %) once wrong ones showed up at 0.50.

Only a face somebody confirmed vouches for an automatic assignment. Before, the nearest face
with a person decided, whoever had assigned it: one mistake handed the name on to the next
look-alike, and a woman beside Boris in two selfies became Boris in photos ten years older.
Suggestions still come from every named face, since somebody answers them.

Nobody is twice in one photo: a person who already has another face in the picture is not
given to a second one. Videos are left out of this rule, their frames show the same people
again and again.

A face somebody assigned by hand is never touched again by any of this. A person is only made
when somebody names a group; afterwards the unnamed faces are looked at again, since the new
name may be theirs.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from muninn.models.face import Face, FaceRejection, Person
from muninn.models.user import User
from muninn.search import service as search_service

AUTO_DISTANCE = 0.45
SUGGEST_DISTANCE = 0.62
#: How close unnamed faces must be to form a group: a little stricter than a suggestion, since
#: nobody looks at each pair.
GROUP_DISTANCE = 0.5

#: Grouping changes shared numbers; two workers doing it at once would split groups.
_LOCK = "muninn:faces:sort"


async def _lock(session: AsyncSession) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": _LOCK})


async def _rejected(session: AsyncSession, face_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        await session.scalars(
            select(FaceRejection.person_id).where(FaceRejection.face_id == face_id)
        )
    )


async def _in_the_same_photo(session: AsyncSession, face: Face) -> set[uuid.UUID]:
    """The persons other faces of this photo already have; nothing for a video."""
    if face.second is not None:
        return set()
    return {
        person_id
        for person_id in await session.scalars(
            select(Face.person_id).where(
                Face.media_id == face.media_id, Face.id != face.id, Face.person_id.is_not(None)
            )
        )
        if person_id is not None
    }


async def _assign_automatically(session: AsyncSession, face: Face) -> bool:
    """Give the face its person or a suggestion. Returns whether it got a person."""
    ruled_out = await _rejected(session, face.id) | await _in_the_same_photo(session, face)
    candidates = [
        neighbor
        for neighbor in await search_service.face_neighbors(
            session, face.id, named=True, max_distance=SUGGEST_DISTANCE
        )
        if neighbor.person_id not in ruled_out
    ]
    best = candidates[0] if candidates else None
    sure = next(
        (
            neighbor
            for neighbor in await search_service.face_neighbors(
                session, face.id, named=True, confirmed=True, max_distance=AUTO_DISTANCE
            )
            if neighbor.person_id not in ruled_out
        ),
        None,
    )
    if sure is not None:
        face.person_id = sure.person_id
        face.assigned_by = "auto"
        face.suggested_person_id = None
        face.suggested_distance = None
        face.cluster = None
        return True
    face.person_id = None
    face.assigned_by = None
    face.suggested_person_id = best.person_id if best else None
    face.suggested_distance = best.distance if best else None
    return False


async def _group(session: AsyncSession, face: Face) -> None:
    """Put an unnamed face into the group of its unnamed neighbours, joining groups it links."""
    neighbors = await search_service.face_neighbors(
        session, face.id, named=False, max_distance=GROUP_DISTANCE
    )
    if not neighbors:
        return
    clusters = {neighbor.cluster for neighbor in neighbors if neighbor.cluster is not None}
    if face.cluster is not None:
        clusters.add(face.cluster)
    if clusters:
        target = min(clusters)
        others = clusters - {target}
        if others:
            await session.execute(
                update(Face).where(Face.cluster.in_(others)).values(cluster=target)
            )
    else:
        target = int(await session.scalar(text("SELECT nextval('face_clusters')")) or 0)
    face.cluster = target
    loose = [neighbor.face_id for neighbor in neighbors if neighbor.cluster is None]
    if loose:
        await session.execute(update(Face).where(Face.id.in_(loose)).values(cluster=target))


async def sort_faces(session: AsyncSession, face_ids: Sequence[uuid.UUID]) -> None:
    """New faces: a person if one is close enough, else a suggestion and a group."""
    await _lock(session)
    for face_id in face_ids:
        face = await session.get(Face, face_id)
        if face is None or face.assigned_by == "user":
            continue
        if not await _assign_automatically(session, face):
            await session.flush()
            await _group(session, face)
        await session.flush()
    await session.commit()


async def reassess(session: AsyncSession, *, batch: int = 500) -> int:
    """After a name was given or taken: every face nobody assigned by hand asks again.

    Returns how many changed their person or suggestion.
    """
    changed = 0
    last: uuid.UUID | None = None
    while True:
        query = (
            select(Face)
            .where((Face.assigned_by.is_(None)) | (Face.assigned_by == "auto"))
            .order_by(Face.id)
            .limit(batch)
        )
        if last is not None:
            query = query.where(Face.id > last)
        faces = list(await session.scalars(query))
        if not faces:
            break
        await _lock(session)
        for face in faces:
            before = (face.person_id, face.suggested_person_id)
            had_person = face.person_id is not None
            got_person = await _assign_automatically(session, face)
            if had_person and not got_person:
                await session.flush()
                await _group(session, face)
            if (face.person_id, face.suggested_person_id) != before:
                changed += 1
        await session.commit()
        last = faces[-1].id
    return changed


# --- what people decide -----------------------------------------------------------------------


class PersonError(Exception):
    """A name that cannot be given, or a person or face that is not there."""


def _clean(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > 80:
        raise PersonError("A name has 1 to 80 characters.")
    return cleaned


async def person_named(session: AsyncSession, name: str, user: User) -> Person:
    """The person with this name - the same regardless of case - or a new one."""
    cleaned = _clean(name)
    person = await session.scalar(select(Person).where(func.lower(Person.name) == cleaned.lower()))
    if person is None:
        person = Person(id=uuid.uuid4(), name=cleaned, created_by=user.id)
        session.add(person)
        await session.flush()
    return person


async def name_group(session: AsyncSession, cluster: int, name: str, user: User) -> Person:
    """Everybody in this group is that person now. An existing name joins them to it."""
    person = await person_named(session, name, user)
    result = await session.execute(
        update(Face)
        .where(Face.cluster == cluster, Face.person_id.is_(None))
        .values(
            person_id=person.id,
            assigned_by="user",
            suggested_person_id=None,
            suggested_distance=None,
            cluster=None,
        )
    )
    if not getattr(result, "rowcount", 0):
        raise PersonError("This group has no faces left.")
    await session.commit()
    return person


async def assign(session: AsyncSession, face_id: uuid.UUID, person: Person) -> None:
    """Somebody said who this face is: a suggestion confirmed, or a face named by hand."""
    face = await session.get(Face, face_id)
    if face is None:
        raise PersonError("No such face.")
    face.person_id = person.id
    face.assigned_by = "user"
    face.suggested_person_id = None
    face.suggested_distance = None
    face.cluster = None
    await session.execute(
        delete(FaceRejection).where(
            FaceRejection.face_id == face_id, FaceRejection.person_id == person.id
        )
    )
    await session.commit()


async def reject(session: AsyncSession, face_id: uuid.UUID) -> None:
    """Not this person: the suggestion goes, or the face leaves the person it had. It is not
    given to them again, and joins the unnamed faces like it."""
    face = await session.get(Face, face_id)
    if face is None:
        raise PersonError("No such face.")
    wrong = face.person_id or face.suggested_person_id
    if wrong is not None:
        session.add(FaceRejection(face_id=face_id, person_id=wrong))
        await session.flush()
    face.person_id = None
    face.assigned_by = None
    face.suggested_person_id = None
    face.suggested_distance = None
    await sort_faces(session, [face_id])


async def merge(session: AsyncSession, source: Person, target: Person) -> None:
    """Two persons are one: every face of the first goes to the second, and the first is gone."""
    if source.id == target.id:
        return
    await session.execute(
        update(Face).where(Face.person_id == source.id).values(person_id=target.id)
    )
    await session.execute(
        update(Face)
        .where(Face.suggested_person_id == source.id)
        .values(suggested_person_id=target.id)
    )
    await session.execute(delete(Person).where(Person.id == source.id))
    await session.commit()


async def rename(session: AsyncSession, person: Person, name: str) -> Person:
    cleaned = _clean(name)
    taken = await session.scalar(
        select(Person.id).where(func.lower(Person.name) == cleaned.lower(), Person.id != person.id)
    )
    if taken is not None:
        raise PersonError("Somebody else has this name; merge the two instead.")
    person.name = cleaned
    await session.commit()
    return person


async def hide(session: AsyncSession, person: Person, hidden: bool) -> Person:
    """A stranger in the background: kept, so the faces are not asked about again, but not
    shown."""
    person.hidden = hidden
    await session.commit()
    return person


@dataclass(frozen=True, slots=True)
class Counts:
    faces: int
    persons: int
    groups: int
    suggestions: int


async def counts(session: AsyncSession) -> Counts:
    return Counts(
        faces=int(await session.scalar(select(func.count()).select_from(Face)) or 0),
        persons=int(await session.scalar(select(func.count()).select_from(Person)) or 0),
        groups=int(
            await session.scalar(
                select(func.count(func.distinct(Face.cluster))).where(
                    Face.cluster.is_not(None), Face.person_id.is_(None)
                )
            )
            or 0
        ),
        suggestions=int(
            await session.scalar(
                select(func.count())
                .select_from(Face)
                .where(Face.suggested_person_id.is_not(None), Face.person_id.is_(None))
            )
            or 0
        ),
    )


# --- persons in a search ----------------------------------------------------------------------

_NAME_WORDS = 3


@dataclass(frozen=True, slots=True)
class PersonsInQuery:
    text: str
    #: As typed, for the chips.
    names: tuple[str, ...]
    person_ids: tuple[uuid.UUID, ...]


async def persons_in(session: AsyncSession, words: str) -> PersonsInQuery:
    """Take the names of persons out of a search: "Oma Lena Strand" looks for the beach among
    the photos both of them are in. Hidden persons are nobody to search for."""
    import re

    from muninn.settings import service as settings_service

    if not (await settings_service.get_settings(session)).faces_enabled:
        return PersonsInQuery(text=words, names=(), person_ids=())
    matches = list(re.finditer(r"[^\W\d_](?:[\w'.-]*\w)?", words))
    if not matches:
        return PersonsInQuery(text=words, names=(), person_ids=())
    known = {
        person.name.lower(): person
        for person in await session.scalars(select(Person).where(Person.hidden.is_(False)))
    }
    if not known:
        return PersonsInQuery(text=words, names=(), person_ids=())

    taken: list[tuple[int, int, Person]] = []
    index = 0
    while index < len(matches):
        for size in range(min(_NAME_WORDS, len(matches) - index), 0, -1):
            phrase = " ".join(match.group() for match in matches[index : index + size]).lower()
            if phrase in known:
                taken.append((index, index + size, known[phrase]))
                index += size
                break
        else:
            index += 1
    if not taken:
        return PersonsInQuery(text=words, names=(), person_ids=())

    rest, position, names = "", 0, []
    for start, end, _ in taken:
        before = words[position : matches[start].start()]
        rest += re.sub(r"\b(?:und|mit|&)\s*$", "", before, flags=re.IGNORECASE)
        names.append(words[matches[start].start() : matches[end - 1].end()])
        position = matches[end - 1].end()
    rest += words[position:]
    ids = tuple(dict.fromkeys(person.id for _, _, person in taken))
    return PersonsInQuery(text=" ".join(rest.split()), names=tuple(names), person_ids=ids)
