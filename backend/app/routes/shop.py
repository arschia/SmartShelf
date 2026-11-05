"""Authenticated university scenario controls and frames. Entry/cart reuse core routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Product, Zone, ShopScenario, CustomerSession
from ..services.auth import get_current_admin
from ..services.shop_scenario import configuration, snapshot, shop_runtime, process_shop_frame
from ..vision.bottle_detector import get_bottle_detector
from ..ws import manager
from .presence import _decode_image

router = APIRouter(prefix="/api/shop", tags=["University live store"], dependencies=[Depends(get_current_admin)])


class Setup(BaseModel):
    enabled: bool
    zone_id: Optional[int] = Field(default=None,ge=1)
    product_id: Optional[int] = Field(default=None,ge=1)
    unit_price: Optional[int] = Field(default=None,ge=0,le=1_000_000_000)
    camera_source: str = Field(default="browser",pattern="^(browser|tablet)$")
    roi: list[float] = Field(default_factory=lambda:[0,0,1,1],min_length=4,max_length=4)
    roi_confirmed: bool = False

    @model_validator(mode="after")
    def validate_roi(self):
        import math
        x,y,w,h = self.roi
        if not all(math.isfinite(v) and 0<=v<=1 for v in self.roi) or min(w,h)<.05 or x+w>1.000001 or y+h>1.000001:
            raise ValueError("Invalid shelf ROI")
        return self


class ShopFrame(BaseModel):
    frame: str = Field(max_length=5_592_424)
    stream_id: str = Field(pattern=r"^[A-Za-z0-9_-]{3,70}$")
    sequence: int = Field(ge=0)


@router.get("/status")
def shop_status(db:Session=Depends(get_db)):
    return {"shop":snapshot(db),
            "products":[{"id":p.id,"name":p.name,"unit_price":p.unit_price,"stock_quantity":p.stock_quantity} for p in db.query(Product).order_by(Product.id)],
            "zones":[{"id":z.id,"name":z.name} for z in db.query(Zone).order_by(Zone.id)]}


@router.post("/configure")
async def configure(payload:Setup,db:Session=Depends(get_db)):
    cfg = configuration(db)
    if not payload.enabled:
        if cfg: cfg.enabled=False
        db.commit(); shop_runtime.reset()
    else:
        if db.query(CustomerSession).filter_by(status="ACTIVE").first():
            raise HTTPException(409,"برای تغییر تنظیمات، ابتدا سشن مشتری فعلی را پایان دهید.")
        zone,product = db.get(Zone,payload.zone_id),db.get(Product,payload.product_id)
        if not zone or not product:
            raise HTTPException(422,"محصول و جایگاه را انتخاب کنید.")
        if not payload.roi_confirmed:
            raise HTTPException(422,"محدودهٔ جایگاه بطری را روی تصویر مشخص و تأیید کنید.")
        if not get_bottle_detector().status()["ready"]:
            raise HTTPException(503,"مدل بطری آماده نیست.")
        if not cfg:
            cfg=ShopScenario(id=1);db.add(cfg);db.flush()
        elif cfg.stock_quantity:
            old=db.get(Product,cfg.product_id)
            if old: old.stock_quantity=max(0,old.stock_quantity-cfg.stock_quantity)
        cfg.enabled=True;cfg.zone_id=zone.id;cfg.product_id=product.id
        cfg.camera_source=payload.camera_source;cfg.stock_quantity=None;cfg.pick_session_id=None
        cfg.generation=(cfg.generation or 0)+1;cfg.needs_review=False
        zone.product_id=product.id;zone.roi_x,zone.roi_y,zone.roi_w,zone.roi_h=payload.roi
        zone.state="UNKNOWN";zone.confidence=0.
        if payload.unit_price is not None: product.unit_price=payload.unit_price
        product.is_active=True
        db.commit();shop_runtime.reset()
    state=snapshot(db)
    await manager.broadcast_to_admins({"type":"SHOP_STATE","shop":state})
    return {"shop":state}


@router.post("/frame")
async def frame(payload:ShopFrame,db:Session=Depends(get_db)):
    cfg=configuration(db)
    if not cfg or not cfg.enabled or cfg.camera_source!="browser":
        raise HTTPException(409,"سناریو با دوربین همین دستگاه فعال نیست.")
    result=await process_shop_frame(_decode_image(payload.frame),db,"browser:"+payload.stream_id,payload.sequence)
    if not result.get("accepted"):
        raise HTTPException(409,"فریم تکراری است یا دوربین دیگری در حال ارسال تصویر است.")
    # No customer secrets are returned to the browser; the cart was pushed server-side.
    return result
