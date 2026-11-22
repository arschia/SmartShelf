"""Server-owned, single-slot university demo: camera -> debounced stock/cart -> WS.

Brand is explicitly assigned by the operator, never guessed by the generic detector.
No payment provider is called. STORE_OPEN is not changed by demo activation.
"""
from __future__ import annotations

import secrets
import time
import asyncio
import json
from typing import Optional

import cv2
from sqlalchemy.orm import Session

from ..models import ShopScenario, Product, Zone, CustomerSession, CartItem, Event, utc_now
from ..vision.bottle_detector import get_bottle_detector
from ..vision.two_reference import is_two_reference, classify_frame, crop_roi, PresenceFeatureError
from ..vision.state_machine import ZoneStateMachine, SlotState
from ..ws import manager
from .event_service import get_cart_summary


def configuration(db):
    return db.get(ShopScenario, 1)


def demo_enabled(db):
    cfg = configuration(db)
    return bool(cfg and cfg.enabled)


def active_customer(db):
    return db.query(CustomerSession).filter_by(status="ACTIVE").order_by(CustomerSession.id).first()


def snapshot(db):
    cfg = configuration(db)
    customer = active_customer(db)
    product = db.get(Product, cfg.product_id) if cfg and cfg.product_id else None
    zone = db.get(Zone, cfg.zone_id) if cfg and cfg.zone_id else None
    try:
        calibrated = bool(zone and is_two_reference(json.loads(zone.ref_full_features or "null"))
                          and is_two_reference(json.loads(zone.ref_empty_features or "null")))
    except (ValueError, TypeError):
        calibrated = False
    return {"enabled": bool(cfg and cfg.enabled), "demo": True,
            "calibrated": calibrated, "vision_mode": "two_reference" if calibrated else "onnx",
            "camera_source": cfg.camera_source if cfg else "browser",
            "zone_id": cfg.zone_id if cfg else None,
            "product_id": cfg.product_id if cfg else None,
            "product_name": product.name if product else None,
            "unit_price": product.unit_price if product else 0,
            "stock_quantity": cfg.stock_quantity if cfg else None,
            "needs_review": bool(cfg and cfg.needs_review),
            "roi": [zone.roi_x,zone.roi_y,zone.roi_w,zone.roi_h] if zone else [0,0,1,1],
            "state": shop_runtime.machine.get_display_state() if shop_runtime.machine else "UNKNOWN",
            "camera_live": shop_runtime.is_fresh(),
            "frames_processed": shop_runtime.processed_frames,
            "session_id": customer.id if customer else None,
            "cart": get_cart_summary(db, customer.id) if customer else None}


