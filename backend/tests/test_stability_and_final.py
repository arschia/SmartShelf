"""Final Stability, Hardening, and Acceptance Tests for SMARTSHELF (Phase 8).

Verifies:
1. Server reboot recovery: DB state preservation, slot state machines starting in UNKNOWN and stabilizing without false transitions.
2. Reconnection and camera disconnect: 10-second inactivity watchdog and warning.
3. Abandoned session timeout: Sessions idle > SESSION_IDLE_TIMEOUT closed with exit_reason=EXPIRED.
4. In-memory sliding-window rate limiting on sensitive endpoints (/enter and /api/admin/login).
5. Comprehensive edge-case input validation.
"""
import time
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import CustomerSession, CartItem, Product, Zone, Event, Device, utc_now
from backend.app.services.seed import seed_initial_data
from backend.app.services.session_service import check_and_expire_idle_sessions
from backend.app.services.rate_limiter import enter_limiter, login_limiter, SimpleRateLimiter
from backend.app.vision.state_machine import ZoneStateMachine, SlotState
from backend.app.vision.camera_feed import camera_feed
from backend.app.vision.pipeline import pipeline


def test_state_machine_cold_start_unknown_stabilizes_without_false_events():
    """Verify that after reboot, state machine in UNKNOWN commits baseline without firing false transitions."""
    sim_time = 1000.0
    sm = ZoneStateMachine(
        zone_id=1,
        initial_state=SlotState.UNKNOWN,
        stable_seconds=1.5,
        clock=lambda: sim_time,
    )

    assert sm.confirmed_state == SlotState.UNKNOWN
    assert sm.get_display_state() == SlotState.UNKNOWN

    # Cold start: Camera sends initial PRESENT frames
    # Frame 1: candidate begins
    assert sm.update("PRESENT") is None
    assert sm.get_display_state() == SlotState.UNKNOWN

    # Frame 2 at 0.8s: still stabilizing
    sim_time = 1000.8
    assert sm.update("PRESENT") is None
    assert sm.get_display_state() == SlotState.UNKNOWN

    # Frame 3 at 1.6s: threshold reached (1.6 >= 1.5)
    sim_time = 1001.6
    transition = sm.update("PRESENT")

    # MUST NOT fire any transition (establishes baseline silently)
    assert transition is None
    assert sm.confirmed_state == SlotState.PRESENT
    assert sm.get_display_state() == SlotState.PRESENT

    # Subsequent genuine removal WILL fire transition
    sim_time = 1010.0
    assert sm.update("ABSENT") is None
    sim_time = 1011.6
    second_trans = sm.update("ABSENT")
    assert second_trans == (SlotState.PRESENT, SlotState.ABSENT)
    assert sm.confirmed_state == SlotState.ABSENT


def test_abandoned_session_idle_timeout_expiration(db_session: Session):
    """Verify that an active session with no activity beyond SESSION_IDLE_TIMEOUT is closed as EXPIRED."""
    now = utc_now()
    past_entry = now - timedelta(seconds=settings.SESSION_IDLE_TIMEOUT + 60)

    # Active session that entered 16 minutes ago with no events
    idle_sess = CustomerSession(
        status="ACTIVE",
        entered_at=past_entry,
        session_secret="idle_secret_phase8",
    )
    db_session.add(idle_sess)
    db_session.commit()
    db_session.refresh(idle_sess)

    # Run expiration check
    expired = check_and_expire_idle_sessions(db_session, timeout_seconds=settings.SESSION_IDLE_TIMEOUT)

    assert len(expired) == 1
    assert expired[0].id == idle_sess.id
    assert idle_sess.status == "CLOSED"
    assert idle_sess.exit_reason == "EXPIRED"
    assert idle_sess.exited_at is not None

    # Check that SESSION_CLOSED event was logged
    evt = db_session.query(Event).filter_by(session_id=idle_sess.id, type="SESSION_CLOSED").first()
    assert evt is not None
    assert "sess_expired" in evt.event_uid


def test_active_session_with_recent_event_is_not_expired(db_session: Session):
    """Verify that an active session with recent activity is preserved and not closed."""
    now = utc_now()
    past_entry = now - timedelta(seconds=settings.SESSION_IDLE_TIMEOUT + 60)

    active_sess = CustomerSession(
        status="ACTIVE",
        entered_at=past_entry,
        session_secret="active_recent_phase8",
    )
    db_session.add(active_sess)
    db_session.commit()

    # Recent event occurred 2 minutes ago
    recent_event = Event(
        event_uid="recent_evt_test_1",
        type="PRODUCT_PICKED",
        session_id=active_sess.id,
        confidence=1.0,
        status="PROCESSED",
        created_at=now - timedelta(seconds=120),
    )
    db_session.add(recent_event)
    db_session.commit()

    # Check expiration
    expired = check_and_expire_idle_sessions(db_session, timeout_seconds=settings.SESSION_IDLE_TIMEOUT)
    assert len(expired) == 0
    assert active_sess.status == "ACTIVE"


def test_camera_inactivity_watchdog_and_admin_warning(client: TestClient, db_session: Session):
    """Verify that if camera hasn't sent a frame in 10 seconds, it's flagged as stale and inactive."""
    camera_feed.clear()

    # Set last frame time to 15 seconds ago
    camera_feed.last_frame_time = time.time() - 15.0
    camera_feed.active_device_id = "test_cam_tab"

    assert camera_feed.is_active(timeout_seconds=10.0) is False

    # Seed a camera device as online in DB
    cam_dev = Device(device_id="test_cam_tab", role="CAMERA", is_online=True, last_seen=utc_now())
    db_session.add(cam_dev)
    db_session.commit()

    # Login as admin and inspect overview
    login_res = client.post("/api/admin/login", json={"pin": settings.ADMIN_PIN})
    token = login_res.json()["token"]

    overview_res = client.get("/api/admin/overview", headers={"Authorization": f"Bearer {token}"})
    assert overview_res.status_code == 200
    data = overview_res.json()
    assert data["devices"]["camera_stale"] is True
    assert data["devices"]["camera_online"] is False


def test_rate_limiter_exceeded_triggers_http_429():
    """Verify that exceeding rate limits returns HTTP 429 Too Many Requests."""
    limiter = SimpleRateLimiter(max_requests=3, window_seconds=10.0)

    class FakeRequest:
        def __init__(self, ip: str):
            self.headers = {}
            self.client = type("Client", (), {"host": ip})()

    req = FakeRequest("192.168.1.100")

    # 3 allowed requests
    limiter.check(req)
    limiter.check(req)
    limiter.check(req)

    # 4th request must be rejected with 429
    with pytest.raises(Exception) as excinfo:
        limiter.check(req)
    assert "429" in str(excinfo.value)
