"""Customer Session Lifecycle and Idle Expiration Services."""
from datetime import timedelta
from typing import List, Optional
from sqlalchemy.orm import Session

from ..config import settings
from ..models import CustomerSession, Event, utc_now
from ..ws import manager


def check_and_expire_idle_sessions(db: Session, timeout_seconds: Optional[int] = None) -> List[CustomerSession]:
    """Check for ACTIVE sessions idle longer than timeout and close them with exit_reason=EXPIRED."""
    if timeout_seconds is None:
        timeout_seconds = settings.SESSION_IDLE_TIMEOUT

    now = utc_now()
    cutoff = now - timedelta(seconds=timeout_seconds)

    active_sessions = db.query(CustomerSession).filter_by(status="ACTIVE").all()
    expired_sessions = []

    for s in active_sessions:
        # Check last activity: latest Event for this session, or s.entered_at
        last_event = (
            db.query(Event)
            .filter_by(session_id=s.id)
            .order_by(Event.created_at.desc())
            .first()
        )
        last_activity = last_event.created_at if last_event and last_event.created_at else s.entered_at

        if last_activity and last_activity < cutoff:
            s.status = "CLOSED"
            s.exited_at = now
            s.exit_reason = "EXPIRED"

            close_evt = Event(
                event_uid=f"sess_expired_{s.id}_{int(now.timestamp())}",
                type="SESSION_CLOSED",
                session_id=s.id,
                confidence=1.0,
                status="PROCESSED",
                created_at=now,
            )
            db.add(close_evt)
            expired_sessions.append(s)

    if expired_sessions:
        db.commit()

    return expired_sessions