class ShopRuntime:
    MAX_GAP = 2.5
    STABLE_SECONDS = 0.4
    MIN_FRAMES = 3

    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.reset()

    def reset(self):
        self.machine = None
        self.generation = None
        self.last_frame = None
        self.processed_frames = 0
        self.source_owner = None
        self.last_sequence = -1
        self.candidate_frames = 0
        self.candidate_session = None
        self.candidate_owner = None
        self.nonce = secrets.token_hex(8)

    def is_fresh(self):
        return self.last_frame is not None and self.clock()-self.last_frame <= self.MAX_GAP

    def break_continuity(self):
        if self.machine:
            self.machine.reset("UNKNOWN")
        self.candidate_frames = 0
        self.candidate_session = None
        self.candidate_owner = None

    def commit(self, db):
        try:
            db.commit()
        except Exception:
            db.rollback()
            self.break_continuity()
            raise

    def accepts(self, cfg, source):
        if not cfg or not cfg.enabled:
            return False
        if cfg.camera_source == "tablet":
            return source == "tablet" or source.startswith("tablet:")
        return source.startswith("browser:")

    def observe(self, db: Session, observation: str, confidence=1., source="tablet", sequence=None):
        cfg = configuration(db)
        if not self.accepts(cfg, source):
            return {"accepted": False}
        now = self.clock()
        if self.generation != cfg.generation:
            self.reset()
            self.generation = cfg.generation
        if self.source_owner != source:
            if self.source_owner and self.is_fresh():
                return {"accepted": False, "reason": "ANOTHER_CAMERA"}
            self.break_continuity()
            self.source_owner = source
            self.last_sequence = -1
        if sequence is not None:
            if sequence <= self.last_sequence:
                return {"accepted": False, "reason": "DUPLICATE_FRAME"}
            self.last_sequence = sequence
        if self.last_frame is not None and now-self.last_frame > self.MAX_GAP:
            self.break_continuity()
        self.last_frame = now
        self.processed_frames += 1
        if not self.machine:
            self.machine = ZoneStateMachine(cfg.zone_id, stable_seconds=self.STABLE_SECONDS, clock=self.clock)
        sm = self.machine
        customer = active_customer(db)
        customer_id = customer.id if customer else None
        previous_candidate = sm.candidate_state
        previous_state = sm.confirmed_state
        if observation not in ("PRESENT", "ABSENT"):
            sm.update("UNKNOWN", now)
            self.candidate_frames = 0
            self.candidate_session = None
            return {"accepted": True, "state": sm.get_display_state(), "events": [], "cart_info": None}
        if observation != previous_candidate:
            self.candidate_frames = 1
            self.candidate_session = customer_id
            self.candidate_owner = cfg.pick_session_id
        else:
            self.candidate_frames += 1
        # A session switch during the observation must not charge/credit the next customer.
        if self.candidate_session != customer_id:
            self.candidate_session = None
        if self.candidate_frames < self.MIN_FRAMES and sm.candidate_state == observation:
            transition = None
        else:
            transition = sm.update(observation, now)
        zone = db.get(Zone, cfg.zone_id)
        if zone:
            zone.state = sm.get_display_state()
            zone.confidence = confidence
        baseline = previous_state == "UNKNOWN" and sm.confirmed_state != "UNKNOWN"
        events, cart_info = [], None
        if baseline or transition:
            quantity = 1 if sm.confirmed_state == "PRESENT" else 0
            old_quantity = cfg.stock_quantity
            product = db.get(Product, cfg.product_id)
            if product:
                product.stock_quantity = max(0, product.stock_quantity + quantity - (old_quantity or 0))
            cfg.stock_quantity = quantity
            event_type = "STOCK_SYNC" if baseline else "PRODUCT_PICKED" if quantity == 0 else "PRODUCT_RETURNED"
            event_status = "BASELINE" if baseline else "STOCK_ONLY"
            event_session = None
            if baseline:
                # A pause/restart is not a purchase. Preserve the last confirmed
                # inventory, and flag an actual change during the interruption.
                if customer_id is not None and old_quantity is not None and old_quantity != quantity:
                    cfg.needs_review = True
                    event_status = "OFFLINE_CHANGE"
                # A change across a blind interval cannot be attributed to a
                # customer. A legacy review flag may also carry a stale owner.
                if old_quantity != quantity:
                    cfg.pick_session_id = None
                elif cfg.needs_review and cfg.pick_session_id is not None:
                    # Older versions could retain ownership through an offline
                    # change. Only restore it for a confirmed, attributed pick.
                    last_change = db.query(Event).filter(
                        Event.zone_id == cfg.zone_id, Event.product_id == cfg.product_id,
                        Event.type.in_(["PRODUCT_PICKED", "PRODUCT_RETURNED", "STOCK_SYNC"]),
                        Event.status != "BASELINE",
                    ).order_by(Event.id.desc()).first()
                    if not (last_change and last_change.type == "PRODUCT_PICKED"
                            and last_change.status == "PROCESSED"
                            and last_change.session_id == cfg.pick_session_id):
                        cfg.pick_session_id = None
            else:
                if quantity == 0:
                    cfg.pick_session_id = None
                    if customer_id is not None and self.candidate_session == customer_id:
                        item = db.query(CartItem).filter_by(session_id=customer_id, product_id=cfg.product_id).first()
                        if item: item.quantity += 1
                        else: db.add(CartItem(session_id=customer_id, product_id=cfg.product_id, quantity=1))
                        cfg.pick_session_id = customer_id
                        event_session, event_status = customer_id, "PROCESSED"
                else:
                    owner = cfg.pick_session_id
                    if owner is not None and owner == customer_id and self.candidate_session == owner and self.candidate_owner == owner:
                        item = db.query(CartItem).filter_by(session_id=owner, product_id=cfg.product_id).first()
                        if item and item.quantity > 0:
                            item.quantity -= 1
                            if item.quantity == 0: db.delete(item)
                            event_session, event_status = owner, "PROCESSED"
                    cfg.pick_session_id = None
            event = Event(event_uid=f"shop_{self.nonce}_{sm.transition_count}", type=event_type,
                          zone_id=cfg.zone_id, product_id=cfg.product_id, session_id=event_session,
                          status=event_status, confidence=round(confidence,3))
            db.add(event)
            self.commit(db)
            events.append({"id": event.id,"event_uid":event.event_uid,"type":event.type,
                           "session_id":event_session,"zone_id":cfg.zone_id,"product_id":cfg.product_id,
                           "product_name":product.name if product else None,"status":event_status,
                           "confidence":event.confidence,"created_at":event.created_at.isoformat()})
            if event_status == "PROCESSED":
                cart_info = {"type":"CART_UPDATED", "action":"PICKED" if quantity == 0 else "RETURNED",
                             "session_id":customer_id,"product_name":product.name if product else "محصول",
                             "cart":get_cart_summary(db,customer_id)}
        else:
            self.commit(db)
        return {"accepted":True,"state":sm.get_display_state(),"events":events,"cart_info":cart_info}

    def classify(self, frame, cfg, zone):
        # A calibrated Windows-local shelf uses the same two-reference occupancy
        # engine as the fixed ZIP. WebRTC is only a preview; camera WSS/HTTPS
        # JPEG frames are the sole source of accounting transitions.
        calibrated = False
        try:
            full = json.loads(zone.ref_full_features or "null")
            empty = json.loads(zone.ref_empty_features or "null")
            if is_two_reference(full) and is_two_reference(empty):
                cropped = crop_roi(frame, [zone.roi_x, zone.roi_y, zone.roi_w, zone.roi_h])
                state, confidence, _ = classify_frame(cropped, full, empty)
                if state != "UNKNOWN":
                    return state, confidence, []
                # A rotated bottle may no longer resemble the full reference.
                # Allow positive model evidence; a missed detection alone must
                # never turn an ambiguous calibrated frame into a purchase.
                calibrated = True
        except (ValueError, TypeError, json.JSONDecodeError, PresenceFeatureError):
            return "UNKNOWN", 0.0, []
        gray = cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        if gray.std() < 3 or cv2.Laplacian(gray,cv2.CV_64F).var() < 5:
            return "UNKNOWN",0.,[]
        result = get_bottle_detector().detect(frame, threshold=0.2)
        x, y, w, h = zone.roi_x, zone.roi_y, zone.roi_w, zone.roi_h
        is_full_frame = (w >= 0.9 and h >= 0.9)
        inside = []
        for detection in result["detections"]:
            x1, y1, x2, y2 = detection["box"]
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            if is_full_frame or (x <= cx <= x + w and y <= cy <= y + h):
                inside.append(detection)
        if len(inside) > 1:
            return "UNKNOWN", 0., result["detections"]
        if inside:
            score = inside[0]["confidence"]
            return ("PRESENT" if score >= 0.35 else "UNKNOWN"), score, result["detections"]
        return "ABSENT", 1.0, result["detections"]


