"""Admin-only portable bottle lab. No changes to stock, zone state, carts or invoices."""
from __future__ import annotations

import base64
import math
from typing import Optional

import cv2
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator

from ..config import settings
from ..services.auth import get_current_admin
from ..services.bottle_dataset import build_dataset_zip, dataset_status, save_sample
from ..vision.bottle_detector import get_bottle_detector
from ..vision.camera_feed import camera_feed
from .presence import _decode_image

router = APIRouter(prefix="/api/bottle", tags=["Portable bottle lab"], dependencies=[Depends(get_current_admin)])


class DetectionRequest(BaseModel):
    frame: Optional[str] = Field(default=None, max_length=5_592_424)
    source: str = Field(default="upload", pattern="^(upload|tablet)$")
    threshold: float = Field(default=0.35, ge=0.1, le=0.95, allow_inf_nan=False)


class ReviewedBox(BaseModel):
    class_id: int = Field(ge=0, le=1)
    box: list[float] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def valid_box(self):
        x1, y1, x2, y2 = self.box
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in self.box) or x2 <= x1 or y2 <= y1:
            raise ValueError("Bounding boxes must be finite, normalized xyxy coordinates")
        return self


class SampleRequest(BaseModel):
    frame: str = Field(max_length=5_592_424)
    environment: str = Field(min_length=1, max_length=80)
    boxes: list[ReviewedBox] = Field(max_length=100)
    reviewed: bool
    negative: bool = False


@router.get("/status")
def status():
    return {**get_bottle_detector().status(), "dataset": dataset_status(settings.BOTTLE_DATASET_DIR)}


@router.post("/detect")
def detect(payload: DetectionRequest):
    if payload.source == "tablet":
        if not camera_feed.is_active(5.0):
            raise HTTPException(409, "فریم زنده از تبلت نداریم؛ اتصال دوربین را بررسی کنید.")
        frame = camera_feed.get_latest_frame()
        if frame is None:
            raise HTTPException(409, "تصویر دوربین آماده نیست.")
        frame = frame.copy()
    else:
        frame = _decode_image(payload.frame)
    try:
        result = get_bottle_detector().detect(frame, payload.threshold)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    # Return the exact analyzed tablet frame; never draw boxes over a newer frame.
    if payload.source == "tablet":
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            result["frame"] = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    return result


@router.post("/samples")
def sample(payload: SampleRequest):
    if not payload.reviewed or (not payload.boxes and not payload.negative) or (payload.boxes and payload.negative):
        raise HTTPException(422, "همه کادرها و برچسب‌ها را تأیید کنید؛ عکس بدون بطری باید صریحاً منفی ثبت شود.")
    environment = payload.environment.strip()
    if not environment:
        raise HTTPException(422, "نام محیط لازم است.")
    frame = _decode_image(payload.frame)
    try:
        record = save_sample(settings.BOTTLE_DATASET_DIR, frame, environment,
                             [box.model_dump() for box in payload.boxes])
    except FileExistsError as exc:
        raise HTTPException(409, str(exc))
    return {"id": record["id"], "saved": True, "dataset": dataset_status(settings.BOTTLE_DATASET_DIR)}


@router.get("/dataset.zip")
def export_dataset():
    try:
        data, _report = build_dataset_zip(settings.BOTTLE_DATASET_DIR)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return Response(data, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="SmartShelf-bottle-dataset.zip"', "Cache-Control": "no-store"})
