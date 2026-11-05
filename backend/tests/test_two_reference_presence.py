"""Unit tests for the integrated two-reference presence detector."""
import cv2
import numpy as np
import pytest

from backend.app.vision.two_reference import (
    PresenceFeatureError,
    calibrate_pair,
    classify_frame,
)


def _scene():
    rng = np.random.default_rng(42)
    height, width = 360, 260
    empty = rng.integers(20, 80, size=(height, width, 3), dtype=np.uint8)
    for y in range(0, height, 40):
        cv2.line(empty, (0, y), (width, y), (90, 85, 70), 2)
    for _ in range(50):
        x = int(rng.integers(0, width))
        y = int(rng.integers(0, height))
        radius = int(rng.integers(1, 4))
        shade = int(rng.integers(70, 150))
        cv2.circle(empty, (x, y), radius, (shade, shade, shade), -1)

    present = empty.copy()
    cv2.rectangle(present, (80, 65), (180, 300), (20, 30, 180), -1)
    cv2.rectangle(present, (90, 80), (170, 120), (0, 210, 240), -1)
    cv2.putText(present, "SHELF ITEM", (90, 160), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 2)
    cv2.putText(present, "REFERENCE", (90, 210), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 2)
    for y in range(235, 285, 12):
        cv2.line(present, (100, y), (160, y), (255, 255, 255), 1)
    return present, empty


def test_two_reference_classifies_present_and_empty():
    present, empty = _scene()
    full_ref, empty_ref, diagnostics = calibrate_pair(present, empty)
    assert diagnostics["separation"] >= 0.07
    assert classify_frame(present, full_ref, empty_ref)[0] == "PRESENT"
    assert classify_frame(empty, full_ref, empty_ref)[0] == "ABSENT"


def test_two_reference_tolerates_small_perspective_and_light_change():
    present, empty = _scene()
    full_ref, empty_ref, _ = calibrate_pair(present, empty)
    height, width = present.shape[:2]
    source = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    target = np.float32([[8, 5], [width - 10, 0], [width - 4, height - 5], [2, height - 10]])
    matrix = cv2.getPerspectiveTransform(source, target)
    shifted = cv2.warpPerspective(present, matrix, (width, height))
    shifted = np.clip(shifted.astype(np.int16) + 18, 0, 255).astype(np.uint8)
    assert classify_frame(shifted, full_ref, empty_ref)[0] == "PRESENT"


def test_two_reference_returns_unknown_for_unrelated_scene():
    present, empty = _scene()
    full_ref, empty_ref, _ = calibrate_pair(present, empty)
    unknown = np.random.default_rng(99).integers(0, 255, size=present.shape, dtype=np.uint8)
    assert classify_frame(unknown, full_ref, empty_ref)[0] == "UNKNOWN"


def test_calibration_rejects_identical_reference_images():
    present, _ = _scene()
    with pytest.raises(PresenceFeatureError):
        calibrate_pair(present, present.copy())
