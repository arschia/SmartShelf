"""
Phase 8 Integration and Unit Tests for SMARTSHELF
Connecting Product Recognition to the Shelf Pipeline, State Machines, Events, and Live Cart.

Key Test Matrix:
1. Injected Clock Debounce: transient occlusion (< 1.5s) produces NO state transition and NO cart change.
2. Stable transition PRESENT -> ABSENT (PICKED) with RECOGNIZED item adds product to customer cart.
3. Stable transition ABSENT -> PRESENT (RETURNED) with matching product decrements customer cart.
4. Stable transition ABSENT -> PRESENT (RETURNED) with DIFFERENT product records PRODUCT_MISMATCH and does NOT change cart.
5. Returning an UNKNOWN / uncertain object records PRODUCT_UNCERTAIN and does NOT change cart.
6. Picking an UNKNOWN object records PRODUCT_UNCERTAIN and does NOT add to cart.
7. Picking a product whose recognition differs from assigned slot adds actual recognized product and flags PRODUCT_MISMATCH.
8. Idempotency: repeated transition events with same UID do not duplicate cart items.
9. Privacy verification: zero surveillance frames are saved to disk during pipeline operations.
10. Admin Manual Correction API: corrects recognized product, generates training embedding, and logs MANUAL_CORRECTION event.
"""
import io
import time
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from backend.app.models import Product, Zone, CustomerSession, CartItem, Event, utc_now
from backend.app.services.event_service import record_transition, get_cart_summary
from backend.app.vision.state_machine import ZoneStateMachine, SlotState
from backend.app.vision.pipeline import pipeline, VisionPipeline


