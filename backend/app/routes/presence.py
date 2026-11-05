
"""Authenticated API for two-reference shelf presence calibration and testing."""
from __future__ import annotations

import base64
import binascii
import json
import time
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..config import settings
from ..models import Zone
from ..services.auth import get_current_admin
from ..vision.pipeline import pipeline
from ..vision.state_machine import SlotState, ZoneStateMachine
from ..vision.two_reference import (
    FEATURE_KIND,
    PresenceFeatureError,
    calibrate_pair,
    classify_frame,
    crop_roi,
    is_two_reference,
)

router = APIRouter(prefix="/api/presence", tags=["Presence"])
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_SIDE = 4096


class PresenceRequest(BaseModel):
    mode: str = Field(..., min_length=1, max_length=20)
    zone_id: int = Field(..., ge=1)
    present: Optional[str] = None
    empty: Optional[str] = None
    frame: Optional[str] = None
    roi: Optional[list[float]] = None


def _decode_image(encoded: Optional[str]) -> np.ndarray:
    if not encoded or not isinstance(encoded, str):
        raise HTTPException(status_code=422, detail="تصویر ارسال نشده است")
    if "," in encoded and encoded.lstrip().startswith("data:"):
        encoded = encoded.split(",", 1)[1]
    if len(encoded) > (MAX_IMAGE_BYTES * 4 // 3 + 16):
        raise HTTPException(status_code=413, detail="حجم تصویر بیش از حد مجاز است")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="کدگذاری تصویر معتبر نیست")
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="حجم تصویر بیش از حد مجاز است")
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=422, detail="فرمت تصویر قابل پردازش نیست")
    h, w = image.shape[:2]
    if min(w, h) < 32 or max(w, h) > MAX_IMAGE_SIDE:
        raise HTTPException(status_code=422, detail="ابعاد تصویر معتبر نیست")
    return image


def _reset_zone_runtime(zone_id: int):
    pipeline.state_machines[zone_id] = ZoneStateMachine(
        zone_id=zone_id,
        initial_state=SlotState.UNKNOWN,
    )
    pipeline.roi_buffers.pop(zone_id, None)
    pipeline.last_recognition_time[zone_id] = 0.0


@router.get("")
def presence_status(
    zone_id: Optional[int] = None,
    _admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Zone).order_by(Zone.id)
    if zone_id is not None:
        query = query.filter(Zone.id == zone_id)
    zones = query.all()
    return {
        "status": "ok",
        "engine": FEATURE_KIND,
        "supported_states": ["PRESENT", "ABSENT", "UNKNOWN"],
        "live_pipeline_integration": True,
        "manual_test_changes_cart": False,
        "zones": [
            {
                "id": zone.id,
                "name": zone.name,
                "calibrated": bool(
                    zone.ref_full_features
                    and zone.ref_empty_features
                    and is_two_reference(_safe_json(zone.ref_full_features))
                    and is_two_reference(_safe_json(zone.ref_empty_features))
                ),
                "state": zone.state,
                "roi": [zone.roi_x, zone.roi_y, zone.roi_w, zone.roi_h],
            }
            for zone in zones
        ],
    }


def _safe_json(value: Optional[str]):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


@router.post("")
def presence_action(
    payload: PresenceRequest,
    _admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    mode = payload.mode.strip().lower()
    zone = db.query(Zone).filter_by(id=payload.zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="جایگاه موردنظر پیدا نشد")

    if mode == "calibrate":
        if payload.present is None or payload.empty is None:
            raise HTTPException(status_code=422, detail="هر دو تصویر مرجعِ محصول حاضر و جایگاه خالی لازم است")
        present_image = _decode_image(payload.present)
        empty_image = _decode_image(payload.empty)
        roi = payload.roi
        try:
            full_ref, empty_ref, diagnostics = calibrate_pair(present_image, empty_image, roi)
        except PresenceFeatureError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        effective_roi = roi if roi is not None else [0.0, 0.0, 1.0, 1.0]
        zone.roi_x, zone.roi_y, zone.roi_w, zone.roi_h = [float(v) for v in effective_roi]
        zone.ref_full_features = json.dumps(full_ref, separators=(",", ":"))
        zone.ref_empty_features = json.dumps(empty_ref, separators=(",", ":"))
        # A new calibration must establish a fresh baseline before any cart event.
        zone.state = SlotState.UNKNOWN
        zone.confidence = 0.0
        zone.recognized_product_id = None
        zone.recognition_status = "UNKNOWN"
        zone.recognition_score = 0.0
        zone.last_recognized_at = None
        zone.last_picked_product_id = None
        db.commit()
        db.refresh(zone)
        _reset_zone_runtime(zone.id)
        return {
            "status": "READY",
            "zone_id": zone.id,
            "zone_name": zone.name,
            "roi": effective_roi,
            "algorithm": full_ref.get("algorithm", "unknown"),
            **diagnostics,
            "message": "کالیبراسیون ذخیره شد؛ سیستم ابتدا وضعیت فعلی قفسه را به‌عنوان مبنا تثبیت می‌کند.",
        }

    if mode == "detect":
        if payload.frame is None:
            raise HTTPException(status_code=422, detail="فریم آزمایشی ارسال نشده است")
        full_ref = _safe_json(zone.ref_full_features)
        empty_ref = _safe_json(zone.ref_empty_features)
        if not is_two_reference(full_ref) or not is_two_reference(empty_ref):
            raise HTTPException(status_code=409, detail="این جایگاه هنوز با دو مرجع جدید کالیبره نشده است")
        frame = _decode_image(payload.frame)
        roi = [zone.roi_x, zone.roi_y, zone.roi_w, zone.roi_h]
        try:
            cropped = crop_roi(frame, roi)
        except PresenceFeatureError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        started = time.perf_counter()
        state, confidence, diagnostics = classify_frame(cropped, full_ref, empty_ref)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "state": state,
            "confidence": confidence,
            "reason": diagnostics.get("reason", ""),
            "diagnostics": diagnostics,
            "elapsed_ms": elapsed_ms,
            "zone_id": zone.id,
            "transactions_enabled": False,
        }

    if mode == "clear":
        zone.ref_full_features = None
        zone.ref_empty_features = None
        zone.state = SlotState.UNKNOWN
        zone.confidence = 0.0
        zone.recognized_product_id = None
        zone.recognition_status = "UNKNOWN"
        zone.recognition_score = 0.0
        zone.last_recognized_at = None
        zone.last_picked_product_id = None
        db.commit()
        _reset_zone_runtime(zone.id)
        return {"status": "CLEARED", "zone_id": zone.id}

    raise HTTPException(status_code=422, detail="mode باید calibrate، detect یا clear باشد")
