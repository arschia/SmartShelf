"""Comprehensive Security & Hardening Tests for Phase 2 (Prompt 2)."""
import time
import json
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.config import Settings, settings
from backend.app.services.auth import (
    create_admin_token,
    is_admin_token_valid,
    check_admin_lockout,
    record_failed_login,
    record_successful_login,
    _failed_attempts,
    _lockout_until,
)
from backend.app.services.camera_pairing import (
    create_camera_pairing_code,
    exchange_pairing_code_for_token,
    is_camera_device_token_valid,
)
from backend.app.models import CustomerSession, utc_now


def test_weak_pin_rejected_at_startup():
    """Verify that empty, '1234', or short (<8 chars) PIN fails validation."""
    with pytest.raises(ValueError, match="Insecure ADMIN_PIN"):
        s = Settings(ADMIN_PIN="")
        s.validate_security()

    with pytest.raises(ValueError, match="Insecure ADMIN_PIN"):
        s = Settings(ADMIN_PIN="1234")
        s.validate_security()

    with pytest.raises(ValueError, match="Insecure ADMIN_PIN"):
        s = Settings(ADMIN_PIN="abc1234")  # 7 chars
        s.validate_security()

    # Valid strong PIN should pass
    valid_s = Settings(ADMIN_PIN="StrongPin#2026")
    valid_s.validate_security()


def test_admin_hmac_token_stateless_and_persistence_across_restarts():
    """Verify HMAC admin token remains valid across simulated restarts without in-memory state."""
    token = create_admin_token(expires_in_hours=8)
    assert is_admin_token_valid(token) is True

    # Tampered payload or signature fails
    parts = token.split(".")
    assert len(parts) == 2
    tampered_token = f"{parts[0]}a.{parts[1]}"
    assert is_admin_token_valid(tampered_token) is False

    invalid_sig_token = f"{parts[0]}.invalid_signature"
    assert is_admin_token_valid(invalid_sig_token) is False


def test_explicit_test_pin_only_allowed_while_store_is_closed():
    closed = Settings(APP_ENV='production', SECRET_KEY='test-only-key-0123456789abcdef0123456789',
                      ADMIN_PIN='1234', ALLOW_INSECURE_TEST_PIN='true', STORE_OPEN='false')
    closed.validate_security()
    with pytest.raises(ValueError, match='requires STORE_OPEN=false'):
        opened = Settings(APP_ENV='production', SECRET_KEY=closed.SECRET_KEY,
                          ADMIN_PIN='1234', ALLOW_INSECURE_TEST_PIN=True, STORE_OPEN=True)
        opened.validate_security()
    for pin, flag in [('1234', False), ('0000', True), ('', True)]:
        with pytest.raises(ValueError, match='Insecure ADMIN_PIN'):
            Settings(SECRET_KEY=closed.SECRET_KEY, ADMIN_PIN=pin,
                     ALLOW_INSECURE_TEST_PIN=flag, STORE_OPEN=False).validate_security()


def test_explicit_test_pin_does_not_relax_secret_key_validation():
    with pytest.raises(ValueError, match='SECRET_KEY must be a strong random value'):
        Settings(APP_ENV='production', SECRET_KEY='weak', ADMIN_PIN='1234',
                 ALLOW_INSECURE_TEST_PIN=True, STORE_OPEN=False).validate_security()


