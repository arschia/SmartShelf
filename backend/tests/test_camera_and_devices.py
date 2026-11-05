import os
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models import Device
from backend.app.config import settings
from backend.app.vision.camera_feed import camera_feed
from backend.app.services.camera_pairing import create_camera_pairing_code, exchange_pairing_code_for_token


def get_camera_token(device_id: str) -> str:
    code = create_camera_pairing_code()
    return exchange_pairing_code_for_token(code, device_id)


def get_admin_headers(client: TestClient) -> dict:
    login_res = client.post("/api/admin/login", json={"pin": settings.ADMIN_PIN})
    token = login_res.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def create_synthetic_jpeg_frame(width: int = 640, height: int = 480) -> bytes:
    """Create a synthetic RGB test pattern frame in memory and encode as JPEG bytes."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (width - 50, height - 50), (216, 180, 0), -1)
    cv2.rectangle(img, (20, 20), (width - 20, height - 20), (43, 19, 11), 4)

    success, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    assert success is True
    return buffer.tobytes()


def test_camera_websocket_device_registration_and_offline(client: TestClient, db_session: Session):
    """Test /ws/camera registers device as online and marks offline upon disconnect."""
    device_id = "test_tablet_cam_101"

    # Before connection: device does not exist
    dev = db_session.query(Device).filter_by(device_id=device_id).first()
    assert dev is None

    # Connect WebSocket with paired device token
    token = get_camera_token(device_id)
    with client.websocket_connect(f"/ws/camera?device_id={device_id}") as ws:
        ws.send_text(json.dumps({"type": "auth", "device_token": token}))
        assert json.loads(ws.receive_text())["type"] == "connected"
        # Ping/pong sync to ensure initial registration block committed
        ws.send_text("ping")
        assert ws.receive_text() == "pong"

        # Check DB: device registered and online
        db_session.expire_all()
        dev = db_session.query(Device).filter_by(device_id=device_id).first()
        assert dev is not None
        assert dev.role == "CAMERA"
        assert dev.is_online is True

    # After WebSocket disconnect: device marked offline
    db_session.expire_all()
    dev_after = db_session.query(Device).filter_by(device_id=device_id).first()
    assert dev_after is not None
    assert dev_after.is_online is False


def test_camera_frame_in_memory_decoding_and_zero_disk_write(client: TestClient, db_session: Session):
    """Test that incoming camera frames are decoded by OpenCV and NEVER written to disk."""
    camera_feed.clear()
    device_id = "test_tablet_cam_feed"

    project_root = Path(__file__).resolve().parent.parent.parent
    files_before = set(project_root.rglob("*.*"))

    frame_bytes = create_synthetic_jpeg_frame(640, 480)
    assert len(frame_bytes) > 0

    token = get_camera_token(device_id)
    with client.websocket_connect(f"/ws/camera?device_id={device_id}") as ws:
        ws.send_text(json.dumps({"type": "auth", "device_token": token}))
        assert json.loads(ws.receive_text())["type"] == "connected"
        # Send 3 binary frames
        for _ in range(3):
            ws.send_bytes(frame_bytes)

        # Synchronize via ping/pong
        ws.send_text("ping")
        assert ws.receive_text() == "pong"

        # Check in-memory decoding
        latest = camera_feed.get_latest_frame()
        assert latest is not None
        assert isinstance(latest, np.ndarray)
        assert latest.shape == (480, 640, 3)

        stats = camera_feed.get_stats()
        assert stats["has_frame"] is True
        assert stats["frame_count"] == 3
        assert stats["resolution"] == "640x480"
        assert stats["device_id"] == device_id

    # Check that NO new files were written to disk
    files_after = set(project_root.rglob("*.*"))
    new_files = [
        f for f in files_after - files_before
        if not f.name.endswith(".db") and not f.name.endswith(".pyc") and "__pycache__" not in str(f) and ".pytest_cache" not in str(f)
    ]
    assert len(new_files) == 0, f"Unexpected files written to disk: {new_files}"


def test_admin_devices_and_camera_preview_endpoints(client: TestClient, db_session: Session):
    """Test admin endpoints for listing devices and retrieving latest camera frame."""
    camera_feed.clear()
    headers = get_admin_headers(client)

    # 1. Connect a camera and send a frame
    device_id = "preview_cam_test"
    test_jpeg = create_synthetic_jpeg_frame(320, 240)

    token = get_camera_token(device_id)
    with client.websocket_connect(f"/ws/camera?device_id={device_id}") as ws:
        ws.send_text(json.dumps({"type": "auth", "device_token": token}))
        assert json.loads(ws.receive_text())["type"] == "connected"
        ws.send_bytes(test_jpeg)
        ws.send_text("ping")
        assert ws.receive_text() == "pong"

        # 2. Check /api/admin/devices
        dev_res = client.get("/api/admin/devices", headers=headers)
        assert dev_res.status_code == 200
        devices = dev_res.json()
        target = next((d for d in devices if d["device_id"] == device_id), None)
        assert target is not None
        assert target["is_online"] is True
        assert target["role"] == "CAMERA"

        # 3. Check /api/admin/camera/status
        status_res = client.get("/api/admin/camera/status", headers=headers)
        assert status_res.status_code == 200
        stats = status_res.json()
        assert stats["has_frame"] is True
        assert stats["resolution"] == "320x240"

        # 4. Check /api/admin/camera/latest-frame (returns JPEG bytes)
        frame_res = client.get("/api/admin/camera/latest-frame", headers=headers)
        assert frame_res.status_code == 200
        assert frame_res.headers["content-type"] == "image/jpeg"
        assert len(frame_res.content) > 0
        assert frame_res.content.startswith(b"\xff\xd8")


def test_camera_static_page_accessible(client: TestClient):
    """Verify that /camera route serves the tablet camera web app."""
    res = client.get("/camera/")
    assert res.status_code == 200
    assert "SMARTSHELF" in res.text
    assert "cameraVideo" in res.text


def test_camera_feed_rejects_oversized_or_invalid_device_frames():
    """Reject oversized payloads and invalid device IDs before decoding."""
    camera_feed.clear()
    too_large = b"x" * (camera_feed.MAX_FRAME_BYTES + 1)
    assert camera_feed.process_frame_bytes("valid_camera_01", too_large) is False
    valid_jpeg = create_synthetic_jpeg_frame(320, 240)
    assert camera_feed.process_frame_bytes("x" * 60, valid_jpeg) is False
    assert camera_feed.get_latest_frame() is None
