"""Automated tests for Phase 7: Simulated Checkout, Invoicing, Exit Handling, and Dashboard Overview."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import CustomerSession, CartItem, Product, Invoice, InvoiceLine, Event, Zone
from backend.app.services.seed import seed_initial_data
from backend.app.services.event_service import record_transition


def get_admin_headers(client: TestClient) -> dict:
    login_res = client.post("/api/admin/login", json={"pin": settings.ADMIN_PIN})
    token = login_res.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def setup_active_session_with_cart(
    db: Session,
    secret: str = "checkout_test_secret_123",
) -> CustomerSession:
    """Helper to seed initial catalog, create active session, and add items to cart."""
    seed_initial_data(db)
    session = CustomerSession(
        status="ACTIVE",
        session_secret=secret,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Pick 2 of Product 1 (Zone 1) and 1 of Product 2 (Zone 2)
    z1 = db.query(Zone).filter_by(id=1).first()
    z2 = db.query(Zone).filter_by(id=2).first()

    record_transition(db, z1, "PRESENT", "ABSENT", transition_counter=1)
    record_transition(db, z1, "PRESENT", "ABSENT", transition_counter=2)
    record_transition(db, z2, "PRESENT", "ABSENT", transition_counter=3)

    return session


def test_checkout_creates_invoice_and_closes_session(client: TestClient, db_session: Session):
    """Test full atomic checkout flow: invoice creation, lines snapshot, events, and session closure."""
    secret = "checkout_atomic_secret_1"
    session = setup_active_session_with_cart(db_session, secret=secret)

    prod1 = db_session.query(Product).filter_by(id=1).first()
    prod2 = db_session.query(Product).filter_by(id=2).first()
    expected_total = (prod1.unit_price * 2) + (prod2.unit_price * 1)

    # 1. Post checkout
    res = client.post(f"/api/customer/checkout?secret={secret}")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    inv_data = data["invoice"]
    assert inv_data["total"] == expected_total
    assert len(inv_data["lines"]) == 2

    # 2. Verify Session in DB
    db_session.expire_all()
    closed_session = db_session.query(CustomerSession).filter_by(id=session.id).first()
    assert closed_session.status == "CLOSED"
    assert closed_session.exit_reason == "CHECKOUT"
    assert closed_session.exited_at is not None

    # 3. Verify Invoice in DB
    invoice = db_session.query(Invoice).filter_by(session_id=session.id).first()
    assert invoice is not None
    assert invoice.total == expected_total
    assert len(invoice.lines) == 2

    # Line 1: prod1 x 2
    l1 = next(l for l in invoice.lines if l.product_name == prod1.name)
    assert l1.unit_price == prod1.unit_price
    assert l1.quantity == 2
    assert l1.line_total == prod1.unit_price * 2

    # 4. Verify Events recorded in DB
    events = db_session.query(Event).filter_by(session_id=session.id).all()
    types = [e.type for e in events]
    assert "CHECKOUT_STARTED" in types
    assert "INVOICE_CREATED" in types
    assert "SESSION_CLOSED" in types


def test_double_checkout_creates_exactly_one_invoice(client: TestClient, db_session: Session):
    """Test idempotency: double clicking or repeating checkout returns existing invoice without duplication."""
    secret = "double_checkout_secret_2"
    session = setup_active_session_with_cart(db_session, secret=secret)

    # First checkout
    res1 = client.post(f"/api/customer/checkout?secret={secret}")
    assert res1.status_code == 200
    inv1_id = res1.json()["invoice"]["id"]

    # Second checkout attempt with identical secret
    res2 = client.post(f"/api/customer/checkout?secret={secret}")
    assert res2.status_code == 200
    assert res2.json()["success"] is True
    assert res2.json()["invoice"]["id"] == inv1_id

    # Strictly 1 invoice exists in DB
    assert db_session.query(Invoice).filter_by(session_id=session.id).count() == 1


def test_empty_cart_checkout_rejected(client: TestClient, db_session: Session):
    """Test that checkout is rejected when the customer has 0 items in their cart."""
    seed_initial_data(db_session)
    secret = "empty_cart_secret_3"
    session = CustomerSession(status="ACTIVE", session_secret=secret)
    db_session.add(session)
    db_session.commit()

    # Attempt checkout
    res = client.post(f"/api/customer/checkout?secret={secret}")
    assert res.status_code == 400
    assert "سبد خرید خالی است" in res.json()["detail"]

    # Session must remain ACTIVE
    db_session.expire_all()
    refreshed = db_session.query(CustomerSession).filter_by(id=session.id).first()
    assert refreshed.status == "ACTIVE"
    assert db_session.query(Invoice).count() == 0


def test_product_price_change_does_not_affect_historical_invoice(client: TestClient, db_session: Session):
    """Test that updating a product's unit price in the catalog preserves historical invoice amounts."""
    secret = "price_change_secret_4"
    session = setup_active_session_with_cart(db_session, secret=secret)
    prod1 = db_session.query(Product).filter_by(id=1).first()
    initial_price = prod1.unit_price

    # Checkout
    res = client.post(f"/api/customer/checkout?secret={secret}")
    assert res.status_code == 200
    inv_id = res.json()["invoice"]["id"]

    # Change product price in database (e.g. inflation / price update)
    prod1.unit_price = 150000
    db_session.commit()

    # Re-fetch invoice and line items
    db_session.expire_all()
    invoice = db_session.query(Invoice).filter_by(id=inv_id).first()
    line1 = next(l for l in invoice.lines if l.product_name == prod1.name)

    # Unit price and line total must match checkout-time snapshot
    assert line1.unit_price == initial_price
    assert line1.unit_price != 150000
    assert line1.line_total == initial_price * line1.quantity