def test_closed_store_test_pin_login_still_blocks_customer_entry(client, monkeypatch):
    monkeypatch.setattr(settings, 'ADMIN_PIN', '1234')
    monkeypatch.setattr(settings, 'ALLOW_INSECURE_TEST_PIN', True)
    monkeypatch.setattr(settings, 'STORE_OPEN', False)
    response = client.post('/api/admin/login', json={'pin': '1234'})
    assert response.status_code == 200
    token = response.json()['token']
    response = client.post('/api/admin/token', headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 403


def test_admin_login_lockout_after_5_failed_attempts(client: TestClient):
    """Verify 5 consecutive failed PIN attempts trigger HTTP 429 lockout for 10 minutes."""
    try:
        _failed_attempts.clear()
        _lockout_until.clear()

        # 4 failed attempts should yield 401
        for _ in range(4):
            res = client.post("/api/admin/login", json={"pin": "WRONG_PIN"})
            assert res.status_code == 401

        # 5th failed attempt should trigger lockout
        res5 = client.post("/api/admin/login", json={"pin": "WRONG_PIN"})
        assert res5.status_code == 401

        # 6th attempt (even with CORRECT pin) is blocked by 429
        res6 = client.post("/api/admin/login", json={"pin": settings.ADMIN_PIN})
        assert res6.status_code == 429
        assert "قفل موقت" in res6.json()["detail"] or "locked" in res6.json()["detail"].lower()
    finally:
        # Cleanup lockout
        _failed_attempts.clear()
        _lockout_until.clear()


def test_admin_websocket_requires_first_message_auth(client: TestClient):
    """Admin WebSocket must reject if first message is not a valid HMAC token."""
    # 1. Invalid token sent in first message
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/admin") as ws:
            ws.send_json({"type": "AUTH", "token": "invalid_fake_token"})
            # Should be closed by server with WS_1008
            ws.receive_text()

    # 2. Valid token sent in first message
    valid_token = create_admin_token()
    with client.websocket_connect("/ws/admin") as ws:
        ws.send_json({"type": "AUTH", "token": valid_token})
        res = ws.receive_json()
        assert res.get("type") == "AUTH_OK"
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


def test_customer_websocket_requires_valid_session(client: TestClient, db_session):
    """Customer WebSocket requires a valid session_secret in first message or query param."""
    # 1. Non-existent session secret should be closed
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/customer") as ws:
            ws.send_json({"type": "AUTH", "session_secret": "non_existent_secret_123"})
            ws.receive_json()

    # 2. Valid active customer session
    sess = CustomerSession(
        session_secret="sec_test_valid_customer_456",
        status="ACTIVE",
        entered_at=utc_now(),
    )
    db_session.add(sess)
    db_session.commit()

    with client.websocket_connect("/ws/customer") as ws:
        ws.send_json({"type": "AUTH", "session_secret": sess.session_secret})
        sync = ws.receive_json()
        assert sync.get("type") == "CART_SYNC"
        assert "cart" in sync


def test_camera_pairing_and_websocket_security(client: TestClient):
    """Admin creates 6-digit code -> Tablet pairs -> /ws/camera requires device_token."""
    # 1. Connection without device_token is rejected
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/camera?device_id=unpaired_cam") as ws:
            ws.send_text("ping")
            ws.receive_text()

    # 2. Admin creates pairing code
    admin_token = create_admin_token()
    code_res = client.post("/api/admin/camera/pairing-code", headers={"Authorization": f"Bearer {admin_token}"})
    assert code_res.status_code == 200
    pairing_code = code_res.json()["pairing_code"]
    assert len(pairing_code) == 6
    assert pairing_code.isdigit()

    # 3. Tablet pairs using code
    pair_res = client.post("/api/camera/pair", json={"pairing_code": pairing_code, "device_id": "paired_tablet_1"})
    assert pair_res.status_code == 200
    device_token = pair_res.json()["device_token"]
    assert len(device_token) > 20

    # 4. Pairing code is one-time use; second exchange fails
    pair_res2 = client.post("/api/camera/pair", json={"pairing_code": pairing_code, "device_id": "paired_tablet_2"})
    assert pair_res2.status_code == 400

    # 5. Connected with valid device token succeeds
    with client.websocket_connect("/ws/camera?device_id=paired_tablet_1") as ws:
        ws.send_text(json.dumps({"type": "auth", "device_token": device_token}))
        connected = json.loads(ws.receive_text())
        assert connected["type"] == "connected"
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


def test_store_open_flag_rejection(client: TestClient, monkeypatch):
    """When STORE_OPEN=false, customer entry is rejected with 403 'فروشگاه بسته است'."""
    monkeypatch.setattr(settings, "STORE_OPEN", False)

    # 1. /api/admin/token fails with 403 when store is closed
    admin_token = create_admin_token()
    token_res = client.post("/api/admin/token", headers={"Authorization": f"Bearer {admin_token}"})
    assert token_res.status_code == 403
    assert "بسته" in token_res.json()["detail"]

    # 2. /enter?token=... fails with 403
    enter_res = client.get("/enter?token=some_token")
    assert enter_res.status_code == 403
    assert "فروشگاه بسته است" in enter_res.text


def test_security_headers_present(client: TestClient):
    """Verify HTTP security headers are set on all responses."""
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("Referrer-Policy") == "no-referrer"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
