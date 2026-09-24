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

Not every named face vouches for an automatic assignment. Before, the nearest face with a
person decided, whoever had assigned it: one mistake handed the name on to the next look-alike,
and a woman beside Boris in two selfies became Boris in photos ten years older. Since then only
a face somebody confirmed could vouch - which meant Muninn could never build on its own correct
work, and everything it was less than certain about piled up as a suggestion.

A face Muninn assigned itself vouches too now, when it lay within VOUCH_DISTANCE of one that
already did and is a good enough picture to speak from. Every link in such a chain is much
shorter than the step that caused the drift. Suggestions still come from every named face, since
somebody answers them.

Nobody is twice in one photo: a person who already has another face in the picture is not
given to a second one. Videos are left out of that rule, their frames show the same people
again and again.

Every medium is tidied afterwards in any case. A video repeats its people frame after frame,
and a photograph repeats them too where it is a collage, a picture of a picture or a mirror -
and what the medium has to say is who is in it, not how often a face of them was found. So
``collapse_duplicates`` leaves every person one face, the one somebody assigned or the
clearest look; a guess about somebody the medium has for certain goes, and of the guesses
left one per person keeps its question.

A face somebody assigned by hand is never touched again by any of this. A person is only made
when somebody names a group; afterwards the unnamed faces are looked at again, since the new
name may be theirs.
"""

import math
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
#: How close to a group's middle a face must lie to join that group.
JOIN_DISTANCE = 0.45
#: How close two groups' middles must lie for the two to be one group. Stricter than joining on
#: purpose: a wrong merge costs hundreds of faces their group, a group too many costs one name.
MERGE_DISTANCE = 0.35
#: How close a face must lie to one of a person's middles to be given their name. A middle is
#: an average of several faces and so a steadier thing to measure against than any one of them.
PROTOTYPE_DISTANCE = 0.40
#: At most this many middles for one person: one for each way they looked over the years.
PROTOTYPES_MAX = 5
#: How far a face may lie from the one just answered and still be offered along with it.
#:
#: As far as a suggestion reaches, and for the same reason: a face Muninn is willing to ask
#: about is one it can offer here. Nothing is taken without being seen - the faces are on the
#: screen and the count says how many the line takes - so the line is somebody's to draw, and
#: drawing it needs something to draw through. At 0.40 there was often only one face below it,
#: and the slider could not be moved far enough to find the others.
ALIKE_DISTANCE = SUGGEST_DISTANCE

#: A person earns another middle every this many faces that vouch for them.
PROTOTYPE_FACES = 8
#: At most this many of a person's faces are gathered into middles. Beyond it the middles do not
#: get better, and the gathering is plain Python: a person with thousands of faces would hold up
#: every other person waiting behind them.
PROTOTYPE_SAMPLE = 600

#: How close an automatic assignment must lie to a face that already vouches, to vouch itself.
#: Far stricter than AUTO_DISTANCE on purpose: what the confirmed-only rule was written against
#: is a chain of guesses each adding a little drift, and a short link adds almost none.
VOUCH_DISTANCE = 0.30

#: A face smaller or less sure than this is kept, is searched, and can be given a name by hand.
#: It just neither founds a group nor vouches for anybody: below this its vector says more about
#: focus and light than about who it is, and faces like it are what tie the groups of different
#: people into one.
SURE_PIXELS = 80
SURE_SCORE = 0.75

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


def _dot(first: list[float], second: list[float]) -> float:
    return sum(a * b for a, b in zip(first, second, strict=True))


def _pointing(vector: list[float]) -> list[float]:
    """The same direction, length one. ArcFace vectors are only ever about direction."""
    length = math.sqrt(sum(part * part for part in vector))
    return [part / length for part in vector] if length else list(vector)


def _mean(points: list[list[float]]) -> list[float]:
    return _pointing([sum(column) / len(points) for column in zip(*points, strict=True)])


def _nearest(point: list[float], centers: list[list[float]]) -> int:
    return max(range(len(centers)), key=lambda index: _dot(point, centers[index]))


def middles(
    vectors: list[list[float]], *, most: int = PROTOTYPES_MAX, rounds: int = 8
) -> list[tuple[list[float], int]]:
    """Gather a person's vectors into a few middles, each with the number of faces behind it.

    Plain k-means on the unit sphere, which is where these vectors live. How many middles
    follows how many faces there are: one to start with, and another every PROTOTYPE_FACES, up
    to `most`. A person of twenty-six years is several people to look at, and one average of all
    of them would be none of them.
    """
    points = [_pointing(vector) for vector in vectors]
    if not points:
        return []
    wanted = min(most, max(1, len(points) // PROTOTYPE_FACES))
    if len(points) > PROTOTYPE_SAMPLE:
        # Evenly across the faces as they were ordered, which is by id and so by nothing in
        # particular: a part of them says as much about the shape of the whole as all of them.
        apart = len(points) / PROTOTYPE_SAMPLE
        points = [points[int(index * apart)] for index in range(PROTOTYPE_SAMPLE)]

    # Start from the face most like all the others, then from the one least like what is chosen:
    # the same faces always give the same middles, which keeps a reassessment from wandering.
    average = _mean(points)
    centers = [max(points, key=lambda point: _dot(point, average))]
    while len(centers) < wanted:
        centers.append(
            max(points, key=lambda point: min(1 - _dot(point, chosen) for chosen in centers))
        )

    for _ in range(rounds):
        buckets: list[list[list[float]]] = [[] for _ in centers]
        for point in points:
            buckets[_nearest(point, centers)].append(point)
        moved = [
            _mean(bucket) if bucket else centers[index] for index, bucket in enumerate(buckets)
        ]
        if moved == centers:
            break
        centers = moved

    buckets = [[] for _ in centers]
    for point in points:
        buckets[_nearest(point, centers)].append(point)
    return [
        (center, len(bucket)) for center, bucket in zip(centers, buckets, strict=True) if bucket
    ]


async def rebuild_prototypes(session: AsyncSession) -> int:
    """What stands for each person, made again from the faces that vouch for them.

    Returns how many middles there are altogether.
    """
    made = 0
    for person_id in list(await session.scalars(select(Person.id))):
        found = await search_service.vouching_vectors(session, person_id)
        centers = middles(found.vectors) if found is not None else []
        await search_service.store_prototypes(
            session,
            person_id,
            model=found.model if found is not None else "",
            centers=centers,
        )
        made += len(centers)
    await session.commit()
    return made


def _take(face: Face, person_id: uuid.UUID, *, trusted: bool) -> bool:
    """This face is that person now, said by Muninn itself."""
    face.person_id = person_id
    face.assigned_by = "auto"
    face.trusted = trusted
    face.suggested_person_id = None
    face.suggested_distance = None
    face.cluster = None
    return True


def _sure_enough(face: Face) -> bool:
    """Whether this face is a good enough picture to group by or to vouch from."""
    return face.pixels >= SURE_PIXELS and face.score >= SURE_SCORE


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
                session,
                face.id,
                named=True,
                confirmed=True,
                max_distance=AUTO_DISTANCE,
                min_pixels=SURE_PIXELS,
                min_score=SURE_SCORE,
            )
            if neighbor.person_id not in ruled_out
        ),
        None,
    )
    if sure is not None and sure.person_id is not None:
        # Close enough, and clear enough, to speak for this person itself from now on.
        return _take(
            face,
            sure.person_id,
            trusted=sure.distance <= VOUCH_DISTANCE and _sure_enough(face),
        )

    # No single face of anybody was close enough. Their middles carry further: what a face of
    # somebody at two has in common is with their other faces at two, not with one photo of them.
    resembles = next(
        (
            neighbor
            for neighbor in await search_service.prototype_neighbors(
                session, face.id, max_distance=PROTOTYPE_DISTANCE
            )
            if neighbor.person_id not in ruled_out
        ),
        None,
    )
    if resembles is not None:
        # A middle already speaks for several faces; what it names does not get to speak again.
        return _take(face, resembles.person_id, trusted=False)

    face.person_id = None
    face.assigned_by = None
    face.trusted = False
    face.suggested_person_id = best.person_id if best else None
    face.suggested_distance = best.distance if best else None
    return False


async def _group(session: AsyncSession, face: Face) -> None:
    """Put an unnamed face into the group it belongs to, and join the groups that are one.

    Which group it joins is decided by the group's middle - the average of its faces - not by
    whichever single face lies nearest. Before, every group a face touched was merged into one,
    so a single face between two of them tied them together for good, and a chain of such faces
    tied hundreds of different people into one group nobody could name.

    A face that is too small or too unsure stays out of the groups altogether. It would bring
    nothing to name and a great deal to confuse.
    """
    if not _sure_enough(face):
        face.cluster = None
        return
    neighbors = await search_service.face_neighbors(
        session,
        face.id,
        named=False,
        max_distance=GROUP_DISTANCE,
        min_pixels=SURE_PIXELS,
        min_score=SURE_SCORE,
    )
    if not neighbors:
        return
    clusters = {neighbor.cluster for neighbor in neighbors if neighbor.cluster is not None}
    middles = await search_service.distance_to_clusters(session, face.id, sorted(clusters))
    near = {cluster: gap for cluster, gap in middles.items() if gap <= JOIN_DISTANCE}
    if near:
        target = min(near, key=lambda cluster: near[cluster])
    elif face.cluster is not None:
        target = face.cluster
    else:
        target = int(await session.scalar(text("SELECT nextval('face_clusters')")) or 0)
    face.cluster = target
    await session.flush()

    # Two groups become one only when their middles are close, never because one face happens
    # to lie between them.
    for other in sorted(clusters - {target}):
        if await search_service.gap_between_clusters(session, target, other) <= MERGE_DISTANCE:
            await session.execute(update(Face).where(Face.cluster == other).values(cluster=target))

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


@dataclass(frozen=True, slots=True)
class Grouping:
    """What building the groups again left behind."""

    groups: int
    faces: int
    largest: int
    ungrouped: int


async def regroup(session: AsyncSession, *, batch: int = 500) -> Grouping:
    """Build the groups of every face nobody named again, under the rule as it stands now.

    A face is only ever put into a group when it is new, so groups made under an older rule stay
    as they were - including the ones an earlier rule ran together. This throws them all away
    and builds them up again. Faces that have a person are not touched: what somebody decided
    is never undone here.

    Returns how many groups there are, how many faces are in them, and how big the largest is.
    """
    await session.execute(update(Face).where(Face.person_id.is_(None)).values(cluster=None))
    await session.commit()

    last: uuid.UUID | None = None
    while True:
        query = select(Face).where(Face.person_id.is_(None)).order_by(Face.id).limit(batch)
        if last is not None:
            query = query.where(Face.id > last)
        faces = list(await session.scalars(query))
        if not faces:
            break
        await _lock(session)
        for face in faces:
            await _group(session, face)
            await session.flush()
        await session.commit()
        last = faces[-1].id

    sizes = (
        select(Face.cluster, func.count().label("faces"))
        .where(Face.cluster.is_not(None))
        .group_by(Face.cluster)
        .subquery()
    )
    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(sizes.c.faces), 0),
                func.coalesce(func.max(sizes.c.faces), 0),
            ).select_from(sizes)
        )
    ).one()
    ungrouped = int(
        await session.scalar(
            select(func.count())
            .select_from(Face)
            .where(Face.person_id.is_(None), Face.cluster.is_(None))
        )
        or 0
    )
    return Grouping(groups=int(row[0]), faces=int(row[1]), largest=int(row[2]), ungrouped=ungrouped)


def _clearest(face: Face) -> tuple[int, float]:
    """What somebody assigned comes first, then the biggest and surest look."""
    return (0 if face.assigned_by == "user" else 1, -face.pixels * face.score)


def _asks_best(face: Face) -> tuple[float, float]:
    """Which face gets to ask about a person: the closest guess, and the clearest of those."""
    return (face.suggested_distance if face.suggested_distance is not None else 1.0,
            -face.pixels * face.score)  # fmt: skip


async def collapse_duplicates(session: AsyncSession, media_id: uuid.UUID) -> list[uuid.UUID]:
    """One medium's faces, each person once: the extra sightings go.

    A frame every few seconds shows the same people again and again, so one person ends up with
    several faces on one video. Which frame they were seen in matters to nobody looking at the
    medium - nothing shows the second or leads to it - so one face per person stays: what
    somebody assigned by hand, else the clearest look. A face that is only guessed at goes with
    them once that person is on the medium for certain - the question has its answer already.

    And where nobody is certain yet, one face per person asks. Several frames that all resemble
    the same person are one question asked several times, and answering it seven times is work
    nobody should be given.

    Videos only. In a photo two faces are two different people, and the rule in
    ``_in_the_same_photo`` keeps them apart from the start.

    Returns the faces that were removed, so their square pictures can go too.
    """
    faces = list(await session.scalars(select(Face).where(Face.media_id == media_id)))
    kept: dict[uuid.UUID, Face] = {}
    doomed: list[Face] = []
    for face in sorted(faces, key=_clearest):
        if face.person_id is None:
            continue
        if face.person_id in kept:
            doomed.append(face)
        else:
            kept[face.person_id] = face
    doomed.extend(
        face for face in faces if face.person_id is None and face.suggested_person_id in kept
    )

    # The same goes for the questions. Seven frames that all resemble Olivia are seven ways of
    # asking whether Olivia is in this video, and the answer to one is the answer to all of
    # them. The nearest look asks; the rest go with the sightings.
    asked: set[uuid.UUID] = set()
    answered = {face.id for face in doomed}
    for face in sorted(
        (
            face
            for face in faces
            if face.person_id is None
            and face.suggested_person_id is not None
            and face.id not in answered
        ),
        key=_asks_best,
    ):
        about = face.suggested_person_id
        if about is None or about in asked:
            doomed.append(face)
        else:
            asked.add(about)

    if not doomed:
        return []

    removed = [face.id for face in doomed]
    await session.execute(delete(Face).where(Face.id.in_(removed)))
    await session.commit()
    return removed


async def reassess(session: AsyncSession, *, batch: int = 500) -> int:
    """After a name was given or taken: every face nobody assigned by hand asks again.

    Returns how many changed their person or suggestion.
    """
    await rebuild_prototypes(session)
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


async def alike_suggestions(
    session: AsyncSession,
    face_id: uuid.UUID,
    person_id: uuid.UUID,
    *,
    max_distance: float = ALIKE_DISTANCE,
    limit: int = 60,
) -> list[tuple[Face, float]]:
    """The open questions about this person whose faces look like the one just answered.

    Only faces nobody has decided, only about this one person, the most alike first, each with
    how alike it is. Answering a screenful of nearly the same face one click at a time is what
    makes a pile of suggestions hopeless; this is what lets somebody answer them together.
    """
    neighbors = await search_service.face_neighbors(
        session,
        face_id,
        named=False,
        max_distance=max_distance,
        limit=limit,
        suggested_for=person_id,
    )
    found: list[tuple[Face, float]] = []
    for neighbor in neighbors:
        face = await session.get(Face, neighbor.face_id)
        if face is not None and face.suggested_person_id == person_id:
            found.append((face, 1.0 - neighbor.distance))
    return found


async def confirm_many(session: AsyncSession, face_ids: Sequence[uuid.UUID]) -> int:
    """Stand by what Muninn decided for each of these faces. Returns how many were confirmed.

    A face Muninn assigned itself is a conclusion, not evidence: it vouches for nobody when the
    next face is sorted, because one wrong guess would otherwise teach the rest. Confirming it
    makes it evidence - which is why going through a person's automatic faces is worth more
    than answering a hundred questions.

    Each face keeps the person it already has; this says yes to that person, not to another.
    A face that was not Muninn's to give - one somebody already decided, or one with nobody at
    all - is skipped rather than refused: the list may have moved on since it was seen.
    """
    confirmed = 0
    for face_id in face_ids:
        face = await session.get(Face, face_id)
        if face is None or face.assigned_by != "auto" or face.person_id is None:
            continue
        person = await session.get(Person, face.person_id)
        if person is None:
            continue
        await assign(session, face_id, person)
        confirmed += 1
    return confirmed


async def decide_many(
    session: AsyncSession, face_ids: Sequence[uuid.UUID], person: Person, *, confirm: bool
) -> int:
    """The same yes or no for several faces at once. Returns how many were answered.

    Only faces that are still an open question about this person; anything else is skipped
    rather than refused, because the list somebody answered may have moved on since they saw it.
    """
    answered = 0
    for face_id in face_ids:
        face = await session.get(Face, face_id)
        if face is None or face.person_id is not None or face.suggested_person_id != person.id:
            continue
        if confirm:
            await assign(session, face_id, person)
        else:
            await reject(session, face_id)
        answered += 1
    return answered


async def reject(session: AsyncSession, face_id: uuid.UUID) -> None:
    """Not this person: the suggestion goes, or the face leaves the person it had. It is not
    given to them again.

    Only the decision is written here, and it is written at once. Looking for the face's new
    group takes the lock the worker holds while it reassesses faces, and somebody waiting in
    front of a "Nein" should not wait for that: the caller hands the sorting to the worker.
    """
    face = await session.get(Face, face_id)
    if face is None:
        raise PersonError("No such face.")
    wrong = face.person_id or face.suggested_person_id
    if wrong is not None:
        session.add(FaceRejection(face_id=face_id, person_id=wrong))
        await session.flush()
    face.person_id = None
    face.assigned_by = None
    # It vouched for that person while it had them; a "Nein" takes that with it.
    face.trusted = False
    face.suggested_person_id = None
    face.suggested_distance = None
    face.cluster = None
    await session.commit()


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
