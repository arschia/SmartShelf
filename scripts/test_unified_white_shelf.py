"""Minimal smoke test for the fixed Windows local white-shelf reference mode."""
import cv2
import numpy as np
from backend.app.vision.two_reference import (
    calibrate_pair, classify_frame, crop_roi, is_two_reference, PresenceFeatureError
)

empty = np.full((480, 640, 3), 225, dtype=np.uint8)
present = empty.copy()
roi = [.35, .35, .3, .5]
cv2.rectangle(present, (260, 205), (350, 370), (50, 90, 120), -1)
cv2.rectangle(present, (270, 220), (340, 310), (190, 190, 190), -1)
full_ref, empty_ref, _ = calibrate_pair(present, empty, roi)
assert is_two_reference(full_ref) and is_two_reference(empty_ref)
assert classify_frame(crop_roi(present, roi), full_ref, empty_ref)[0] == "PRESENT"
assert classify_frame(crop_roi(empty, roi), full_ref, empty_ref)[0] == "ABSENT"
ambiguous = ((present.astype(np.float32) + empty.astype(np.float32)) / 2).astype(np.uint8)
assert classify_frame(crop_roi(ambiguous, roi), full_ref, empty_ref)[0] == "UNKNOWN"
print("PASS: Windows-local white-shelf reference calibration and safe ambiguity")
