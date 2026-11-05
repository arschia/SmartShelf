"""Deployment safety regressions: no customer billing during calibration."""
from datetime import timedelta
from backend.app.config import settings
from backend.app.models import CartItem, CustomerSession, Event, Product, Zone
from backend.app.services.event_service import record_transition


def test_closed_store_does_not_mutate_cart(db_session, monkeypatch):
    monkeypatch.setattr(settings, 'STORE_OPEN', False)
    product = Product(sku='SAFE-PATCH-1', name='Safety test', unit_price=1000)
    db_session.add(product)
    db_session.flush()
    zone = Zone(name='Test slot', product_id=product.id, state='PRESENT')
    session = CustomerSession(status='ACTIVE', session_secret='test-safety-secret-1234567890')
    db_session.add_all([zone, session])
    db_session.commit()

    event, notification = record_transition(db_session, zone, 'PRESENT', 'ABSENT', transition_counter=1)
    assert event.status == 'OBSERVED_STORE_CLOSED'
    assert notification is None
    assert db_session.query(CartItem).count() == 0
    event2, _ = record_transition(db_session, zone, 'PRESENT', 'ABSENT', transition_counter=1)
    assert event2.id == event.id
    assert db_session.query(Event).count() == 1


def test_qr_token_expires_in_30_seconds(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, 'STORE_OPEN', True)
    res = client.post('/api/admin/token', headers=auth_headers)
    assert res.status_code == 200
    assert res.json()['expires_in'] == settings.ENTRY_TOKEN_TTL_SECONDS == 30
    if settings.PUBLIC_BASE_URL.startswith('https://') and settings.FRONTEND_PUBLIC_URL:
        assert 'api=' in res.json()['enter_url']
