"""Automated tests for Phase 6: Events, Shopping Cart business rules, and Live Customer View."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import CustomerSession, CartItem, Event, Zone, Product
from backend.app.services.seed import seed_initial_data
from backend.app.services.event_service import (
    record_transition,
    record_system_event,
    get_cart_summary,
)


def get_admin_headers(client: TestClient) -> dict:
    login_res = client.post("/api/admin/login", json={"pin": settings.ADMIN_PIN})
    token = login_res.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def setup_active_session(db: Session, secret: str = "test_customer_secret_123") -> CustomerSession:
    """Helper to create an active customer session."""
    session = CustomerSession(
        status="ACTIVE",
        session_secret=secret,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def test_product_picked_increments_cart_quantity_and_creates_event(db_session: Session):
    """Test that PRESENT -> ABSENT transition increments quantity and records PRODUCT_PICKED event."""
    seed_initial_data(db_session)
    cust_session = setup_active_session(db_session)

    zone1 = db_session.query(Zone).filter_by(id=1).first()
    product1 = zone1.product
    assert product1 is not None

    # First pickup
    evt1, cart_info1 = record_transition(
        db=db_session,
        zone=zone1,
        from_state="PRESENT",
        to_state="ABSENT",
        confidence=0.96,
        transition_counter=1,
    )

    assert evt1 is not None
    assert evt1.type == "PRODUCT_PICKED"
    assert evt1.status == "PROCESSED"
    assert evt1.session_id == cust_session.id
    assert evt1.product_id == product1.id
    assert abs(evt1.confidence - 0.96) < 1e-3

    assert cart_info1 is not None
    assert cart_info1["action"] == "PICKED"
    assert cart_info1["cart"]["total_quantity"] == 1
    assert cart_info1["cart"]["grand_total"] == product1.unit_price

    # Verify CartItem in DB
    cart_items = db_session.query(CartItem).filter_by(session_id=cust_session.id).all()
    assert len(cart_items) == 1
    assert cart_items[0].product_id == product1.id
    assert cart_items[0].quantity == 1

    # Second pickup of the same product
    evt2, cart_info2 = record_transition(
        db=db_session,
        zone=zone1,
        from_state="PRESENT",
        to_state="ABSENT",
        confidence=0.92,
        transition_counter=2,
    )

    assert evt2 is not None
    assert evt2.status == "PROCESSED"
    assert cart_info2["cart"]["total_quantity"] == 2
    assert cart_info2["cart"]["grand_total"] == product1.unit_price * 2

    db_session.expire_all()
    cart_item = db_session.query(CartItem).filter_by(session_id=cust_session.id).first()
    assert cart_item.quantity == 2


def test_product_returned_decrements_cart_and_deletes_at_zero(db_session: Session):
    """Test that ABSENT -> PRESENT decrements quantity, and removes row at 0 without going negative."""
    seed_initial_data(db_session)
    cust_session = setup_active_session(db_session)
    zone1 = db_session.query(Zone).filter_by(id=1).first()
    product1 = zone1.product

    # Pick 2 items first
    record_transition(db_session, zone1, "PRESENT", "ABSENT", transition_counter=1)
    record_transition(db_session, zone1, "PRESENT", "ABSENT", transition_counter=2)

    cart_before = get_cart_summary(db_session, cust_session.id)
    assert cart_before["total_quantity"] == 2

    # Return 1 item
    evt_ret1, cart_info_ret1 = record_transition(
        db=db_session,
        zone=zone1,
        from_state="ABSENT",
        to_state="PRESENT",
        confidence=0.94,
        transition_counter=3,
    )

    assert evt_ret1 is not None
    assert evt_ret1.type == "PRODUCT_RETURNED"
    assert evt_ret1.status == "PROCESSED"
    assert cart_info_ret1["cart"]["total_quantity"] == 1
    assert cart_info_ret1["cart"]["grand_total"] == product1.unit_price

    # Return second item (drops to 0 -> CartItem deleted)
    evt_ret2, cart_info_ret2 = record_transition(
        db=db_session,
        zone=zone1,
        from_state="ABSENT",
        to_state="PRESENT",
        confidence=0.95,
        transition_counter=4,
    )

    assert evt_ret2.status == "PROCESSED"
    assert cart_info_ret2["cart"]["total_quantity"] == 0
    assert cart_info_ret2["cart"]["grand_total"] == 0
    assert len(cart_info_ret2["cart"]["items"]) == 0

    # Ensure no orphan CartItem rows exist in DB
    remaining_items = db_session.query(CartItem).filter_by(session_id=cust_session.id).all()
    assert len(remaining_items) == 0


def test_duplicate_event_is_idempotent_and_does_not_modify_cart_again(db_session: Session):
    """Test that duplicate transitions with the same event_uid are ignored without altering cart."""
    seed_initial_data(db_session)
    cust_session = setup_active_session(db_session)
    zone1 = db_session.query(Zone).filter_by(id=1).first()

    # First execution with fixed transition sequence
    evt1, cart_info1 = record_transition(
        db=db_session,
        zone=zone1,
        from_state="PRESENT",
        to_state="ABSENT",
        transition_counter=10,
    )
    assert evt1 is not None
    assert cart_info1["cart"]["total_quantity"] == 1

    # Replay same transition with identical event_uid / sequence
    evt1_dup, cart_info1_dup = record_transition(
        db=db_session,
        zone=zone1,
        from_state="PRESENT",
        to_state="ABSENT",
        transition_counter=10,
    )

    # Must return existing event and None cart update (no double count)
    assert evt1_dup.id == evt1.id
    assert cart_info1_dup is None

    # Cart quantity must strictly remain 1
    cart = get_cart_summary(db_session, cust_session.id)
    assert cart["total_quantity"] == 1


def test_transition_without_active_session_is_ignored(db_session: Session):
    """Test that transitions occurring when no customer is in the store are flagged IGNORED_NO_SESSION."""
    seed_initial_data(db_session)
    zone1 = db_session.query(Zone).filter_by(id=1).first()

    # No session in DB
    assert db_session.query(CustomerSession).count() == 0

    evt, cart_info = record_transition(
        db=db_session,
        zone=zone1,
        from_state="PRESENT",
        to_state="ABSENT",
        confidence=0.88,
        transition_counter=1,
    )

    assert evt is not None
    assert evt.type == "PRODUCT_PICKED"
    assert evt.status == "IGNORED_NO_SESSION"
    assert evt.session_id is None
    assert cart_info is None

    # Zero cart items created
    assert db_session.query(CartItem).count() == 0


def test_return_item_not_in_cart_is_ignored_and_never_negative(db_session: Session):
    """Test that returning an item not in cart is marked IGNORED_NOT_IN_CART and never causes negative qty."""
    seed_initial_data(db_session)
    cust_session = setup_active_session(db_session)
    zone2 = db_session.query(Zone).filter_by(id=2).first()

    # Attempt to return item from Zone 2 when cart is empty
    evt, cart_info = record_transition(
        db=db_session,
        zone=zone2,
        from_state="ABSENT",
        to_state="PRESENT",
        confidence=0.91,
        transition_counter=1,
    )

    assert evt is not None
    assert evt.type == "PRODUCT_RETURNED"
    assert evt.status == "IGNORED_NOT_IN_CART"
    assert cart_info is None

    # Verify no cart items created and quantity is never negative
    cart = get_cart_summary(db_session, cust_session.id)
    assert cart["total_quantity"] == 0
    assert cart["grand_total"] == 0


def test_grand_total_calculated_correctly_with_multiple_products(db_session: Session):
    """Test cart calculation with multiple distinct products and varied quantities."""
    seed_initial_data(db_session)
    cust_session = setup_active_session(db_session)

    zones = db_session.query(Zone).order_by(Zone.id).all()
    z1, z2, z3 = zones[0], zones[1], zones[2]

    # Pick 2 of Product 1 (35,000 * 2 = 70,000)
    record_transition(db_session, z1, "PRESENT", "ABSENT", transition_counter=101)
    record_transition(db_session, z1, "PRESENT", "ABSENT", transition_counter=102)

    # Pick 3 of Product 2 (15,000 * 3 = 45,000)
    record_transition(db_session, z2, "PRESENT", "ABSENT", transition_counter=201)
    record_transition(db_session, z2, "PRESENT", "ABSENT", transition_counter=202)
    record_transition(db_session, z2, "PRESENT", "ABSENT", transition_counter=203)

    # Pick 1 of Product 3 (45,000 * 1 = 45,000)
    record_transition(db_session, z3, "PRESENT", "ABSENT", transition_counter=301)

    expected_grand_total = (35000 * 2) + (15000 * 3) + (45000 * 1)  # 160,000
    expected_quantity = 2 + 3 + 1  # 6

    cart = get_cart_summary(db_session, cust_session.id)
    assert cart["total_quantity"] == expected_quantity
    assert cart["grand_total"] == expected_grand_total
    assert len(cart["items"]) == 3


def test_customer_cart_api_and_auth(client: TestClient, db_session: Session):
    """Test GET /api/customer/cart with valid and invalid session secrets."""
    seed_initial_data(db_session)
    secret = "cust_valid_secret_999"
    cust_session = setup_active_session(db_session, secret=secret)
    zone1 = db_session.query(Zone).filter_by(id=1).first()

    # Add item
    record_transition(db_session, zone1, "PRESENT", "ABSENT", transition_counter=1)

    # 1. Valid secret request
    res = client.get(f"/api/customer/cart?secret={secret}")
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == cust_session.id
    assert data["total_quantity"] == 1
    assert data["grand_total"] > 0
    assert len(data["items"]) == 1

    # 2. Invalid secret request
    bad_res = client.get("/api/customer/cart?secret=non_existent_secret")
    assert bad_res.status_code == 404


def test_admin_events_api_and_system_events(client: TestClient, db_session: Session):
    """Test recording system events and querying them via protected GET /api/admin/events."""
    seed_initial_data(db_session)

    # Record miscellaneous system events
    e1 = record_system_event(db_session, "DEVICE_CONNECTED", device_id="tablet_cam_1")
    e2 = record_system_event(db_session, "DEVICE_DISCONNECTED", device_id="tablet_cam_1")

    # Unauthenticated request rejected
    client.cookies.clear()
    unauth = client.get("/api/admin/events")
    assert unauth.status_code == 401

    # Authenticated request
    headers = get_admin_headers(client)
    res = client.get("/api/admin/events?limit=50", headers=headers)
    assert res.status_code == 200
    events = res.json()
    assert len(events) >= 2

    types = [e["type"] for e in events]
    assert "DEVICE_CONNECTED" in types
    assert "DEVICE_DISCONNECTED" in types


def test_persistence_after_db_reload_active_session_cart(db_session: Session):
    """Verify that cart items and totals remain 100% consistent across session reloads."""
    seed_initial_data(db_session)
    cust_session = setup_active_session(db_session, secret="persistence_secret")
    zone1 = db_session.query(Zone).filter_by(id=1).first()

    record_transition(db_session, zone1, "PRESENT", "ABSENT", transition_counter=1)

    # Clear ORM session to simulate restart / fresh connection
    db_session.expire_all()

    # Re-query
    reloaded_cart = get_cart_summary(db_session, cust_session.id)
    assert reloaded_cart["total_quantity"] == 1
    assert reloaded_cart["grand_total"] == zone1.product.unit_price
    assert reloaded_cart["items"][0]["product_id"] == zone1.product_id
