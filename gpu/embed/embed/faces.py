"""Faces: where they are in a picture, and a vector that tells one person from another.

InsightFace's "buffalo_l" models, run with ONNX Runtime: SCRFD finds the faces and five points
on each (eyes, nose, corners of the mouth), ArcFace turns every face - turned upright and cut to
112 by 112 pixels by those points - into 512 numbers. Two faces of the same person lie close
together, whatever the light, the age or the angle; different people lie far apart.

The models come as one archive from the InsightFace releases and are fetched on first start into
the models volume. The pretrained models are licensed for non-commercial use only, which a
family's photo library is.

The decoding follows InsightFace's own (insightface/model_zoo/scrfd.py and arcface_onnx.py); the
package itself is not used, because it has to be compiled and brings a dozen libraries along.
"""

import io
import logging
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

#: Where ArcFace expects the five points on its 112 by 112 face.
ARCFACE_POINTS = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)

#: The side the detector looks at: every picture is shrunk to fit and padded.
DETECT_SIZE = 640
STRIDES = (8, 16, 32)
ANCHORS_PER_CELL = 2
#: Overlapping boxes of one face: the weaker ones go.
NMS_OVERLAP = 0.4

DETECTOR_FILE = "det_10g.onnx"
RECOGNIZER_FILE = "w600k_r50.onnx"


class UnusableImageError(Exception):
    """What was sent is no picture."""


@dataclass(frozen=True, slots=True)
class Face:
    #: Left, top, right, bottom, in pixels of the picture as it was sent (upright).
    box: tuple[float, float, float, float]
    score: float
    #: Eyes, nose, corners of the mouth.
    landmarks: list[tuple[float, float]]
    #: 512 numbers of length 1.
    embedding: list[float]


@dataclass(frozen=True, slots=True)
class Found:
    width: int
    height: int
    faces: list[Face]


class FaceFinder(Protocol):
    def find(self, pictures: list[bytes]) -> list[Found]: ...


def decode(picture: bytes) -> np.ndarray[Any, Any]:
    """RGB pixels, turned the way the camera meant them."""
    try:
        with Image.open(io.BytesIO(picture)) as image:
            upright = ImageOps.exif_transpose(image).convert("RGB")
            return np.asarray(upright)
    except Exception as error:
        raise UnusableImageError(f"Not a picture: {error}") from error


def anchor_centers(stride: int) -> np.ndarray[Any, Any]:
    """The middle of every cell of the detector's grid at this stride, each twice."""
    cells = DETECT_SIZE // stride
    rows, columns = np.mgrid[:cells, :cells]
    grid = np.stack([columns, rows], axis=-1).astype(np.float32)
    centers = (grid * stride).reshape(-1, 2)
    return np.repeat(centers, ANCHORS_PER_CELL, axis=0)


def non_maximum(boxes: np.ndarray[Any, Any], scores: np.ndarray[Any, Any]) -> list[int]:
    """The strongest box of every cluster of overlapping ones."""
    order = scores.argsort()[::-1]
    keep: list[int] = []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    while order.size > 0:
        best = int(order[0])
        keep.append(best)
        rest = order[1:]
        width = np.maximum(0.0, np.minimum(x2[best], x2[rest]) - np.maximum(x1[best], x1[rest]) + 1)
        height = np.maximum(
            0.0, np.minimum(y2[best], y2[rest]) - np.maximum(y1[best], y1[rest]) + 1
        )
        overlap = width * height / (areas[best] + areas[rest] - width * height)
        order = rest[overlap <= NMS_OVERLAP]
    return keep


