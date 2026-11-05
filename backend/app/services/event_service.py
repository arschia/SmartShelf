"""Event and Cart Management Service for SMARTSHELF.

Converts confirmed vision transitions and system occurrences into persistent,
idempotent events and applies business rules to customer shopping carts.
"""
import secrets

# Unique per process; preserves idempotency for a repeated sequence in this process.
_PROCESS_EVENT_NONCE = secrets.token_hex(8)
from typing import Dict, Optional, Tuple
from sqlalchemy.orm import Session

from ..models import CustomerSession, CartItem, Event, Zone, Product, utc_now
from ..vision.state_machine import SlotState
from ..config import settings


def get_cart_summary(db: Session, session_id: int) -> dict:
    """Calculate and return live cart items, quantities, and grand total."""
    items = (
        db.query(CartItem)
        .filter(CartItem.session_id == session_id)
        .order_by(CartItem.id.asc())
        .all()
    )

    item_list = []
    grand_total = 0
    total_quantity = 0

    for item in items:
        p = item.product
        unit_price = p.unit_price if p else 0
        line_total = unit_price * item.quantity
        grand_total += line_total
        total_quantity += item.quantity

        item_list.append({
            "id": item.id,
            "product_id": item.product_id,
            "product_name": p.name if p else "محصول نامشخص",
            "sku": p.sku if p else "",
            "image_path": p.image_path if p else None,
            "unit_price": unit_price,
            "quantity": item.quantity,
            "line_total": line_total,
        })

    return {
        "session_id": session_id,
        "items": item_list,
        "total_quantity": total_quantity,
        "grand_total": grand_total,
    }


