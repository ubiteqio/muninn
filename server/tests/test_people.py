"""Who a face is: automatic persons, suggestions, groups, and what people decide."""

import math
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from muninn.faces import people
from muninn.models.face import Face, Person
from muninn.models.user import User
from muninn.search.service import FaceToStore, store_faces
from tests.helpers import create_user
from tests.test_timeline import JULY, a_medium, an_album

pytestmark = pytest.mark.usefixtures("api_client")


def at(similarity: float, towards: int = 1) -> list[float]:
    """A vector with this cosine similarity to the first axis, leaning towards another axis."""
    vector = [0.0] * 8
    vector[0] = similarity
    vector[towards] = math.sqrt(1 - similarity**2)
    return vector


async def faces_in_a_photo(session: AsyncSession, *vectors: list[float]) -> list[uuid.UUID]:
    medium = await a_medium(
        session,
        await an_album(session, f"Fest-{uuid.uuid4().hex[:6]}"),
        taken_at=JULY,
        name="a.jpg",
    )
    ids = await store_faces(
        session,
        medium.id,
        model="buffalo_l",
        faces=[
            FaceToStore(
                box=(0.1 + 0.2 * index, 0.1, 0.25 + 0.2 * index, 0.3),
                score=0.9,
                pixels=100,
                second=None,
                embedding=vector,
            )
            for index, vector in enumerate(vectors)
        ],
    )
    await session.commit()
    await people.sort_faces(session, ids)
    return ids


async def face(session: AsyncSession, face_id: uuid.UUID) -> Face:
    found = await session.get(Face, face_id, populate_existing=True)
    assert found is not None
    return found


async def a_user(session_factory: async_sessionmaker[AsyncSession], session: AsyncSession) -> User:
    await create_user(session_factory, username="anna", display_name="Anna")
    user = await session.scalar(select(User).where(User.username == "anna"))
    assert user is not None
    return user


async def test_alike_faces_form_a_group_and_others_stay_apart(session: AsyncSession) -> None:
    (lena,) = await faces_in_a_photo(session, at(1.0))
    (again,) = await faces_in_a_photo(session, at(0.9))
    (stranger,) = await faces_in_a_photo(session, at(0.0, towards=3))

    first, second, other = [await face(session, id_) for id_ in (lena, again, stranger)]

    assert first.cluster is not None
    assert first.cluster == second.cluster
    assert other.cluster is None


async def test_a_face_joins_two_groups_it_links(session: AsyncSession) -> None:
    (left,) = await faces_in_a_photo(session, at(1.0))
    (left_too,) = await faces_in_a_photo(session, at(0.97, towards=1))
    (right,) = await faces_in_a_photo(session, at(0.0, towards=2))
    (right_too,) = await faces_in_a_photo(session, [0.0, 0.24, 0.97, 0, 0, 0, 0, 0])
    before = {(await face(session, i)).cluster for i in (left, left_too, right, right_too)}
    assert len(before) == 2

    # Close to both: now they are one group.
    (bridge,) = await faces_in_a_photo(session, [0.707, 0.0, 0.707] + [0.0] * 5)

    after = {(await face(session, i)).cluster for i in (left, left_too, right, right_too, bridge)}
    assert len(after) == 1


