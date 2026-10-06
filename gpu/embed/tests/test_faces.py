"""Faces, tested without the models: the decoding, the alignment, and the endpoint."""

import base64
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from embed.config import Settings
from embed.faces import (
    ARCFACE_POINTS,
    DETECT_SIZE,
    Face,
    Found,
    UnusableImageError,
    aligned,
    anchor_centers,
    decode,
    decode_detections,
    non_maximum,
)
from embed.main import create_app


def test_every_cell_has_two_anchors_at_its_corner() -> None:
    centers = anchor_centers(32)

    cells = DETECT_SIZE // 32
    assert centers.shape == (cells * cells * 2, 2)
    assert centers[:4].tolist() == [[0, 0], [0, 0], [32, 0], [32, 0]]
    # Row by row: after a full row, the next one starts one stride lower.
    assert centers[cells * 2].tolist() == [0, 32]


def test_overlapping_boxes_leave_the_strongest() -> None:
    boxes = np.array([[10, 10, 50, 50], [12, 12, 52, 52], [100, 100, 140, 140]], dtype=float)
    scores = np.array([0.8, 0.9, 0.7])

    assert non_maximum(boxes, scores) == [1, 2]


def test_detections_come_back_as_boxes_and_points() -> None:
    outputs = []
    for stride in (8, 16, 32):
        anchors = (DETECT_SIZE // stride) ** 2 * 2
        outputs.append(np.zeros((anchors, 1), dtype=np.float32))
    for stride in (8, 16, 32):
        anchors = (DETECT_SIZE // stride) ** 2 * 2
        outputs.append(np.ones((anchors, 4), dtype=np.float32))
    for stride in (8, 16, 32):
        anchors = (DETECT_SIZE // stride) ** 2 * 2
        outputs.append(np.zeros((anchors, 10), dtype=np.float32))
    # One confident anchor at stride 32: the third cell of the first row.
    outputs[2][4] = 0.9

    boxes, scores, points = decode_detections(outputs, threshold=0.5)

    assert scores.tolist() == pytest.approx([0.9])
    # A distance of 1 in every direction, times the stride, around the anchor at (64, 0).
    assert boxes.tolist() == [[32.0, -32.0, 96.0, 32.0]]
    assert points.shape == (1, 5, 2)
    assert points[0][0].tolist() == [64.0, 0.0]


def test_a_face_already_in_place_is_cut_out_unchanged() -> None:
    pixels = np.zeros((112, 112, 3), dtype=np.uint8)
    pixels[40:60, 30:80] = 200

    face = aligned(pixels, ARCFACE_POINTS.copy())

    assert face.shape == (112, 112, 3)
    assert abs(int(face[50, 50, 0]) - 200) < 5
    assert int(face[100, 10, 0]) == 0


def test_what_is_no_picture_is_refused() -> None:
    with pytest.raises(UnusableImageError):
        decode(b"not a picture")


class FakeFinder:
    def __init__(self) -> None:
        self.seen: list[int] = []

    def find(self, pictures: list[bytes]) -> list[Found]:
        self.seen.append(len(pictures))
        return [
            Found(
                width=640,
                height=480,
                faces=[
                    Face(
                        box=(10.0, 20.0, 110.0, 140.0),
                        score=0.9,
                        landmarks=[(40.0, 60.0)] * 5,
                        embedding=[1.0] + [0.0] * 511,
                    )
                ],
            )
            for _ in pictures
        ]


def a_picture() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (120, 80, 60)).save(buffer, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


@pytest.fixture
def finder() -> FakeFinder:
    return FakeFinder()


@pytest.fixture
def client(finder: FakeFinder) -> TestClient:
    settings = Settings(lazy=True, face_model_name="buffalo_l", api_key="secret")
    return TestClient(create_app(settings, encoders={}, face_finder=finder))


def test_faces_come_with_box_points_and_vector(client: TestClient, finder: FakeFinder) -> None:
    response = client.post(
        "/v1/faces",
        json={"model": "buffalo_l", "input": [a_picture(), a_picture()]},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["index"] for item in body["data"]] == [0, 1]
    (face,) = body["data"][0]["faces"]
    assert face["box"] == [10.0, 20.0, 110.0, 140.0]
    assert len(face["embedding"]) == 512
    assert body["data"][0]["width"] == 640
    assert finder.seen == [2]


def test_faces_need_the_key_and_a_known_model_and_pictures(client: TestClient) -> None:
    headers = {"Authorization": "Bearer secret"}

    assert client.post("/v1/faces", json={"model": "buffalo_l", "input": []}).status_code == 401
    unknown = client.post("/v1/faces", json={"model": "other", "input": []}, headers=headers)
    assert unknown.status_code == 404
    text = client.post(
        "/v1/faces", json={"model": "buffalo_l", "input": ["ein Hund"]}, headers=headers
    )
    assert text.status_code == 400


def test_the_face_model_is_listed(client: TestClient) -> None:
    models = client.get("/v1/models", headers={"Authorization": "Bearer secret"}).json()

    assert "buffalo_l" in [card["id"] for card in models["data"]]