def record_transition(
    db: Session,
    zone: Zone,
    from_state: str,
    to_state: str,
    confidence: float = 1.0,
    transition_counter: int = 1,
    custom_event_uid: Optional[str] = None,
) -> Tuple[Optional[Event], Optional[dict]]:
    """Convert a confirmed shelf slot transition into a persistent Event and update cart.

    Transitions:
        PRESENT -> ABSENT : PRODUCT_PICKED (or PRODUCT_UNCERTAIN if recognition is UNKNOWN/NEEDS_REVIEW)
        ABSENT -> PRESENT : PRODUCT_RETURNED (or PRODUCT_MISMATCH / PRODUCT_UNCERTAIN)

    Returns:
        (Event, cart_notification_payload or None)
    """
    from_norm = SlotState.normalize(from_state)
    to_norm = SlotState.normalize(to_state)

    if from_norm == SlotState.PRESENT and to_norm == SlotState.ABSENT:
        event_type = "PRODUCT_PICKED"
        action = "PICKED"
    elif from_norm == SlotState.ABSENT and to_norm == SlotState.PRESENT:
        event_type = "PRODUCT_RETURNED"
        action = "RETURNED"
    else:
        return None, None

    # Deterministic or specified event UID for idempotency
    event_uid = custom_event_uid or f"trans_{_PROCESS_EVENT_NONCE}_z{zone.id}_seq{transition_counter}"

    # 1. Idempotency Check: if event_uid already processed, ignore duplicate
    existing = db.query(Event).filter_by(event_uid=event_uid).first()
    if existing:
        return existing, None

    # In closed/calibration mode, keep the observation but never bill a customer.
    if not settings.STORE_OPEN:
        event = Event(
            event_uid=event_uid,
            type=event_type,
            session_id=None,
            zone_id=zone.id,
            product_id=zone.product_id,
            confidence=round(confidence, 3),
            status="OBSERVED_STORE_CLOSED",
            created_at=utc_now(),
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event, None

    # 2. Check for an active customer session
    active_session = (
        db.query(CustomerSession)
        .filter_by(status="ACTIVE")
        .order_by(CustomerSession.id.desc())
        .first()
    )

    now = utc_now()

    # Determine effective recognition state
    is_vision_active = (
        zone.last_recognized_at is not None
        or zone.recognized_product_id is not None
        or zone.recognition_status != "UNKNOWN"
    )
    if is_vision_active:
        rec_status = zone.recognition_status or "UNKNOWN"
        rec_product_id = zone.recognized_product_id
    else:
        # Legacy fallback when vision recognition has not run on this slot
        rec_status = "RECOGNIZED" if zone.product_id else "UNKNOWN"
        rec_product_id = zone.product_id

    assigned_product_id = zone.product_id

    # -------------------------------------------------------------
    # CASE 1: PICKED (PRESENT -> ABSENT)
    # -------------------------------------------------------------
    if event_type == "PRODUCT_PICKED":
        # Check if recognition is uncertain
        if rec_status in ("UNKNOWN", "NEEDS_REVIEW") or not rec_product_id:
            # Rule 2: UNKNOWN or NEEDS_REVIEW -> record PRODUCT_UNCERTAIN, no cart update
            event = Event(
                event_uid=event_uid,
                type="PRODUCT_UNCERTAIN",
                session_id=active_session.id if active_session else None,
                zone_id=zone.id,
                product_id=rec_product_id or assigned_product_id,
                confidence=round(confidence, 3),
                status="UNCERTAIN",
                created_at=now,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            uncertain_info = {
                "session_secret": active_session.session_secret if active_session else None,
                "session_id": active_session.id if active_session else None,
                "action": "UNCERTAIN",
                "type": "PRODUCT_UNCERTAIN",
                "product_name": "محصول نامشخص",
                "zone_id": zone.id,
                "cart": get_cart_summary(db, active_session.id) if active_session else None,
            }
            return event, uncertain_info

        # Here: rec_status == "RECOGNIZED" and rec_product_id is valid
        # Save last picked product on zone for subsequent return matching
        zone.last_picked_product_id = rec_product_id
        db.flush()

        # If no active session exists, record event as IGNORED_NO_SESSION
        if not active_session:
            event = Event(
                event_uid=event_uid,
                type=event_type,
                session_id=None,
                zone_id=zone.id,
                product_id=rec_product_id,
                confidence=round(confidence, 3),
                status="IGNORED_NO_SESSION",
                created_at=now,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            return event, None

        session_id = active_session.id

        # Add to customer cart
        cart_item = (
            db.query(CartItem)
            .filter_by(session_id=session_id, product_id=rec_product_id)
            .first()
        )
        if cart_item:
            cart_item.quantity += 1
        else:
            cart_item = CartItem(
                session_id=session_id,
                product_id=rec_product_id,
                quantity=1,
            )
            db.add(cart_item)

        # Record PRODUCT_PICKED event
        event = Event(
            event_uid=event_uid,
            type=event_type,
            session_id=session_id,
            zone_id=zone.id,
            product_id=rec_product_id,
            confidence=round(confidence, 3),
            status="PROCESSED",
            created_at=now,
        )
        db.add(event)

        # If recognized product does not match assigned slot product, flag PRODUCT_MISMATCH
        if assigned_product_id and rec_product_id != assigned_product_id:
            mismatch_event = Event(
                event_uid=f"mismatch_pick_z{zone.id}_{event_uid}",
                type="PRODUCT_MISMATCH",
                session_id=session_id,
                zone_id=zone.id,
                product_id=rec_product_id,
                confidence=round(confidence, 3),
                status="FLAGGED_MISMATCH",
                created_at=now,
            )
            db.add(mismatch_event)

        db.commit()
        db.refresh(event)

        picked_prod = db.query(Product).filter_by(id=rec_product_id).first()
        cart_data = get_cart_summary(db, session_id)
        cart_info = {
            "session_secret": active_session.session_secret,
            "session_id": session_id,
            "action": action,
            "product_name": picked_prod.name if picked_prod else "محصول",
            "cart": cart_data,
        }
        return event, cart_info

    # -------------------------------------------------------------
    # CASE 2: RETURNED (ABSENT -> PRESENT)
    # -------------------------------------------------------------
    elif event_type == "PRODUCT_RETURNED":
        expected_product_id = zone.last_picked_product_id or assigned_product_id

        # Check if returned item is UNKNOWN or NEEDS_REVIEW
        if rec_status in ("UNKNOWN", "NEEDS_REVIEW") or not rec_product_id:
            # Rule 2: UNKNOWN or NEEDS_REVIEW -> record PRODUCT_UNCERTAIN, no cart update
            event = Event(
                event_uid=event_uid,
                type="PRODUCT_UNCERTAIN",
                session_id=active_session.id if active_session else None,
                zone_id=zone.id,
                product_id=rec_product_id or expected_product_id,
                confidence=round(confidence, 3),
                status="UNCERTAIN",
                created_at=now,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            uncertain_info = {
                "session_secret": active_session.session_secret if active_session else None,
                "session_id": active_session.id if active_session else None,
                "action": "UNCERTAIN",
                "type": "PRODUCT_UNCERTAIN",
                "product_name": "شیء نامشخص",
                "zone_id": zone.id,
                "cart": get_cart_summary(db, active_session.id) if active_session else None,
            }
            return event, uncertain_info

        # Check if returned product does NOT match previous product
        # Rule 3: Different product returned -> PRODUCT_MISMATCH, do not change cart
        if expected_product_id and rec_product_id != expected_product_id:
            event = Event(
                event_uid=event_uid,
                type="PRODUCT_MISMATCH",
                session_id=active_session.id if active_session else None,
                zone_id=zone.id,
                product_id=rec_product_id,
                confidence=round(confidence, 3),
                status="MISMATCH_IGNORED_CART",
                created_at=now,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            mismatch_info = {
                "session_secret": active_session.session_secret if active_session else None,
                "session_id": active_session.id if active_session else None,
                "action": "MISMATCH",
                "type": "PRODUCT_MISMATCH",
                "product_name": "محصول نامنطبق",
                "zone_id": zone.id,
                "cart": get_cart_summary(db, active_session.id) if active_session else None,
            }
            return event, mismatch_info

        # Product matches! Clear last_picked_product_id
        zone.last_picked_product_id = None
        db.flush()

        # If no active session exists, record event as IGNORED_NO_SESSION
        if not active_session:
            event = Event(
                event_uid=event_uid,
                type=event_type,
                session_id=None,
                zone_id=zone.id,
                product_id=rec_product_id,
                confidence=round(confidence, 3),
                status="IGNORED_NO_SESSION",
                created_at=now,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            return event, None

        session_id = active_session.id
        status = "PROCESSED"
        cart_modified = False

        # Decrement quantity from cart
        cart_item = (
            db.query(CartItem)
            .filter_by(session_id=session_id, product_id=rec_product_id)
            .first()
        )
        if cart_item and cart_item.quantity > 0:
            cart_item.quantity -= 1
            if cart_item.quantity == 0:
                db.delete(cart_item)
            cart_modified = True
            status = "PROCESSED"
        else:
            status = "IGNORED_NOT_IN_CART"

        event = Event(
            event_uid=event_uid,
            type=event_type,
            session_id=session_id,
            zone_id=zone.id,
            product_id=rec_product_id,
            confidence=round(confidence, 3),
            status=status,
            created_at=now,
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        cart_info = None
        if cart_modified:
            cart_data = get_cart_summary(db, session_id)
            returned_prod = db.query(Product).filter_by(id=rec_product_id).first()
            cart_info = {
                "session_secret": active_session.session_secret,
                "session_id": session_id,
                "action": action,
                "product_name": returned_prod.name if returned_prod else "محصول",
                "cart": cart_data,
            }
        return event, cart_info


def record_system_event(
    db: Session,
    event_type: str,
    session_id: Optional[int] = None,
    device_id: Optional[str] = None,
    zone_id: Optional[int] = None,
    product_id: Optional[int] = None,
    confidence: float = 1.0,
    status: str = "PROCESSED",
    event_uid: Optional[str] = None,
) -> Event:
    """Record an operational system event (DEVICE_CONNECTED, CUSTOMER_ENTERED, etc.)."""
    uid = event_uid or secrets.token_hex(16)
    event = Event(
        event_uid=uid,
        type=event_type,
        session_id=session_id,
        device_id=device_id,
        zone_id=zone_id,
        product_id=product_id,
        confidence=round(confidence, 3),
        status=status,
        created_at=utc_now(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