shop_runtime = ShopRuntime()


async def process_shop_frame(frame, db, source, sequence=None):
    cfg = configuration(db)
    if not shop_runtime.accepts(cfg,source):
        return {"accepted":False}
    zone = db.get(Zone,cfg.zone_id)
    if not zone:
        return {"accepted":False}
    # Snapshot generation before releasing the event loop for inference.
    # SQLAlchemy refreshes cfg on expire_all(), so comparing cfg.generation
    # after inference would otherwise compare the new value to itself.
    expected_generation = cfg.generation
    try:
        # ONNX inference is CPU-bound and must not block stop/configure,
        # WebSocket delivery or other frame requests on the event loop.
        observation, confidence, detections = await asyncio.to_thread(
            shop_runtime.classify, frame, cfg, zone
        )
    except Exception:
        observation, confidence, detections = "UNKNOWN",0.,[]
    # The scenario may have been stopped/reconfigured while inference ran.
    # Never commit a stale detection to a newly started scenario.
    db.expire_all()
    latest = configuration(db)
    if not latest or not latest.enabled or latest.generation != expected_generation:
        return {"accepted": False, "reason": "SCENARIO_CHANGED"}
    result = shop_runtime.observe(db,observation,confidence,source,sequence)
    if not result.get("accepted"):
        return result
    result["detections"] = detections
    state = snapshot(db)
    for event in result.get("events",[]):
        await manager.broadcast_to_admins({"type":"EVENT_CREATED","event":event})
    cart_info = result.get("cart_info")
    if cart_info:
        owner = db.get(CustomerSession,cart_info["session_id"])
        if owner:
            await manager.broadcast_to_customer(owner.session_secret,cart_info)
        await manager.broadcast_to_admins(cart_info)
    await manager.broadcast_to_admins({"type":"SHOP_STATE","shop":state})
    await manager.broadcast_to_admins({"type":"ZONES_STATUS","zones":[{"id":cfg.zone_id,"state":result["state"],"confidence":confidence}]})
    result["shop"] = state
    return result