async def test_a_named_group_takes_new_faces_or_suggests_them(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await a_user(session_factory, session)
    first, second = await faces_in_a_photo(session, at(1.0), at(0.95))
    group = (await face(session, first)).cluster
    assert group is not None

    lena = await people.name_group(session, group, "Lena", anna)
    (sure,) = await faces_in_a_photo(session, at(0.9, towards=4))
    (unsure,) = await faces_in_a_photo(session, at(0.5, towards=5))
    (nobody,) = await faces_in_a_photo(session, at(0.1, towards=6))

    assert (await face(session, second)).person_id == lena.id
    assert ((await face(session, sure)).person_id, (await face(session, sure)).assigned_by) == (
        lena.id,
        "auto",
    )
    unsure_face = await face(session, unsure)
    assert (unsure_face.person_id, unsure_face.suggested_person_id) == (None, lena.id)
    # How alike: the distance to Lena's nearest face, kept for the app to show.
    assert unsure_face.suggested_distance == pytest.approx(0.5, abs=0.03)
    assert (await face(session, nobody)).suggested_person_id is None


async def test_a_no_only_writes_the_decision_and_leaves_the_sorting_to_the_worker(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A "Nein" answers at once. Finding the face's new group takes the lock the worker holds
    while it reassesses, and nobody should wait in front of a dialog for that."""
    anna = await a_user(session_factory, session)
    named = await faces_in_a_photo(session, at(1.0), at(0.96))
    lena = await people.name_group(
        session, (await face(session, named[0])).cluster or 0, "Lena", anna
    )
    (mistaken,) = await faces_in_a_photo(session, at(0.9, towards=3))
    assert (await face(session, mistaken)).person_id == lena.id

    await people.reject(session, mistaken)

    after = await face(session, mistaken)
    assert (after.person_id, after.suggested_person_id, after.cluster) == (None, None, None)

    # What the worker does with it afterwards: a group, and never Lena again.
    await people.sort_faces(session, [mistaken])
    sorted_face = await face(session, mistaken)
    assert (sorted_face.person_id, sorted_face.suggested_person_id) == (None, None)


async def test_the_same_name_in_another_case_is_the_same_person(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await a_user(session_factory, session)
    one = await faces_in_a_photo(session, at(1.0, towards=1), at(0.97, towards=1))
    two = await faces_in_a_photo(session, at(0.0, towards=2), [0.0, 0.0, 0.97, 0.24, 0, 0, 0, 0])
    first = await people.name_group(
        session, (await face(session, one[0])).cluster or 0, "Lena", anna
    )
    second = await people.name_group(
        session, (await face(session, two[0])).cluster or 0, " lena ", anna
    )

    assert first.id == second.id
    assert len(list(await session.scalars(select(Person)))) == 1


async def test_a_no_is_remembered_and_a_hand_assignment_is_kept(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await a_user(session_factory, session)
    named = await faces_in_a_photo(session, at(1.0), at(0.96))
    lena = await people.name_group(
        session, (await face(session, named[0])).cluster or 0, "Lena", anna
    )
    (maybe,) = await faces_in_a_photo(session, at(0.5, towards=3))
    assert (await face(session, maybe)).suggested_person_id == lena.id

    await people.reject(session, maybe)
    assert (await face(session, maybe)).suggested_person_id is None
    await people.reassess(session)
    assert (await face(session, maybe)).suggested_person_id is None

    # Somebody says it is Lena after all, by hand: nothing automatic takes that back.
    await people.assign(session, maybe, lena)
    await people.reassess(session)
    assigned = await face(session, maybe)
    assert (assigned.person_id, assigned.assigned_by) == (lena.id, "user")


async def test_naming_a_group_reaches_the_unnamed_faces_like_it(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await a_user(session_factory, session)
    group = await faces_in_a_photo(session, at(1.0), at(0.98))
    (alone,) = await faces_in_a_photo(session, at(0.45, towards=5))
    assert (await face(session, alone)).cluster is None

    lena = await people.name_group(
        session, (await face(session, group[0])).cluster or 0, "Lena", anna
    )
    assert await people.reassess(session) == 1

    assert (await face(session, alone)).suggested_person_id == lena.id


async def test_two_persons_become_one(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    anna = await a_user(session_factory, session)
    child = await faces_in_a_photo(session, at(1.0, towards=1), at(0.97, towards=1))
    adult = await faces_in_a_photo(session, at(0.0, towards=2), [0.0, 0.0, 0.97, 0.24, 0, 0, 0, 0])
    small = await people.name_group(
        session, (await face(session, child[0])).cluster or 0, "Lena als Kind", anna
    )
    grown = await people.name_group(
        session, (await face(session, adult[0])).cluster or 0, "Lena", anna
    )

    await people.merge(session, small, grown)

    assert {(await face(session, i)).person_id for i in (*child, *adult)} == {grown.id}
    assert await session.get(Person, small.id) is None


async def lena_confirmed(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> Person:
    """Lena, named by hand on two faces along the first axis."""
    anna = await a_user(session_factory, session)
    first, _ = await faces_in_a_photo(session, at(1.0), at(0.97, towards=7))
    group = (await face(session, first)).cluster
    assert group is not None
    return await people.name_group(session, group, "Lena", anna)


async def test_only_a_confirmed_face_vouches_for_an_automatic_one(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    lena = await lena_confirmed(session, session_factory)
    (auto,) = await faces_in_a_photo(session, at(0.8, towards=2))
    assert (await face(session, auto)).assigned_by == "auto"

    # Very close to the automatic face, but only half like the confirmed ones: before, the
    # automatic face handed Lena on. Now it is a question.
    (look_alike,) = await faces_in_a_photo(session, at(0.5, towards=2))

    found = await face(session, look_alike)
    assert (found.person_id, found.suggested_person_id) == (None, lena.id)


async def test_similarity_below_55_percent_is_only_a_question(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    lena = await lena_confirmed(session, session_factory)

    (close,) = await faces_in_a_photo(session, at(0.56, towards=3))
    (not_quite,) = await faces_in_a_photo(session, at(0.52, towards=4))

    assert (await face(session, close)).person_id == lena.id
    assert (await face(session, not_quite)).person_id is None
    assert (await face(session, not_quite)).suggested_person_id == lena.id


async def test_nobody_is_given_twice_in_one_photo(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    lena = await lena_confirmed(session, session_factory)

    both = await faces_in_a_photo(session, at(0.95, towards=3), at(0.9, towards=4))

    found = [await face(session, id_) for id_ in both]
    assert [f.person_id for f in found].count(lena.id) == 1
    # Nor asked about: she is already in the picture.
    assert [f.suggested_person_id for f in found] == [None, None]


async def test_a_persons_faces_filtered_for_checking(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from muninn.faces import listing

    lena = await lena_confirmed(session, session_factory)
    (auto,) = await faces_in_a_photo(session, at(0.9, towards=3))
    confirmed = list(await session.scalars(select(Face.id).where(Face.assigned_by == "user")))

    automatic, _ = await listing.faces_of(
        session, lena.id, offset=0, limit=10, only=listing.FaceFilter.AUTO
    )
    twice, _ = await listing.faces_of(
        session, lena.id, offset=0, limit=10, only=listing.FaceFilter.TWICE
    )

    assert [shown.face.id for shown in automatic] == [auto]
    # The two named by hand share a photo: one of them is somebody else.
    assert sorted(shown.face.id for shown in twice) == sorted(confirmed)


async def test_copies_given_by_muninn_do_not_hide_the_confirmed_face(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    lena = await lena_confirmed(session, session_factory)
    # The same photo, kept eleven times: every copy is Lena, given by Muninn.
    for _ in range(11):
        (copy,) = await faces_in_a_photo(session, at(0.8, towards=2))
        assert (await face(session, copy)).assigned_by == "auto"

    # The twelfth has the copies as its ten nearest; the confirmed face lies further, but
    # close enough to decide.
    (twelfth,) = await faces_in_a_photo(session, at(0.8, towards=2))

    found = await face(session, twelfth)
    assert (found.person_id, found.assigned_by) == (lena.id, "auto")
