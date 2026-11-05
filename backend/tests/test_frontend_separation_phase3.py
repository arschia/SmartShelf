"""Tests for Frontend Separation, API Entry, and Asset Integrity (Prompt 3)."""
import subprocess
import sys
from pathlib import Path
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import EntryToken, CustomerSession, utc_now
from backend.app.services.auth import create_admin_token


def test_api_enter_valid_token_success(client: TestClient, db_session: Session):
    """POST /api/enter with a valid QR token creates an active session and returns session_secret."""
    # 1. Admin generates token
    admin_token = create_admin_token()
    tok_res = client.post("/api/admin/token", headers={"Authorization": f"Bearer {admin_token}"})
    assert tok_res.status_code == 200
    token_str = tok_res.json()["token"]

    # 2. Customer posts to /api/enter
    enter_res = client.post("/api/enter", json={"token": token_str})
    assert enter_res.status_code == 200
    data = enter_res.json()
    assert "session_secret" in data
    assert len(data["session_secret"]) > 20
    assert data["status"] == "ACTIVE"
    assert data["session_id"] > 0

    # 3. Verify in DB
    db_session.expire_all()
    token_db = db_session.query(EntryToken).filter_by(token=token_str).first()
    assert token_db.used_at is not None

    sess_db = db_session.query(CustomerSession).filter_by(session_secret=data["session_secret"]).first()
    assert sess_db is not None
    assert sess_db.status == "ACTIVE"


def test_api_enter_expired_token_rejected(client: TestClient, db_session: Session):
    """POST /api/enter with an expired token returns HTTP 410 GONE."""
    now = utc_now()
    expired_tok = EntryToken(
        token="tok_expired_test_123",
        created_at=now - timedelta(seconds=60),
        expires_at=now - timedelta(seconds=10),
    )
    db_session.add(expired_tok)
    db_session.commit()

    res = client.post("/api/enter", json={"token": expired_tok.token})
    assert res.status_code == 410
    assert "منقضی" in res.json()["detail"]


def test_api_enter_used_token_rejected(client: TestClient, db_session: Session):
    """POST /api/enter with an already-used token returns HTTP 400 BAD REQUEST."""
    admin_token = create_admin_token()
    tok_res = client.post("/api/admin/token", headers={"Authorization": f"Bearer {admin_token}"})
    token_str = tok_res.json()["token"]

    # First entry succeeds
    first_res = client.post("/api/enter", json={"token": token_str})
    assert first_res.status_code == 200

    # Mark first session closed so store isn't occupied, then re-try token
    db_session.expire_all()
    sess = db_session.query(CustomerSession).filter_by(status="ACTIVE").first()
    if sess:
        sess.status = "CLOSED"
        db_session.commit()

    # Second entry fails
    second_res = client.post("/api/enter", json={"token": token_str})
    assert second_res.status_code == 400
    assert "نامعتبر" in second_res.json()["detail"] or "استفاده" in second_res.json()["detail"]


def test_api_enter_occupied_store_rejected(client: TestClient, db_session: Session):
    """POST /api/enter when store is occupied returns HTTP 409 CONFLICT."""
    # Active session inside
    now = utc_now()
    existing_sess = CustomerSession(
        session_secret="sec_occupied_occupant",
        status="ACTIVE",
        entered_at=now,
    )
    db_session.add(existing_sess)

    # Valid token waiting
    tok = EntryToken(
        token="tok_waiting_outside",
        created_at=now,
        expires_at=now + timedelta(seconds=30),
    )
    db_session.add(tok)
    db_session.commit()

    res = client.post("/api/enter", json={"token": tok.token})
    assert res.status_code == 409
    assert "اشغال" in res.json()["detail"]


def test_api_enter_closed_store_rejected(client: TestClient, db_session: Session, monkeypatch):
    """POST /api/enter when STORE_OPEN=false returns HTTP 403 FORBIDDEN."""
    monkeypatch.setattr(settings, "STORE_OPEN", False)

    now = utc_now()
    tok = EntryToken(
        token="tok_store_closed_test",
        created_at=now,
        expires_at=now + timedelta(seconds=30),
    )
    db_session.add(tok)
    db_session.commit()

    res = client.post("/api/enter", json={"token": tok.token})
    assert res.status_code == 403
    assert "بسته" in res.json()["detail"]


def test_frontend_portal_and_assets_served(client: TestClient):
    """Verify landing portal, config.js, and static assets are served properly."""
    # 1. Landing portal
    root_res = client.get("/")
    assert root_res.status_code == 200
    assert "های کلاب" in root_res.text or "SMARTSHELF" in root_res.text

    # 2. config.js
    cfg_res = client.get("/config.js")
    assert cfg_res.status_code == 200
    assert "SMARTSHELF_CONFIG" in cfg_res.text

    # 3. Shared api.js
    api_res = client.get("/assets/js/api.js")
    assert api_res.status_code == 200
    assert "SmartShelfApi" in api_res.text

    # 4. Dana font CSS
    font_res = client.get("/assets/fonts/dana.css")
    assert font_res.status_code == 200
    assert "@font-face" in font_res.text


def test_frontend_asset_paths_integrity_script():
    """Run check_frontend_paths.py to guarantee 0 missing assets."""
    project_root = Path(__file__).resolve().parent.parent.parent
    script_path = project_root / "scripts" / "check_frontend_paths.py"

    res = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True)
    assert res.returncode == 0, f"Asset check failed:\n{res.stdout}\n{res.stderr}"
    assert "ALL REFERENCED ASSET PATHS EXIST!" in res.stdout