def decode_detections(
    outputs: list[np.ndarray[Any, Any]], threshold: float
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """SCRFD's nine outputs - scores, box distances and points for three strides - as boxes,
    scores and points on the 640 by 640 canvas."""
    boxes, scores, points = [], [], []
    for index, stride in enumerate(STRIDES):
        score = outputs[index].reshape(-1)
        distance = outputs[index + len(STRIDES)].reshape(-1, 4) * stride
        offsets = outputs[index + 2 * len(STRIDES)].reshape(-1, 10) * stride
        centers = anchor_centers(stride)
        keep = score >= threshold
        if not keep.any():
            continue
        center = centers[keep]
        box = np.concatenate(
            [center - distance[keep][:, :2], center + distance[keep][:, 2:]], axis=1
        )
        point = offsets[keep].reshape(-1, 5, 2) + center[:, None, :]
        boxes.append(box)
        scores.append(score[keep])
        points.append(point)
    if not boxes:
        return np.zeros((0, 4)), np.zeros(0), np.zeros((0, 5, 2))
    return np.concatenate(boxes), np.concatenate(scores), np.concatenate(points)


def aligned(pixels: np.ndarray[Any, Any], landmarks: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """The face turned upright and cut to 112 by 112, its points where ArcFace wants them."""
    matrix, _ = cv2.estimateAffinePartial2D(
        landmarks.astype(np.float32), ARCFACE_POINTS, method=cv2.LMEDS
    )
    if matrix is None:
        raise UnusableImageError("The points of this face do not make a face.")
    return cv2.warpAffine(pixels, matrix, (112, 112), borderValue=0.0)


class InsightFaces:
    """buffalo_l with ONNX Runtime, on the card when there is one."""

    def __init__(
        self, directory: Path, device: str, threshold: float, memory_mb: int = 1024
    ) -> None:
        import onnxruntime as ort

        providers: list[Any] = ["CPUExecutionProvider"]
        if device.startswith("cuda"):
            # The CUDA and cuDNN libraries come as Python packages with torch; ONNX Runtime
            # finds them once they are loaded.
            preload = getattr(ort, "preload_dlls", None)
            if preload is not None:
                preload()
            # The card is shared with the describing model, which takes its share once at start
            # and fails when it is not there. Left alone, ONNX Runtime grows its memory in powers
            # of two and tries every convolution algorithm with large scratch buffers; here it
            # takes what it needs, up to a limit, and picks algorithms by rule.
            cuda = {
                "gpu_mem_limit": memory_mb * 1024 * 1024,
                "arena_extend_strategy": "kSameAsRequested",
                "cudnn_conv_algo_search": "HEURISTIC",
                "cudnn_conv_use_max_workspace": "0",
            }
            providers = [("CUDAExecutionProvider", cuda), "CPUExecutionProvider"]
        self._detector = ort.InferenceSession(str(directory / DETECTOR_FILE), providers=providers)
        self._recognizer = ort.InferenceSession(
            str(directory / RECOGNIZER_FILE), providers=providers
        )
        self._threshold = threshold
        logger.info("Faces on %s", self._detector.get_providers()[0])

    def find(self, pictures: list[bytes]) -> list[Found]:
        return [self._find_one(decode(picture)) for picture in pictures]

    def _find_one(self, pixels: np.ndarray[Any, Any]) -> Found:
        height, width = pixels.shape[:2]
        scale = min(DETECT_SIZE / width, DETECT_SIZE / height)
        shrunk = cv2.resize(pixels, (max(1, int(width * scale)), max(1, int(height * scale))))
        canvas = np.zeros((DETECT_SIZE, DETECT_SIZE, 3), dtype=np.uint8)
        canvas[: shrunk.shape[0], : shrunk.shape[1]] = shrunk
        blob = ((canvas.astype(np.float32) - 127.5) / 128.0).transpose(2, 0, 1)[None]
        outputs = self._detector.run(None, {self._detector.get_inputs()[0].name: blob})

        boxes, scores, points = decode_detections(list(outputs), self._threshold)
        if len(scores) == 0:
            return Found(width=width, height=height, faces=[])
        keep = non_maximum(boxes, scores)
        boxes, scores, points = boxes[keep] / scale, scores[keep], points[keep] / scale

        # One face per run: the recognizer is exported for a batch of one, and a card may
        # refuse more.
        name = self._recognizer.get_inputs()[0].name
        rows = []
        for landmarks in points:
            face = aligned(pixels, landmarks).astype(np.float32)
            blob = ((face - 127.5) / 127.5).transpose(2, 0, 1)[None]
            rows.append(self._recognizer.run(None, {name: blob})[0][0])
        vectors = np.stack(rows)
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

        return Found(
            width=width,
            height=height,
            faces=[
                Face(
                    box=(
                        float(max(0.0, box[0])),
                        float(max(0.0, box[1])),
                        float(min(width, box[2])),
                        float(min(height, box[3])),
                    ),
                    score=float(score),
                    landmarks=[(float(x), float(y)) for x, y in landmark],
                    embedding=[float(value) for value in vector],
                )
                for box, score, landmark, vector in zip(boxes, scores, points, vectors, strict=True)
            ],
        )


def fetch_models(url: str, directory: Path) -> Path:
    """Download and unpack the models once; afterwards they are simply there."""
    if (directory / DETECTOR_FILE).exists() and (directory / RECOGNIZER_FILE).exists():
        return directory
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "models.zip.part"
    logger.info("Fetching face models from %s", url)
    urllib.request.urlretrieve(url, archive)  # noqa: S310 - the address is our own setting
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if Path(name).name in (DETECTOR_FILE, RECOGNIZER_FILE):
                (directory / Path(name).name).write_bytes(bundle.read(name))
    archive.unlink()
    return directory


def load_insightface(
    url: str, directory: Path, device: str, threshold: float, memory_mb: int = 1024
) -> InsightFaces:
    return InsightFaces(fetch_models(url, directory), device, threshold, memory_mb)