def test_exit_without_purchase_closes_session_without_invoice(client: TestClient, db_session: Session):
    """Test exiting the store without buying when cart is empty."""
    seed_initial_data(db_session)
    secret = "exit_empty_secret_5"
    session = CustomerSession(status="ACTIVE", session_secret=secret)
    db_session.add(session)
    db_session.commit()

    # 1. Exit without purchase
    res = client.post(f"/api/customer/exit-empty?secret={secret}")
    assert res.status_code == 200
    assert res.json()["success"] is True

    # 2. Verify Session is CLOSED with exit_reason=EMPTY_EXIT
    db_session.expire_all()
    closed = db_session.query(CustomerSession).filter_by(id=session.id).first()
    assert closed.status == "CLOSED"
    assert closed.exit_reason == "EMPTY_EXIT"
    assert closed.exited_at is not None

    # 3. No invoice created
    assert db_session.query(Invoice).count() == 0


def test_exit_without_purchase_rejected_if_cart_not_empty(client: TestClient, db_session: Session):
    """Test that exit-without-purchase is rejected if customer still has items in their cart."""
    secret = "exit_not_empty_secret_6"
    setup_active_session_with_cart(db_session, secret=secret)

    res = client.post(f"/api/customer/exit-empty?secret={secret}")
    assert res.status_code == 400
    assert "شامل اقلامی است" in res.json()["detail"]


def test_admin_invoices_api_and_session_link(client: TestClient, db_session: Session):
    """Test admin GET /api/admin/invoices, /api/admin/invoices/{id}, and session invoice link."""
    secret = "admin_invoices_secret_7"
    session = setup_active_session_with_cart(db_session, secret=secret)
    client.post(f"/api/customer/checkout?secret={secret}")

    # Unauthenticated request rejected
    client.cookies.clear()
    unauth = client.get("/api/admin/invoices")
    assert unauth.status_code == 401

    headers = get_admin_headers(client)

    # 1. List invoices
    inv_res = client.get("/api/admin/invoices", headers=headers)
    assert inv_res.status_code == 200
    invoices = inv_res.json()
    assert len(invoices) >= 1
    target = invoices[0]
    inv_id = target["id"]
    assert target["session_id"] == session.id
    assert target["total"] > 0

    # 2. Get specific invoice details
    detail_res = client.get(f"/api/admin/invoices/{inv_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == inv_id
    assert len(detail["lines"]) == 2

    # 3. Verify session shows linked invoice
    sess_res = client.get("/api/admin/sessions", headers=headers)
    assert sess_res.status_code == 200
    sessions_list = sess_res.json()
    target_sess = next((s for s in sessions_list if s["id"] == session.id), None)
    assert target_sess is not None
    assert target_sess["invoice_id"] == inv_id
    assert target_sess["invoice_total"] == target["total"]


def test_admin_overview_telemetry_api(client: TestClient, db_session: Session):
    """Test admin GET /api/admin/overview returns complete store metrics."""
    seed_initial_data(db_session)
    secret = "overview_secret_8"
    setup_active_session_with_cart(db_session, secret=secret)
    headers = get_admin_headers(client)

    res = client.get("/api/admin/overview", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # Metric assertions
    assert data["today_sessions_count"] >= 1
    assert data["active_session"] is not None
    assert data["active_session"]["items_count"] == 3
    assert data["total_invoices_count"] == 0
    assert len(data["zones"]) == 3
    assert "camera_online" in data["devices"]
