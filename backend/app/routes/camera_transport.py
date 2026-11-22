"""Authenticated HTTPS fallback for devices whose network cannot keep WSS open."""
import re
from fastapi import APIRouter,Request,Depends,HTTPException,Response
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Device,utc_now
from ..services.camera_pairing import get_device_info_by_token
from ..vision.camera_feed import camera_feed
from ..ws import manager

router=APIRouter(prefix="/api/camera",tags=["Camera transport"])


def authenticate(request,device_id):
    value=request.headers.get('Authorization','')
    token=value[7:] if value.startswith('Bearer ') else ''
    info=get_device_info_by_token(token)
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,50}',device_id) or not info or info['device_id']!=device_id:
        raise HTTPException(401,'جفت‌سازی دوربین معتبر نیست؛ یک کد جفت‌سازی تازه از پنل بگیرید.')


# Bounded in-memory desired AI-upload state for HTTPS-only tablets.
# Authentication is identical to the camera frame upload route.
_desired_controls = {}
_control_revision = 0


def set_camera_control(device_id: str, enabled: bool):
    global _control_revision
    if not device_id:
        return 0
    _control_revision += 1
    if len(_desired_controls) >= 32 and device_id not in _desired_controls:
        _desired_controls.pop(next(iter(_desired_controls)))
    _desired_controls[device_id] = {"revision": _control_revision, "enabled": bool(enabled)}
    return _control_revision


@router.get('/control')
def camera_control(request: Request, response: Response, device_id: str):
    authenticate(request, device_id)
    response.headers['Cache-Control'] = 'no-store'
    return _desired_controls.get(device_id, {"revision": 0, "enabled": None})


@router.post('/frame')
async def camera_frame(request:Request,device_id:str,db:Session=Depends(get_db)):
    authenticate(request,device_id)
    data=bytearray()
    async for chunk in request.stream():
        if len(data)+len(chunk)>camera_feed.MAX_FRAME_BYTES:raise HTTPException(413,'حجم فریم زیاد است.')
        data.extend(chunk)
    if not camera_feed.process_frame_bytes(device_id,bytes(data)):raise HTTPException(422,'فریم دوربین معتبر نیست.')
    device=db.query(Device).filter_by(device_id=device_id).first()
    was_online=bool(device and device.is_online and (utc_now()-device.last_seen).total_seconds()<10)
    if not device:
        device=Device(device_id=device_id,role='CAMERA');db.add(device)
    device.is_online=True;device.last_seen=utc_now();db.commit()
    if not was_online:
        await manager.broadcast_to_admins({'type':'DEVICE_STATUS','device_id':device_id,'role':'CAMERA','is_online':True})
    from ..main import process_received_camera_frame
    await process_received_camera_frame(camera_feed.get_latest_frame(),db,device_id)
    return {'type':'frame_received','frame_count':camera_feed.frame_count,'transport':'https'}