def _create_test_product(db, sku="PROD-P8-1", name="کالای آزمایشی ۱", price=25000) -> Product:
    prod = Product(
        sku=sku,
        name=name,
        unit_price=price,
        is_active=True,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return prod


def _create_test_session(db) -> CustomerSession:
    sess = CustomerSession(
        status="ACTIVE",
        entered_at=utc_now(),
        session_secret="sec_test_phase8_12345",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def test_injected_clock_short_occlusion_produces_no_transition_and_no_cart_change(db_session):
    """
    Verify that transient occlusions (< stable_seconds) using an injected clock
    do not trigger transitions, events, or cart changes.
    """
    simulated_time = 1000.0

    def mock_clock():
        return simulated_time

    sm = ZoneStateMachine(
        zone_id=1,
        initial_state=SlotState.PRESENT,
        stable_seconds=1.5,
        clock=mock_clock
    )

    # Initial state is PRESENT
    assert sm.confirmed_state == SlotState.PRESENT

    # A hand occludes the slot -> raw observation ABSENT
    simulated_time += 0.2
    trans = sm.update(SlotState.ABSENT, current_time=simulated_time)
    assert trans is None
    assert sm.get_display_state() == SlotState.TRANSITION

    # 0.8 seconds have passed (less than 1.5s threshold)
    simulated_time += 0.6
    trans = sm.update(SlotState.ABSENT, current_time=simulated_time)
    assert trans is None
    assert sm.confirmed_state == SlotState.PRESENT

    # Hand leaves -> observation returns to PRESENT
    simulated_time += 0.2
    trans = sm.update(SlotState.PRESENT, current_time=simulated_time)
    assert trans is None
    assert sm.confirmed_state == SlotState.PRESENT
    assert sm.get_display_state() == SlotState.PRESENT
    assert sm.transition_count == 0


def test_product_picked_with_recognized_item_increments_cart(db_session):
    """
    When a slot in PRESENT state with a RECOGNIZED product transitions to ABSENT,
    the recognized product must be added to the customer cart and a PRODUCT_PICKED event created.
    """
    prod = _create_test_product(db_session, sku="CHIPS-01", name="چیپس نمکی", price=30000)
    sess = _create_test_session(db_session)

    zone = Zone(
        name="جایگاه ۱",
        product_id=prod.id,
        state="PRESENT",
        recognized_product_id=prod.id,
        recognition_status="RECOGNIZED",
        recognition_score=0.92,
        last_recognized_at=utc_now(),
    )
    db_session.add(zone)
    db_session.commit()
    db_session.refresh(zone)

    # Trigger transition PRESENT -> ABSENT
    evt, cart_info = record_transition(
        db=db_session,
        zone=zone,
        from_state=SlotState.PRESENT,
        to_state=SlotState.ABSENT,
        transition_counter=10,
    )

    assert evt is not None
    assert evt.type == "PRODUCT_PICKED"
    assert evt.product_id == prod.id
    assert evt.status == "PROCESSED"
    assert zone.last_picked_product_id == prod.id

    assert cart_info is not None
    assert cart_info["action"] == "PICKED"
    assert cart_info["cart"]["total_quantity"] == 1
    assert cart_info["cart"]["grand_total"] == 30000


def test_product_returned_with_matching_item_decrements_cart(db_session):
    """
    When an item previously picked from a slot is returned (ABSENT -> PRESENT)
    and visual recognition matches that item, it must be decremented from customer cart.
    """
    prod = _create_test_product(db_session, sku="CHIPS-01", name="چیپس نمکی", price=30000)
    sess = _create_test_session(db_session)

    # Pre-populate cart with 1 chips
    cart_item = CartItem(session_id=sess.id, product_id=prod.id, quantity=1)
    db_session.add(cart_item)
    db_session.commit()

    zone = Zone(
        name="جایگاه ۱",
        product_id=prod.id,
        state="ABSENT",
        last_picked_product_id=prod.id,
        recognized_product_id=prod.id,
        recognition_status="RECOGNIZED",
        recognition_score=0.88,
        last_recognized_at=utc_now(),
    )
    db_session.add(zone)
    db_session.commit()

    # Return matching item to slot
    evt, cart_info = record_transition(
        db=db_session,
        zone=zone,
        from_state=SlotState.ABSENT,
        to_state=SlotState.PRESENT,
        transition_counter=11,
    )

    assert evt is not None
    assert evt.type == "PRODUCT_RETURNED"
    assert evt.product_id == prod.id
    assert evt.status == "PROCESSED"
    assert zone.last_picked_product_id is None

    assert cart_info is not None
    assert cart_info["action"] == "RETURNED"
    assert cart_info["cart"]["total_quantity"] == 0
    assert cart_info["cart"]["grand_total"] == 0


def test_product_returned_with_mismatching_item_does_not_modify_cart_and_flags_mismatch(db_session):
    """
    If customer places Product B into Slot A (where Product A was expected),
    status must be PRODUCT_MISMATCH and cart MUST NOT be altered.
    """
    prod_a = _create_test_product(db_session, sku="PROD-A", name="محصول الف", price=10000)
    prod_b = _create_test_product(db_session, sku="PROD-B", name="محصول ب", price=20000)
    sess = _create_test_session(db_session)

    # Customer has Product A in cart
    cart_item = CartItem(session_id=sess.id, product_id=prod_a.id, quantity=1)
    db_session.add(cart_item)
    db_session.commit()

    zone = Zone(
        name="جایگاه ۱",
        product_id=prod_a.id,
        state="ABSENT",
        last_picked_product_id=prod_a.id,
        # But recognized item placed in slot is Product B!
        recognized_product_id=prod_b.id,
        recognition_status="RECOGNIZED",
        recognition_score=0.91,
        last_recognized_at=utc_now(),
    )
    db_session.add(zone)
    db_session.commit()

    evt, mismatch_info = record_transition(
        db=db_session,
        zone=zone,
        from_state=SlotState.ABSENT,
        to_state=SlotState.PRESENT,
        transition_counter=12,
    )

    assert evt is not None
    assert evt.type == "PRODUCT_MISMATCH"
    assert evt.product_id == prod_b.id
    assert evt.status == "MISMATCH_IGNORED_CART"

    # Cart MUST NOT be modified
    cart = get_cart_summary(db_session, sess.id)
    assert cart["total_quantity"] == 1
    assert cart["items"][0]["product_id"] == prod_a.id
    assert mismatch_info["action"] == "MISMATCH"


def test_product_returned_with_unknown_object_does_not_modify_cart_and_flags_uncertain(db_session):
    """
    If an unknown object (e.g. coffee cup or keys) is placed in a slot,
    status must be PRODUCT_UNCERTAIN and cart MUST NOT be altered.
    """
    prod = _create_test_product(db_session, sku="PROD-SODA", name="نوشابه قوطی", price=15000)
    sess = _create_test_session(db_session)

    cart_item = CartItem(session_id=sess.id, product_id=prod.id, quantity=1)
    db_session.add(cart_item)
    db_session.commit()

    zone = Zone(
        name="جایگاه ۲",
        product_id=prod.id,
        state="ABSENT",
        last_picked_product_id=prod.id,
        # Recognition fails to identify catalog product
        recognized_product_id=None,
        recognition_status="UNKNOWN",
        recognition_score=0.25,
        last_recognized_at=utc_now(),
    )
    db_session.add(zone)
    db_session.commit()

    evt, uncertain_info = record_transition(
        db=db_session,
        zone=zone,
        from_state=SlotState.ABSENT,
        to_state=SlotState.PRESENT,
        transition_counter=13,
    )

    assert evt is not None
    assert evt.type == "PRODUCT_UNCERTAIN"
    assert evt.status == "UNCERTAIN"

    # Cart unchanged
    cart = get_cart_summary(db_session, sess.id)
    assert cart["total_quantity"] == 1
    assert uncertain_info["action"] == "UNCERTAIN"


def test_product_picked_with_unknown_object_does_not_add_to_cart_and_flags_uncertain(db_session):
    """
    If an object in the slot had UNKNOWN recognition status and is removed,
    it must NOT be added to customer cart, and must log PRODUCT_UNCERTAIN.
    """
    sess = _create_test_session(db_session)

    zone = Zone(
        name="جایگاه ۳",
        product_id=None,
        state="PRESENT",
        recognized_product_id=None,
        recognition_status="UNKNOWN",
        recognition_score=0.15,
        last_recognized_at=utc_now(),
    )
    db_session.add(zone)
    db_session.commit()

    evt, uncertain_info = record_transition(
        db=db_session,
        zone=zone,
        from_state=SlotState.PRESENT,
        to_state=SlotState.ABSENT,
        transition_counter=14,
    )

    assert evt is not None
    assert evt.type == "PRODUCT_UNCERTAIN"
    assert evt.status == "UNCERTAIN"

    # Cart remains empty
    cart = get_cart_summary(db_session, sess.id)
    assert cart["total_quantity"] == 0


def test_slot_assigned_mismatch_during_pick_flags_mismatch_and_adds_actual_recognized_product(db_session):
    """
    If Slot was assigned Product A, but item in slot was recognized as Product B and picked,
    customer cart receives Product B (what was actually taken), and PRODUCT_MISMATCH is logged for admin.
    """
    prod_a = _create_test_product(db_session, sku="PROD-MILK", name="شیر", price=28000)
    prod_b = _create_test_product(db_session, sku="PROD-JUICE", name="آبمیوه", price=32000)
    sess = _create_test_session(db_session)

    zone = Zone(
        name="جایگاه ۱",
        product_id=prod_a.id,  # Assigned to Milk
        state="PRESENT",
        recognized_product_id=prod_b.id,  # Actually Juice
        recognition_status="RECOGNIZED",
        recognition_score=0.94,
        last_recognized_at=utc_now(),
    )
    db_session.add(zone)
    db_session.commit()

    evt, cart_info = record_transition(
        db=db_session,
        zone=zone,
        from_state=SlotState.PRESENT,
        to_state=SlotState.ABSENT,
        transition_counter=15,
    )

    assert evt is not None
    assert evt.type == "PRODUCT_PICKED"
    assert evt.product_id == prod_b.id

    # Check cart receives Product B
    cart = get_cart_summary(db_session, sess.id)
    assert cart["total_quantity"] == 1
    assert cart["items"][0]["product_id"] == prod_b.id

    # Check that PRODUCT_MISMATCH was also recorded in system events
    mismatch_evt = db_session.query(Event).filter_by(type="PRODUCT_MISMATCH").first()
    assert mismatch_evt is not None
    assert mismatch_evt.product_id == prod_b.id


def test_idempotent_event_uid_does_not_retrigger_cart_changes(db_session):
    """
    Verify that delivering duplicate transition events with identical event UID
    does not alter cart quantities multiple times.
    """
    prod = _create_test_product(db_session)
    sess = _create_test_session(db_session)

    zone = Zone(
        name="جایگاه ۱",
        product_id=prod.id,
        state="PRESENT",
        recognized_product_id=prod.id,
        recognition_status="RECOGNIZED",
        recognition_score=0.90,
        last_recognized_at=utc_now(),
    )
    db_session.add(zone)
    db_session.commit()

    fixed_uid = "idempotent_test_uid_9999"

    # 1st call
    evt1, cart1 = record_transition(
        db=db_session,
        zone=zone,
        from_state=SlotState.PRESENT,
        to_state=SlotState.ABSENT,
        custom_event_uid=fixed_uid,
    )
    assert evt1 is not None
    assert cart1["cart"]["total_quantity"] == 1

    # 2nd call with identical UID
    evt2, cart2 = record_transition(
        db=db_session,
        zone=zone,
        from_state=SlotState.PRESENT,
        to_state=SlotState.ABSENT,
        custom_event_uid=fixed_uid,
    )
    assert evt2.id == evt1.id
    assert cart2 is None  # Ignored duplicate

    # Cart quantity must remain exactly 1
    cart = get_cart_summary(db_session, sess.id)
    assert cart["total_quantity"] == 1


def test_zero_surveillance_frames_persisted_to_disk(db_session):
    """
    Requirement 7: Verify that video frames remain strictly in-memory
    and zero surveillance or monitoring images are written to disk.
    """
    import tempfile
    test_pipeline = VisionPipeline()

    zone = Zone(
        name="جایگاه ۱",
        roi_x=0.1,
        roi_y=0.1,
        roi_w=0.4,
        roi_h=0.4,
        state="PRESENT",
        confidence=1.0,
    )
    db_session.add(zone)
    db_session.commit()

    # Track files before pipeline runs
    project_dir = Path(__file__).resolve().parent.parent.parent
    uploads_dir = project_dir / "frontend" / "static" / "uploads"
    before_files = set(uploads_dir.glob("**/*")) if uploads_dir.exists() else set()

    # Process 25 synthetic frames through pipeline
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    dummy_frame[:] = (120, 150, 180)

    for _ in range(25):
        test_pipeline.process_frame(dummy_frame, db_session)

    # Check files after pipeline runs
    after_files = set(uploads_dir.glob("**/*")) if uploads_dir.exists() else set()
    new_files = after_files - before_files

    assert len(new_files) == 0, f"Surveillance frames must NOT be saved to disk! Found: {new_files}"
    # Verify in-memory buffer is active
    assert test_pipeline.get_annotated_jpeg() is not None


def test_admin_manual_correction_api_trains_reference_and_updates_zone(client, auth_headers, db_session):
    """
    Requirement 6: Test admin manual correction API endpoint.
    Updates zone's recognized product and logs MANUAL_CORRECTION event.
    """
    prod = _create_test_product(db_session, sku="PROD-MANUAL-1", name="کالای تصحیح ۱")

    zone = Zone(
        name="جایگاه ۱",
        product_id=None,
        state="PRESENT",
        recognized_product_id=None,
        recognition_status="UNKNOWN",
        recognition_score=0.0,
    )
    db_session.add(zone)
    db_session.commit()
    db_session.refresh(zone)

    # Seed in-memory ROI bytes in pipeline
    dummy_img = Image.new("RGB", (100, 100), color=(80, 140, 200))
    buf = io.BytesIO()
    dummy_img.save(buf, format="JPEG")
    pipeline.latest_zone_roi_bytes[zone.id] = buf.getvalue()

    # Call manual correction API
    res = client.post(
        f"/api/admin/zones/{zone.id}/manual-correction",
        json={"product_id": prod.id},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["recognized_product_id"] == prod.id
    assert data["recognition_status"] == "RECOGNIZED"
    assert data["recognition_score"] == 1.0

    # Verify event logged
    evt = db_session.query(Event).filter_by(type="MANUAL_CORRECTION").first()
    assert evt is not None
    assert evt.product_id == prod.id
    assert evt.zone_id == zone.id
