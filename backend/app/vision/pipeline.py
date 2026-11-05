"""Real-time shelf vision pipeline.

Orchestrates ROI extraction, feature similarity scoring, temporal state machines,
and visual bounding box overlays (Green=PRESENT, Red=ABSENT, Yellow=TRANSITION).
Strictly in-memory with zero disk I/O.
"""
import json
import time
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Zone, utc_now
from ..ws import manager
from .occupancy import extract_features, classify_roi_occupancy, crop_relative_roi
from .state_machine import ZoneStateMachine, SlotState
from .camera_feed import camera_feed
from .two_reference import classify_frame as classify_two_reference, is_two_reference


class VisionPipeline:
    """Shelf vision pipeline managing all slot state machines and overlays."""

    def __init__(self):
        self.state_machines: Dict[int, ZoneStateMachine] = {}
        self.annotated_jpeg: Optional[bytes] = None
        self.last_process_time: float = 0.0
        self.roi_buffers: Dict[int, List[np.ndarray]] = {}
        self.latest_zone_roi_bytes: Dict[int, bytes] = {}
        self.last_recognition_time: Dict[int, float] = {}

    def get_or_create_state_machine(self, zone_id: int, initial_state: str = SlotState.UNKNOWN) -> ZoneStateMachine:
        if zone_id not in self.state_machines:
            self.state_machines[zone_id] = ZoneStateMachine(
                zone_id=zone_id,
                initial_state=initial_state,
                stable_seconds=settings.STABLE_SECONDS,
            )
        return self.state_machines[zone_id]

    def recognize_zone(self, zone: Zone, db: Session) -> Optional[Dict]:
        """Averages recent buffered ROI frames and runs ProductRecognitionEngine without disk I/O."""
        buf = self.roi_buffers.get(zone.id, [])
        if not buf:
            return None

        # 1. Average frames across buffer
        if len(buf) == 1:
            avg_roi = buf[0]
        else:
            avg_roi = np.mean(buf, axis=0).astype(np.uint8)

        # 2. Encode to in-memory JPEG bytes (strictly in-memory, zero disk write)
        success, enc = cv2.imencode(".jpg", avg_roi)
        if not success:
            return None
        roi_bytes = enc.tobytes()
        self.latest_zone_roi_bytes[zone.id] = roi_bytes

        try:
            from ..services.recognition import ProductRecognitionEngine
            engine = ProductRecognitionEngine.get_instance()
            result = engine.identify(roi_bytes, db)

            zone.recognized_product_id = result.get("product_id")
            zone.recognition_status = result.get("status", "UNKNOWN")
            zone.recognition_score = result.get("similarity", 0.0)
            zone.last_recognized_at = utc_now()
            self.last_recognition_time[zone.id] = time.time()
            return result
        except Exception as e:
            # Fail closed: never reuse a stale product identity after a model error.
            zone.recognized_product_id = None
            zone.recognition_status = "UNKNOWN"
            zone.recognition_score = 0.0
            zone.last_recognized_at = utc_now()
            self.last_recognition_time[zone.id] = time.time()
            print(f"[RECOGNITION ERROR] Zone {zone.id} recognition failed: {e}")
            return {"status": "UNKNOWN", "product_id": None, "similarity": 0.0}

    def process_frame(self, frame: np.ndarray, db: Session) -> Tuple[np.ndarray, List[Dict]]:
        """Process incoming video frame through all zone ROIs and render visual overlay."""
        if frame is None or frame.size == 0:
            return frame, []

        h, w = frame.shape[:2]
        annotated_frame = frame.copy()
        zones = db.query(Zone).order_by(Zone.id).all()
        zone_results = []
        db_dirty = False

        for zone in zones:
            sm = self.get_or_create_state_machine(zone.id, initial_state=SlotState.UNKNOWN)

            # 1. Crop ROI using relative coordinates
            roi = crop_relative_roi(frame, zone.roi_x, zone.roi_y, zone.roi_w, zone.roi_h)
            if roi is None or roi.size == 0:
                continue

            # 2. Parse reference features
            ref_full = json.loads(zone.ref_full_features) if zone.ref_full_features else None
            ref_empty = json.loads(zone.ref_empty_features) if zone.ref_empty_features else None

            # 3. Classify with the selected reference engine.
            # New two-reference calibrations use SIFT/ORB + RANSAC; old databases
            # remain compatible with the legacy HSV/thumbnail feature format.
            if is_two_reference(ref_full) and is_two_reference(ref_empty):
                raw_state, conf, _presence_diagnostics = classify_two_reference(
                    roi, full_ref=ref_full, empty_ref=ref_empty
                )
            elif (
                (ref_full and ref_full.get("kind")) or
                (ref_empty and ref_empty.get("kind"))
            ):
                # Mixed/incomplete calibration is never allowed to guess.
                raw_state, conf = SlotState.UNKNOWN, 0.0
            else:
                curr_feats = extract_features(roi)
                raw_state, conf = classify_roi_occupancy(
                    curr_feats,
                    ref_full=ref_full,
                    ref_empty=ref_empty,
                    threshold_present=settings.THRESHOLD_PRESENT,
                    threshold_absent=settings.THRESHOLD_ABSENT,
                    alpha=settings.SIMILARITY_ALPHA,
                )

            # 4. Update temporal state machine
            transition = sm.update(raw_state)
            disp_state = sm.get_display_state()

            # Buffer ROI frames when present for temporal averaging
            if raw_state == SlotState.PRESENT or disp_state == SlotState.PRESENT:
                if zone.id not in self.roi_buffers:
                    self.roi_buffers[zone.id] = []
                self.roi_buffers[zone.id].append(roi.copy())
                if len(self.roi_buffers[zone.id]) > 5:
                    self.roi_buffers[zone.id] = self.roi_buffers[zone.id][-5:]
            elif disp_state == SlotState.ABSENT:
                if zone.id in self.roi_buffers:
                    self.roi_buffers[zone.id].clear()

            # Run visual recognition when newly PRESENT or periodically (every 8s)
            if transition and transition[1] == SlotState.PRESENT:
                self.recognize_zone(zone, db)
                db_dirty = True
            elif disp_state == SlotState.PRESENT and (time.time() - self.last_recognition_time.get(zone.id, 0.0)) > 8.0:
                self.recognize_zone(zone, db)
                db_dirty = True

            # 5. Update DB if state or confidence changed
            if zone.state != disp_state or abs(zone.confidence - conf) > 0.05:
                zone.state = disp_state
                zone.confidence = conf
                db_dirty = True

            # 6. Compute pixel coordinates for visual overlay
            x1 = max(0, min(w - 1, int(round(zone.roi_x * w))))
            y1 = max(0, min(h - 1, int(round(zone.roi_y * h))))
            x2 = max(x1 + 1, min(w, int(round((zone.roi_x + zone.roi_w) * w))))
            y2 = max(y1 + 1, min(h, int(round((zone.roi_y + zone.roi_h) * h))))

            is_mismatch = (
                disp_state == SlotState.PRESENT
                and zone.product_id is not None
                and zone.recognized_product_id is not None
                and zone.product_id != zone.recognized_product_id
                and zone.recognition_status == "RECOGNIZED"
            )
            is_uncertain = (
                disp_state == SlotState.PRESENT
                and zone.recognition_status in ("UNKNOWN", "NEEDS_REVIEW")
            )

            # 7. Colors: Green=PRESENT, Red=ABSENT, Yellow=TRANSITION, Orange=MISMATCH/UNCERTAIN, Gray=UNKNOWN
            if is_mismatch:
                box_color = (0, 140, 255)     # BGR Orange
            elif is_uncertain:
                box_color = (0, 180, 240)     # BGR Amber
            elif disp_state == SlotState.PRESENT:
                box_color = (0, 200, 30)      # BGR Green
            elif disp_state == SlotState.ABSENT:
                box_color = (30, 30, 220)     # BGR Red
            elif disp_state == SlotState.TRANSITION:
                box_color = (0, 215, 255)     # BGR Yellow / Amber
            else:
                box_color = (150, 150, 150)   # BGR Gray

            # Draw bounding box
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), box_color, 2)

            # Draw label banner
            rec_tag = ""
            if zone.recognition_status == "RECOGNIZED" and zone.recognized_product:
                rec_tag = f" [{zone.recognized_product.sku}]"
            elif is_mismatch:
                rec_tag = " [MISMATCH]"
            elif is_uncertain:
                rec_tag = " [UNCERTAIN]"

            label = f"{zone.name.split('(')[0].strip()}: {disp_state}{rec_tag} ({int(conf * 100)}%)"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            banner_y1 = max(0, y1 - th - 8)
            banner_y2 = y1
            cv2.rectangle(annotated_frame, (x1, banner_y1), (x1 + tw + 10, banner_y2), box_color, -1)
            cv2.putText(
                annotated_frame,
                label,
                (x1 + 5, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (20, 20, 20),
                1,
                cv2.LINE_AA,
            )

            zone_results.append({
                "id": zone.id,
                "name": zone.name,
                "state": disp_state,
                "confidence": conf,
                "raw_observation": raw_state,
                "has_ref_full": ref_full is not None,
                "has_ref_empty": ref_empty is not None,
                "transition": transition,
                "transition_count": sm.transition_count,
                "product_id": zone.product_id,
                "product_name": zone.product.name if zone.product else None,
                "product_sku": zone.product.sku if zone.product else None,
                "recognized_product_id": zone.recognized_product_id,
                "recognized_product_name": zone.recognized_product.name if zone.recognized_product else None,
                "recognized_product_sku": zone.recognized_product.sku if zone.recognized_product else None,
                "recognition_status": zone.recognition_status,
                "recognition_score": zone.recognition_score,
                "is_mismatch": is_mismatch,
            })

        if db_dirty:
            db.commit()

        # Update in-memory annotated JPEG buffer
        success, buf = cv2.imencode(".jpg", annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if success:
            self.annotated_jpeg = buf.tobytes()

        return annotated_frame, zone_results

    def get_annotated_jpeg(self) -> Optional[bytes]:
        """Returns the latest frame with visual bounding box overlay."""
        return self.annotated_jpeg


pipeline = VisionPipeline()
