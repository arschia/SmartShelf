"""Authenticated signaling only. Video flows directly between tablet and admin.

HTTPS signaling also works when the tablet's WSS connection falls back to HTTPS.
Single-process, bounded, short-lived queues; no frames, SDP or ICE are persisted.
"""
import hashlib
import json
import os
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from ..services.auth import get_current_admin
from .camera_transport import authenticate
from ..vision.camera_feed import camera_feed

router = APIRouter(prefix='/api/rtc', tags=['WebRTC'])
sessions = {}
TTL = 45
MAX_SESSIONS = 8


def ice_servers():
    try:
        servers = json.loads(os.getenv('RTC_ICE_SERVERS', '[{"urls":"stun:stun.l.google.com:19302"}]'))
        if not isinstance(servers, list) or len(servers) > 8:
            raise ValueError()
        for server in servers:
            urls = server.get('urls', [])
            if isinstance(urls, str): urls = [urls]
            if not urls or len(urls) > 8 or any(not isinstance(u, str) or not u.startswith(('stun:', 'stuns:', 'turn:', 'turns:')) for u in urls):
                raise ValueError()
        return servers
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(503, 'تنظیم RTC_ICE_SERVERS معتبر نیست.')


def cleanup():
    now = time.monotonic()
    for sid, session in list(sessions.items()):
        if now - session['seen'] > TTL or (session['closed'] and now - session['closed'] > 10):
            sessions.pop(sid, None)


def get_session(sid):
    cleanup()
    session = sessions.get(sid)
    if not session: raise HTTPException(404, 'نشست نمایش دوربین پایان یافته است.')
    return session


def owned_session(sid, token):
    session = get_session(sid)
    if session['owner'] != hashlib.sha256(token.encode()).hexdigest():
        raise HTTPException(403, 'این نشست متعلق به ورود فعلی مدیر نیست.')
    return session


async def body(request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 96 * 1024: raise HTTPException(413, 'پیام اتصال بیش از حد بزرگ است.')
    try:
        value = json.loads(data)
        if not isinstance(value, dict): raise ValueError()
        return value
    except (ValueError, UnicodeError):
        raise HTTPException(422, 'پیام اتصال معتبر نیست.')


def append_signal(session, side, payload):
    kind = payload.get('type')
    allowed = ('offer', 'ice', 'close') if side == 'camera' else ('answer', 'ice', 'close')
    if kind not in allowed: raise HTTPException(422, 'نوع پیام اتصال معتبر نیست.')
    if kind in ('offer', 'answer'):
        description = payload.get('description')
        if not isinstance(description, dict) or description.get('type') != kind or not isinstance(description.get('sdp'), str) or len(description['sdp']) > 65536:
            raise HTTPException(422, 'SDP معتبر نیست.')
        payload = {'type': kind, 'description': {'type': kind, 'sdp': description['sdp']}}
    elif kind == 'ice':
        candidate = payload.get('candidate')
        if candidate is not None and (not isinstance(candidate, dict) or not isinstance(candidate.get('candidate'), str) or len(candidate['candidate']) > 8192):
            raise HTTPException(422, 'ICE معتبر نیست.')
        payload = {'type': kind, 'candidate': candidate}
    else:
        payload = {'type': 'close'}
    if session['closed']: return
    queue = session[side]
    if len(queue) >= 128: raise HTTPException(429, 'صف اتصال پر شده است؛ نمایش دوربین را دوباره باز کنید.')
    session[side + '_seq'] += 1
    queue.append(dict(payload, seq=session[side + '_seq']))
    if kind == 'close': session['closed'] = time.monotonic()


def events(session, side, after):
    if not isinstance(after, int) or isinstance(after, bool) or after < 0:
        raise HTTPException(422, 'شماره پیام معتبر نیست.')
    queue = session[side]
    # Messages stay until acknowledged by the next poll, making retries lossless.
    session[side] = [event for event in queue if event['seq'] > after]
    return session[side]


@router.post('/view')
async def open_view(request: Request, response: Response, token: str = Depends(get_current_admin)):
    cleanup()
    payload = await body(request)
    device_id = payload.get('device_id') or camera_feed.active_device_id
    if not device_id or device_id != camera_feed.active_device_id or not camera_feed.is_active():
        raise HTTPException(409, 'صفحهٔ دوربین تبلت باید باز، جفت‌شده و در حال ارسال تصویر باشد.')
    if len(sessions) >= MAX_SESSIONS or sum(s['device_id'] == device_id and not s['closed'] for s in sessions.values()) >= 3:
        raise HTTPException(429, 'نمایش دوربین در چند صفحه باز است؛ صفحه‌های اضافی را ببندید.')
    servers = ice_servers()
    sid = secrets.token_urlsafe(24)
    sessions[sid] = dict(device_id=device_id, owner=hashlib.sha256(token.encode()).hexdigest(), seen=time.monotonic(), closed=0, camera=[], viewer=[], camera_seq=0, viewer_seq=0)
    response.headers['Cache-Control'] = 'no-store'
    return dict(session_id=sid, device_id=device_id, ice_servers=servers, target_fps=30)


@router.get('/view/{sid}')
async def poll_view(sid: str, response: Response, after: int = 0, token: str = Depends(get_current_admin)):
    session = owned_session(sid, token)
    session['seen'] = time.monotonic()
    response.headers['Cache-Control'] = 'no-store'
    return dict(messages=events(session, 'viewer', after), closed=bool(session['closed']))


@router.post('/view/{sid}/signal')
async def signal_view(sid: str, request: Request, token: str = Depends(get_current_admin)):
    session = owned_session(sid, token)
    append_signal(session, 'camera', await body(request))
    return {'ok': True}


@router.post('/camera/poll')
async def poll_camera(request: Request, response: Response, device_id: str):
    authenticate(request, device_id)
    cleanup()
    cursors = (await body(request)).get('after', {})
    if not isinstance(cursors, dict) or len(cursors) > MAX_SESSIONS: raise HTTPException(422, 'فهرست نشست‌ها معتبر نیست.')
    result = []
    for sid, session in sessions.items():
        if session['device_id'] == device_id:
            result.append(dict(session_id=sid, messages=events(session, 'camera', cursors.get(sid, 0)), closed=bool(session['closed'])))
    response.headers['Cache-Control'] = 'no-store'
    return dict(sessions=result, ice_servers=ice_servers())


@router.post('/camera/{sid}/signal')
async def signal_camera(sid: str, request: Request, device_id: str):
    authenticate(request, device_id)
    session = get_session(sid)
    if session['device_id'] != device_id: raise HTTPException(403, 'دوربین این نشست متفاوت است.')
    append_signal(session, 'viewer', await body(request))
    return {'ok': True}
