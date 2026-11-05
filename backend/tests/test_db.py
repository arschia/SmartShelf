from datetime import datetime, timedelta, timezone
import uuid

from backend.app.models import (
    utc_now,
    Product,
    Zone,
    EntryToken,
    CustomerSession,
    CartItem,
    Event,
    Invoice,
    InvoiceLine,
    Device,
)


def test_product_model(db_session):
    product = Product(
        sku="TEST-SKU-1",
        name="Test Item",
        description="A sample test item",
        image_path="/static/test.png",
        unit_price=25000,
        is_active=True,
    )
    db_session.add(product)
    db_session.commit()

    saved = db_session.query(Product).filter_by(sku="TEST-SKU-1").first()
    assert saved is not None
    assert saved.name == "Test Item"
    assert saved.unit_price == 25000
    assert saved.is_active is True


def test_zone_model(db_session):
    product = Product(
        sku="TEST-SKU-ZONE",
        name="Zone Product",
        unit_price=10000,
    )
    db_session.add(product)
    db_session.commit()

    zone = Zone(
        name="Slot 1",
        product_id=product.id,
        roi_x=10,
        roi_y=20,
        roi_w=100,
        roi_h=120,
        state="FULL",
        confidence=0.98,
    )
    db_session.add(zone)
    db_session.commit()

    saved_zone = db_session.query(Zone).filter_by(name="Slot 1").first()
    assert saved_zone is not None
    assert saved_zone.product.name == "Zone Product"
    assert saved_zone.state == "FULL"
    assert saved_zone.confidence == 0.98


def test_entry_token_model(db_session):
    now = utc_now()
    token = EntryToken(
        token="tok_1234567890",
        created_at=now,
        expires_at=now + timedelta(seconds=30),
    )
    db_session.add(token)
    db_session.commit()

    saved = db_session.query(EntryToken).filter_by(token="tok_1234567890").first()
    assert saved is not None
    assert saved.used_at is None
    assert saved.expires_at > now


def test_session_and_cart_item_models(db_session):
    session = CustomerSession(
        status="ACTIVE",
        session_secret="sec_secret_123",
    )
    product = Product(
        sku="PROD-CART",
        name="Cart Item Product",
        unit_price=50000,
    )
    db_session.add_all([session, product])
    db_session.commit()

    cart_item = CartItem(
        session_id=session.id,
        product_id=product.id,
        quantity=2,
    )
    db_session.add(cart_item)
    db_session.commit()

    saved_session = db_session.query(CustomerSession).filter_by(session_secret="sec_secret_123").first()
    assert saved_session is not None
    assert len(saved_session.cart_items) == 1
    assert saved_session.cart_items[0].product.name == "Cart Item Product"
    assert saved_session.cart_items[0].quantity == 2


def test_invoice_and_lines_models(db_session):
    session = CustomerSession(
        status="CLOSED",
        exit_reason="CHECKOUT",
        session_secret="sec_invoice_123",
    )
    db_session.add(session)
    db_session.commit()

    invoice = Invoice(
        session_id=session.id,
        total=70000,
    )
    db_session.add(invoice)
    db_session.commit()

    line = InvoiceLine(
        invoice_id=invoice.id,
        product_name="Chocolate Milk",
        unit_price=35000,
        quantity=2,
        line_total=70000,
    )
    db_session.add(line)
    db_session.commit()

    saved_invoice = db_session.query(Invoice).filter_by(session_id=session.id).first()
    assert saved_invoice is not None
    assert saved_invoice.total == 70000
    assert len(saved_invoice.lines) == 1
    assert saved_invoice.lines[0].product_name == "Chocolate Milk"


def test_event_and_device_models(db_session):
    device = Device(
        device_id="cam_tablet_01",
        role="CAMERA",
        is_online=True,
    )
    db_session.add(device)
    db_session.commit()

    event = Event(
        event_uid=str(uuid.uuid4()),
        type="ITEM_PICKED",
        device_id=device.device_id,
        confidence=0.95,
        status="PROCESSED",
    )
    db_session.add(event)
    db_session.commit()

    saved_event = db_session.query(Event).filter_by(device_id="cam_tablet_01").first()
    assert saved_event is not None
    assert saved_event.type == "ITEM_PICKED"

    saved_device = db_session.query(Device).filter_by(device_id="cam_tablet_01").first()
    assert saved_device.is_online is True
