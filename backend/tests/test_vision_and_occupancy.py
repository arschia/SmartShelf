"""Automated tests for Phase 5: Vision calibration, occupancy scoring, and debounced state machine."""
import json
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import Zone
from backend.app.services.seed import seed_initial_data
from backend.app.vision.occupancy import (
    extract_features,
    compare_features,
    classify_roi_occupancy,
    crop_relative_roi,
)
from backend.app.vision.state_machine import ZoneStateMachine, SlotState
from backend.app.vision.camera_feed import camera_feed
from backend.app.vision.pipeline import pipeline


def get_admin_headers(client: TestClient) -> dict:
    login_res = client.post("/api/admin/login", json={"pin": settings.ADMIN_PIN})
    token = login_res.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def create_synthetic_full_roi(width: int = 120, height: int = 150) -> np.ndarray:
    """Create a synthetic image representing a populated shelf slot (product present)."""
    img = np.full((height, width, 3), (30, 30, 30), dtype=np.uint8)  # shelf background
    # Vibrant product box (red & gold)
    cv2.rectangle(img, (20, 25), (width - 20, height - 15), (20, 30, 220), -1)
    cv2.rectangle(img, (35, 45), (width - 35, height - 45), (0, 215, 255), -1)
    return img


def create_synthetic_empty_roi(width: int = 120, height: int = 150) -> np.ndarray:
    """Create a synthetic image representing an empty shelf slot (wood/dark gray shelf only)."""
    img = np.full((height, width, 3), (30, 30, 30), dtype=np.uint8)
    # Simple shelf plank lines
    cv2.line(img, (0, height // 2), (width, height // 2), (45, 45, 45), 2)
    return img


def test_occupancy_present_vs_absent_classification():
    """Verify that a populated slot classifies as PRESENT and an empty slot as ABSENT."""
    full_img = create_synthetic_full_roi()
    empty_img = create_synthetic_empty_roi()

    ref_full = extract_features(full_img)
    ref_empty = extract_features(empty_img)

    # 1. Populated slot -> PRESENT
    state_pop, conf_pop = classify_roi_occupancy(
        extract_features(full_img),
        ref_full=ref_full,
        ref_empty=ref_empty,
        threshold_present=0.60,
        threshold_absent=0.60,
    )
    assert state_pop == "PRESENT"
    assert conf_pop >= 0.70

    # 2. Empty slot -> ABSENT
    state_emp, conf_emp = classify_roi_occupancy(
        extract_features(empty_img),
        ref_full=ref_full,
        ref_empty=ref_empty,
        threshold_present=0.60,
        threshold_absent=0.60,
    )
    assert state_emp == "ABSENT"
    assert conf_emp >= 0.70




def test_single_reference_never_guesses_the_opposite_state():
    """A missing reference must be UNKNOWN, not proof that the product was removed."""
    full_img = create_synthetic_full_roi()
    ref_full = extract_features(full_img)
    state, confidence = classify_roi_occupancy(
        extract_features(create_synthetic_empty_roi()),
        ref_full=ref_full,
        ref_empty=None,
    )
    assert state == "UNKNOWN"
    assert confidence == 0.0


def test_unknown_observation_breaks_continuous_debounce_window():
    """An UNKNOWN frame must restart the timer; absence must be continuous."""
    sim_time = 0.0
    sm = ZoneStateMachine(
        zone_id=11,
        initial_state=SlotState.PRESENT,
        stable_seconds=1.5,
        clock=lambda: sim_time,
    )
    assert sm.update("ABSENT") is None
    sim_time = 1.0
    assert sm.update("UNKNOWN") is None
    sim_time = 1.5
    assert sm.update("ABSENT") is None
    sim_time = 2.4
    assert sm.update("ABSENT") is None
    sim_time = 3.1
    assert sm.update("ABSENT") == (SlotState.PRESENT, SlotState.ABSENT)


def test_debounce_works_when_clock_starts_at_zero():
    """Timestamp zero is a valid start time and must not stall debounce."""
    sim_time = 0.0
    sm = ZoneStateMachine(
        zone_id=12,
        initial_state=SlotState.PRESENT,
        stable_seconds=1.5,
        clock=lambda: sim_time,
    )
    assert sm.update("ABSENT") is None
    sim_time = 1.0
    assert sm.update("ABSENT") is None
    sim_time = 1.6
    assert sm.update("ABSENT") == (SlotState.PRESENT, SlotState.ABSENT)


def test_state_machine_short_occlusion_produces_no_transition():
    """Verify that transient occlusion shorter than STABLE_SECONDS produces NO state transition."""
    # Clock injection variable
    sim_time = 100.0

    sm = ZoneStateMachine(
        zone_id=1,
        initial_state=SlotState.PRESENT,
        stable_seconds=1.5,
        clock=lambda: sim_time,
    )

    # Initial stable state
    assert sm.update("PRESENT") is None
    assert sm.get_display_state() == SlotState.PRESENT

    # Hand moves across shelf (observation drops to ABSENT)
    sim_time = 100.1
    assert sm.update("ABSENT") is None
    assert sm.get_display_state() == SlotState.TRANSITION

    # Hand still covering at 0.5s (< 1.5s threshold)
    sim_time = 100.6
    assert sm.update("ABSENT") is None
    assert sm.get_display_state() == SlotState.TRANSITION

    # Hand leaves shelf at 0.8s: observation returns to PRESENT
    sim_time = 100.9
    assert sm.update("PRESENT") is None

    # Transition aborted: display and confirmed state must remain PRESENT
    assert sm.get_display_state() == SlotState.PRESENT
    assert sm.confirmed_state == SlotState.PRESENT

    # Time progresses further
    sim_time = 105.0
    assert sm.update("PRESENT") is None
    assert sm.confirmed_state == SlotState.PRESENT


def test_state_machine_stable_occlusion_produces_exactly_one_transition():
    """Verify that a genuine change persisting >= STABLE_SECONDS emits exactly one transition."""
    sim_time = 0.0

    sm = ZoneStateMachine(
        zone_id=2,
        initial_state=SlotState.PRESENT,
        stable_seconds=1.5,
        clock=lambda: sim_time,
    )

    # Product is picked up: observation becomes ABSENT
    sim_time = 10.0
    res = sm.update("ABSENT")
    assert res is None
    assert sm.get_display_state() == SlotState.TRANSITION

    # 1.0s elapsed (< 1.5s)
    sim_time = 11.0
    assert sm.update("ABSENT") is None
    assert sm.get_display_state() == SlotState.TRANSITION

    # 1.6s elapsed (>= 1.5s threshold): MUST emit confirmed transition
    sim_time = 11.6
    transition = sm.update("ABSENT")
    assert transition == (SlotState.PRESENT, SlotState.ABSENT)
    assert sm.confirmed_state == SlotState.ABSENT
    assert sm.get_display_state() == SlotState.ABSENT

    # Subsequent frames must NOT re-emit
    sim_time = 11.7
    assert sm.update("ABSENT") is None

    sim_time = 15.0
    assert sm.update("ABSENT") is None
    assert sm.confirmed_state == SlotState.ABSENT


def test_occupancy_mild_lighting_change_does_not_cause_false_classification():
    """Verify that mild lighting illumination changes do not cause false classification."""
    full_base = create_synthetic_full_roi()
    empty_base = create_synthetic_empty_roi()

    ref_full = extract_features(full_base)
    ref_empty = extract_features(empty_base)

    # Simulate +30 brightness increase on populated item
    full_illuminated = np.clip(full_base.astype(np.int16) + 30, 0, 255).astype(np.uint8)
    state, conf = classify_roi_occupancy(
        extract_features(full_illuminated),
        ref_full=ref_full,
        ref_empty=ref_empty,
        threshold_present=0.55,
        threshold_absent=0.55,
    )
    assert state == "PRESENT"
    assert conf > 0.50


def test_state_machine_duplicate_frame_does_not_retrigger_transition():
    """Verify that repeated duplicate observations never re-trigger confirmed transitions."""
    sim_time = 50.0
    sm = ZoneStateMachine(
        zone_id=3,
        initial_state=SlotState.ABSENT,
        stable_seconds=1.5,
        clock=lambda: sim_time,
    )

    # Product returned to shelf
    sim_time = 50.1
    sm.update("PRESENT")

    sim_time = 51.7  # 1.6s later -> confirmed
    trans = sm.update("PRESENT")
    assert trans == (SlotState.ABSENT, SlotState.PRESENT)

    # 20 duplicate subsequent frames
    for i in range(1, 21):
        sim_time += 0.2
        assert sm.update("PRESENT") is None


def test_admin_roi_update_and_reference_capture_api(client: TestClient, db_session: Session):
    """Test updating zone ROI and capturing in-memory reference features via admin endpoints."""
    seed_initial_data(db_session)
    headers = get_admin_headers(client)

    # 1. Update Zone 1 ROI
    roi_payload = {
        "roi_x": 0.12,
        "roi_y": 0.25,
        "roi_w": 0.22,
        "roi_h": 0.50,
    }
    res = client.put("/api/admin/zones/1/roi", json=roi_payload, headers=headers)
    assert res.status_code == 200
    z_data = res.json()
    assert abs(z_data["roi_x"] - 0.12) < 1e-4
    assert abs(z_data["roi_w"] - 0.22) < 1e-4

    # 2. Feed a synthetic camera frame into RAM buffer
    synthetic_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(synthetic_frame, (50, 50), (300, 300), (0, 200, 200), -1)
    _, buf = cv2.imencode(".jpg", synthetic_frame)
    camera_feed.process_frame_bytes("test_dev", buf.tobytes())

    # 3. Capture FULL reference for Zone 1
    cap_res = client.post(
        "/api/admin/zones/1/capture-reference",
        json={"reference_type": "FULL"},
        headers=headers,
    )
    assert cap_res.status_code == 200
    cap_data = cap_res.json()
    assert cap_data["success"] is True
    assert cap_data["reference_type"] == "FULL"

    # Verify stored in DB as computed features
    db_session.expire_all()
    zone = db_session.query(Zone).filter_by(id=1).first()
    assert zone.ref_full_features is not None
    features = json.loads(zone.ref_full_features)
    assert "hist" in features
    assert "thumb" in features
    assert len(features["hist"]) == 128
    assert len(features["thumb"]) == 256

    # 4. Capture All Full References
    all_cap_res = client.post("/api/admin/zones/capture-all-full", headers=headers)
    assert all_cap_res.status_code == 200
    all_cap_data = all_cap_res.json()
    assert all_cap_data["success"] is True
    assert len(all_cap_data["zones_calibrated"]) == 3
