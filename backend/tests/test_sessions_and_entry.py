import secrets
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models import EntryToken, CustomerSession, Event, utc_now
from backend.app.config import settings


def get_admin_headers(client: TestClient) -> dict:
    login_res = client.post("/api/admin/login", json={"pin": settings.ADMIN_PIN})
    token = login_res.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_creates_active_session_and_events(client: TestClient, db_session: Session):
    """Test valid single-use token creates ACTIVE session, marks token used, and logs Event."""
    # 1. Generate token via admin endpoint
    headers = get_admin_headers(client)
    res = client.post("/api/admin/token", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["active_session"] is False
    assert data["token"] is not None
    assert "/enter?token=" in data["enter_url"]
    token_str = data["token"]

    # 2. Customer visits /enter?token=...
    enter_res = client.get(f"/enter?token={token_str}", follow_redirects=False)
    assert enter_res.status_code == 303
    redirect_url = enter_res.headers["location"]
    assert "/customer?session=" in redirect_url

    session_secret = redirect_url.split("session=")[1]
    assert len(session_secret) > 10

    # 3. Verify in DB
    db_token = db_session.query(EntryToken).filter_by(token=token_str).first()
    assert db_token.used_at is not None

    db_session_obj = db_session.query(CustomerSession).filter_by(session_secret=session_secret).first()
    assert db_session_obj is not None
    assert db_session_obj.status == "ACTIVE"
    assert db_session_obj.entered_at is not None
    assert db_session_obj.exited_at is None

    # 4. Verify Event logged
    event = db_session.query(Event).filter_by(session_id=db_session_obj.id).first()
    assert event is not None
    assert event.type == "CUSTOMER_ENTERED"
    assert event.confidence == 1.0
    assert event.status == "PROCESSED"


def test_expired_token_rejected(client: TestClient, db_session: Session):
    """Test expired entry token is rejected with 400 and clear error message."""
    now = utc_now()
    expired_token = EntryToken(
        token="expired_" + secrets.token_urlsafe(16),
        created_at=now - timedelta(seconds=60),
        expires_at=now - timedelta(seconds=10),
    )
    db_session.add(expired_token)
    db_session.commit()

    res = client.get(f"/enter?token={expired_token.token}", follow_redirects=False)
    assert res.status_code == 400
    assert "منقضی شده" in res.text
    assert "Expired" in res.text

    # No session should be created
    sessions = db_session.query(CustomerSession).all()
    assert len(sessions) == 0


def test_used_token_cannot_be_reused(client: TestClient, db_session: Session):
    """Test that a token already used once cannot be used again."""
    headers = get_admin_headers(client)
    res = client.post("/api/admin/token", headers=headers)
    token_str = res.json()["token"]

    # First entry succeeds
    first_res = client.get(f"/enter?token={token_str}", follow_redirects=False)
    assert first_res.status_code == 303

    # Close session to simulate customer having exited
    active_session = db_session.query(CustomerSession).filter_by(status="ACTIVE").first()
    active_session.status = "CLOSED"
    active_session.exited_at = utc_now()
    active_session.exit_reason = "ADMIN"
    db_session.commit()

    # Second entry with the same token must fail
    second_res = client.get(f"/enter?token={token_str}", follow_redirects=False)
    assert second_res.status_code == 400
    assert "قبلاً استفاده شده" in second_res.text


def test_entry_rejected_when_store_is_occupied(client: TestClient, db_session: Session):
    """Test that a second customer cannot enter while an active session exists."""
    headers = get_admin_headers(client)
    t1_res = client.post("/api/admin/token", headers=headers)
    token1 = t1_res.json()["token"]

    # Customer 1 enters
    enter1 = client.get(f"/enter?token={token1}", follow_redirects=False)
    assert enter1.status_code == 303

    # Generate token 2 directly in DB (as admin endpoint would refuse)
    now = utc_now()
    token2_obj = EntryToken(
        token="token2_" + secrets.token_urlsafe(16),
        created_at=now,
        expires_at=now + timedelta(seconds=30),
    )
    db_session.add(token2_obj)
    db_session.commit()

    # Customer 2 attempts entry
    enter2 = client.get(f"/enter?token={token2_obj.token}", follow_redirects=False)
    assert enter2.status_code == 409
    assert "فروشگاه اشغال است" in enter2.text
    assert "Store is Currently Occupied" in enter2.text

    # Verify only 1 active session in DB
    active_sessions = db_session.query(CustomerSession).filter_by(status="ACTIVE").all()
    assert len(active_sessions) == 1


def test_admin_force_close_session_records_exit_and_event(client: TestClient, db_session: Session):
    """Test admin force-closing active session records exit time, reason, and SESSION_CLOSED event."""
    headers = get_admin_headers(client)
    t_res = client.post("/api/admin/token", headers=headers)
    token = t_res.json()["token"]

    # Customer enters
    client.get(f"/enter?token={token}", follow_redirects=False)
    session = db_session.query(CustomerSession).filter_by(status="ACTIVE").first()
    assert session is not None

    # Admin force closes
    close_res = client.post(f"/api/admin/sessions/{session.id}/close", headers=headers)
    assert close_res.status_code == 200
    data = close_res.json()
    assert data["status"] == "CLOSED"
    assert data["exit_reason"] == "ADMIN"
    assert data["exited_at"] is not None

    # Verify in DB
    db_session.refresh(session)
    assert session.status == "CLOSED"
    assert session.exit_reason == "ADMIN"
    assert session.exited_at is not None

    # Verify SESSION_CLOSED Event in DB
    event = db_session.query(Event).filter_by(session_id=session.id, type="SESSION_CLOSED").first()
    assert event is not None
    assert event.confidence == 1.0
    assert event.status == "PROCESSED"


def test_customer_session_status_api(client: TestClient, db_session: Session):
    """Test /api/customer/session validation endpoint."""
    headers = get_admin_headers(client)
    t_res = client.post("/api/admin/token", headers=headers)
    token = t_res.json()["token"]

    enter_res = client.get(f"/enter?token={token}", follow_redirects=False)
    secret = enter_res.headers["location"].split("session=")[1]

    # 1. Valid active session
    status_res = client.get(f"/api/customer/session?secret={secret}")
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["valid"] is True
    assert data["status"] == "ACTIVE"

    # 2. Non-existent secret
    fake_res = client.get("/api/customer/session?secret=non_existent_secret")
    assert fake_res.status_code == 200
    fake_data = fake_res.json()
    assert fake_data["valid"] is False

    # 3. Closed session
    session = db_session.query(CustomerSession).filter_by(session_secret=secret).first()
    session.status = "CLOSED"
    session.exit_reason = "ADMIN"
    db_session.commit()

    closed_res = client.get(f"/api/customer/session?secret={secret}")
    assert closed_res.status_code == 200
    closed_data = closed_res.json()
    assert closed_data["valid"] is False
    assert closed_data["status"] == "CLOSED"


def test_admin_token_endpoint_occupied_state(client: TestClient, db_session: Session):
    """Test that admin /api/admin/token returns occupied if a session is currently active."""
    headers = get_admin_headers(client)

    # 1. Free store
    res1 = client.post("/api/admin/token", headers=headers)
    assert res1.status_code == 200
    assert res1.json()["active_session"] is False
    token1 = res1.json()["token"]

    # Customer enters
    client.get(f"/enter?token={token1}", follow_redirects=False)

    # 2. Occupied store
    res2 = client.post("/api/admin/token", headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["active_session"] is True
    assert data2["token"] is None
    assert "اشغال است" in data2["message"]
