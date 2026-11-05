import json
import re
import base64
import asyncio
import time
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy.orm import Session

from .config import settings
from .ws import manager
from .db import init_db, SessionLocal, get_db
from .models import Device, CustomerSession, Zone, utc_now
from .vision.camera_feed import camera_feed
from .vision.pipeline import pipeline
from .vision.state_machine import ZoneStateMachine, SlotState
from .services.seed import seed_initial_data, seed_store_data
from .services.migration import run_idempotent_migrations
from .services.recognition import ProductRecognitionEngine
from .services.event_service import record_transition, record_system_event, get_cart_summary
from .services.session_service import check_and_expire_idle_sessions
from .services.auth import is_admin_token_valid
from .services.camera_pairing import is_camera_device_token_valid, get_device_info_by_token
from .schemas import HealthResponse
from .routes.admin import router as admin_router
from .routes.entry import router as entry_router
from .routes.presence import router as presence_router
from .routes.bottle import router as bottle_router
from .routes.shop import router as shop_router
from .routes.camera_transport import router as camera_transport_router
from .routes.rtc import router as rtc_router
from .services.shop_scenario import demo_enabled, process_shop_frame, snapshot as shop_snapshot

# Directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
ADMIN_DIR = FRONTEND_DIR / "admin"
CUSTOMER_DIR = FRONTEND_DIR / "customer"
CAMERA_DIR = FRONTEND_DIR / "camera"
ASSETS_DIR = FRONTEND_DIR / "assets"
ENTER_DIR = FRONTEND_DIR / "enter"
DEMO_DIR = FRONTEND_DIR / "demo"
STYLEGUIDE_DIR = FRONTEND_DIR / "styleguide"
UPLOADS_DIR = Path(settings.UPLOAD_DIR).resolve()

STATIC_DIR.mkdir(parents=True, exist_ok=True)
ADMIN_DIR.mkdir(parents=True, exist_ok=True)
CUSTOMER_DIR.mkdir(parents=True, exist_ok=True)
CAMERA_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
ENTER_DIR.mkdir(parents=True, exist_ok=True)
DEMO_DIR.mkdir(parents=True, exist_ok=True)
STYLEGUIDE_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def load_startup_recovery(db: Session):
    """Recover persisted store state from database upon server boot/restart."""
    # 1. Check and report active customer session and cart
    active_sess = db.query(CustomerSession).filter_by(status="ACTIVE").order_by(CustomerSession.id.desc()).first()
    if active_sess:
        cart_info = get_cart_summary(db, active_sess.id)
        print(f"[RECOVERY] Resumed active session #{active_sess.id} with {cart_info['total_quantity']} cart items.")

    # 2. Initialize in-memory state machines to UNKNOWN state
    # This guarantees zero false PICKED/RETURNED events during cold start stabilization.
    zones = db.query(Zone).order_by(Zone.id).all()
    for z in zones:
        pipeline.state_machines[z.id] = ZoneStateMachine(
            zone_id=z.id,
            initial_state=SlotState.UNKNOWN,
            stable_seconds=settings.STABLE_SECONDS,
        )
    print(f"[RECOVERY] Initialized {len(zones)} slot state machines in UNKNOWN state.")


async def run_background_watchdog():
    """Periodic watchdog for idle sessions and camera sensor timeout (>10s)."""
    while True:
        try:
            await asyncio.sleep(2.0)
            with SessionLocal() as db:
                # 1. Expire idle/abandoned sessions
                expired = check_and_expire_idle_sessions(db)
                for s in expired:
                    await manager.broadcast_to_customer(s.session_secret, {
                        "type": "SESSION_CLOSED",
                        "exit_reason": "EXPIRED",
                    })
                    await manager.broadcast_to_admins({
                        "type": "SESSION_CLOSED",
                        "session_id": s.id,
                        "exit_reason": "EXPIRED",
                        "exited_at": s.exited_at.isoformat() if s.exited_at else None,
                    })

                # 2. Camera timeout warning (> 10 seconds without frame)
                if camera_feed.active_device_id and not camera_feed.is_active(timeout_seconds=10.0):
                    await manager.broadcast_to_admins({
                        "type": "CAMERA_WARNING",
                        "message": "دوربین بیش از ۱۰ ثانیه قطع است / Camera sensor timeout (>10s)"
                    })
        except asyncio.CancelledError:
            break
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database schema, run safe migrations, seed initial data, and recover runtime state
    init_db()
    run_idempotent_migrations()
    with SessionLocal() as db:
        # Production starts with the owner's single intended item (Hejoo Peach),
        # not the three generic demo products used by automated tests.
        if settings.APP_ENV == "production":
            seed_store_data(db)
        else:
            seed_initial_data(db)
        load_startup_recovery(db)
        ProductRecognitionEngine.get_instance().load_or_rebuild_index(db)

    watchdog_task = asyncio.create_task(run_background_watchdog())
    yield
    watchdog_task.cancel()


app = FastAPI(
    title="SMARTSHELF Local Cashierless Store",
    version="0.1.0",
    lifespan=lifespan
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


# Strict CORS: Only explicitly allowed origins, specific methods & headers. No wildcard '*'.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
)

if settings.TRUST_PROXY:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Include API and entry routes
app.include_router(entry_router)
app.include_router(admin_router)
app.include_router(presence_router)
app.include_router(bottle_router)
app.include_router(shop_router)
app.include_router(camera_transport_router)
app.include_router(rtc_router)

# Mount Static and Frontend assets
# Uploaded media lives on a persistent volume in cloud deployments.
# Mount this route before /static so /static/uploads/* does not resolve to
# the ephemeral frontend/static directory.
app.mount("/static/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="persistent_uploads")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
app.mount("/admin", StaticFiles(directory=str(ADMIN_DIR), html=True), name="admin")
app.mount("/customer", StaticFiles(directory=str(CUSTOMER_DIR), html=True), name="customer")
app.mount("/camera", StaticFiles(directory=str(CAMERA_DIR), html=True), name="camera")
app.mount("/demo", StaticFiles(directory=str(DEMO_DIR), html=True), name="demo")
app.mount("/styleguide", StaticFiles(directory=str(STYLEGUIDE_DIR), html=True), name="styleguide")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


# WebSocket Endpoints
@app.websocket("/ws/admin")
async def websocket_admin_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    """Admin live events/feed WebSocket. Requires valid HMAC token in the first message within 5s."""
    await websocket.accept()
    token = None
    try:
        raw_msg = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        try:
            payload = json.loads(raw_msg)
            if isinstance(payload, dict):
                token = payload.get("token")
        except Exception:
            token = raw_msg.strip()
    except Exception:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return

    if not is_admin_token_valid(token):
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return

    await manager.connect_admin(websocket)
    try:
        await websocket.send_json({"type": "AUTH_OK"})
        if demo_enabled(db):
            await websocket.send_json({"type": "SHOP_STATE", "shop": shop_snapshot(db)})
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        manager.disconnect_admin(websocket)


@app.websocket("/ws/customer")
async def websocket_customer_endpoint(
    websocket: WebSocket,
    session: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Customer live cart WebSocket. Reads session_secret from first message within 5s (or query param)."""
    await websocket.accept()
    session_secret = session
    if not session_secret:
        try:
            raw_msg = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            try:
                payload = json.loads(raw_msg)
                if isinstance(payload, dict):
                    session_secret = payload.get("session_secret") or payload.get("session")
            except Exception:
                session_secret = raw_msg.strip()
        except Exception:
            try:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            except Exception:
                pass
            return

    if not session_secret:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return

    # Security: Only allow connection if valid customer session secret exists in database
    cust_session = db.query(CustomerSession).filter_by(session_secret=session_secret).first()
    if not cust_session:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return

    await manager.connect_customer(websocket, session_secret)

    # Immediately synchronize client with current live cart state
    current_cart = get_cart_summary(db, cust_session.id)
    try:
        await websocket.send_json({
            "type": "CART_SYNC",
            "cart": current_cart
        })
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        manager.disconnect_customer(websocket, session_secret)


async def process_received_camera_frame(frame, db, device_id):
    """Shared WSS/HTTPS camera path; accounting and broadcasts are identical."""
    db.expire_all()
    # Run vision pipeline on decoded frame (only while camera is active and within 10s freshness)
    if demo_enabled(db) and camera_feed.is_active(timeout_seconds=10.0):
        current_frame = frame
        if current_frame is not None:
            await process_shop_frame(current_frame, db, "tablet:" + device_id)

    if not demo_enabled(db) and camera_feed.is_active(timeout_seconds=10.0):
        current_frame = frame
        if current_frame is not None:
            _, zone_results = pipeline.process_frame(current_frame, db)
            await manager.broadcast_to_admins({
                "type": "ZONES_STATUS",
                "zones": zone_results
            })

            # Handle confirmed slot transitions
            for zres in zone_results:
                if zres.get("transition"):
                    from_st, to_st = zres["transition"]
                    zone = db.query(Zone).filter_by(id=zres["id"]).first()
                    if zone:
                        evt, cart_info = record_transition(
                            db=db,
                            zone=zone,
                            from_state=from_st,
                            to_state=to_st,
                            confidence=zres.get("confidence", 1.0),
                            transition_counter=zres.get("transition_count", 1),
                        )
                        if evt:
                            await manager.broadcast_to_admins({
                                "type": "EVENT_CREATED",
                                "event": {
                                    "id": evt.id,
                                    "event_uid": evt.event_uid,
                                    "type": evt.type,
                                    "session_id": evt.session_id,
                                    "device_id": device_id,
                                    "zone_id": evt.zone_id,
                                    "zone_name": zone.name,
                                    "product_id": evt.product_id,
                                    "product_name": evt.product.name if evt.product else None,
                                    "confidence": evt.confidence,
                                    "status": evt.status,
                                    "created_at": evt.created_at.isoformat(),
                                }
                            })
                            if cart_info:
                                action_type = cart_info.get("action")
                                sec = cart_info.get("session_secret")
                                if action_type in ("PICKED", "RETURNED") and cart_info.get("cart"):
                                    if sec:
                                        await manager.broadcast_to_customer(sec, {
                                            "type": "CART_UPDATED",
                                            "action": cart_info["action"],
                                            "product_name": cart_info["product_name"],
                                            "cart": cart_info["cart"],
                                        })
                                    await manager.broadcast_to_admins({
                                        "type": "CART_UPDATED",
                                        "session_id": cart_info["session_id"],
                                        "cart": cart_info["cart"],
                                    })
                                elif action_type == "UNCERTAIN" and sec:
                                    await manager.broadcast_to_customer(sec, {
                                        "type": "PRODUCT_UNCERTAIN",
                                        "zone_id": cart_info.get("zone_id"),
                                        "message": "کالای برداشته یا بازگردانده شده نامشخص است و سبد تغییر نکرد."
                                    })
                                elif action_type == "MISMATCH" and sec:
                                    await manager.broadcast_to_customer(sec, {
                                        "type": "PRODUCT_MISMATCH",
                                        "zone_id": cart_info.get("zone_id"),
                                        "message": "کالای قرار داده شده با کالای این جایگاه تطابق ندارد."
                                    })



@app.websocket("/ws/camera")
async def websocket_camera_endpoint(
    websocket: WebSocket,
    device_id: str = Query("camera_tablet"),
    db: Session = Depends(get_db),
):
    """Camera sensor WebSocket. Paired device token is sent in the first AUTH message, never in the URL."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,50}", str(device_id or "")):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Always authenticate in the first WebSocket message; never accept credentials in URL query strings.
    await websocket.accept()
    device_token = None
    frame_ack_requested = False
    try:
        raw_msg = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        data = json.loads(raw_msg)
        if isinstance(data, dict) and data.get("type") == "auth":
            device_token = data.get("device_token") or data.get("token")
            frame_ack_requested = data.get("frame_ack") is True
            if data.get("device_id"):
                candidate_device_id = str(data.get("device_id"))
                if not re.fullmatch(r"[A-Za-z0-9_-]{3,50}", candidate_device_id):
                    raise ValueError("Invalid device_id")
                device_id = candidate_device_id
    except Exception:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return

    device_info = get_device_info_by_token(device_token)
    if device_info and "device_id" not in websocket.query_params:
        device_id = device_info["device_id"]
    if not device_info or device_info.get("device_id") != device_id:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return

    await manager.connect_camera(websocket, device_id)

    # Register or mark online in database
    device = db.query(Device).filter_by(device_id=device_id).first()
    now = utc_now()
    if not device:
        device = Device(
            device_id=device_id,
            role="CAMERA",
            last_seen=now,
            is_online=True
        )
        db.add(device)
    else:
        device.role = "CAMERA"
        device.is_online = True
        device.last_seen = now
    db.commit()
    await websocket.send_json({"type": "connected", "device_id": device_id, "frame_ack":frame_ack_requested})

    # Record DEVICE_CONNECTED operational event
    conn_evt = record_system_event(
        db,
        event_type="DEVICE_CONNECTED",
        device_id=device_id,
        status="PROCESSED"
    )

    # Broadcast device status update to connected admin dashboards
    await manager.broadcast_to_admins({
        "type": "DEVICE_STATUS",
        "device_id": device_id,
        "role": "CAMERA",
        "is_online": True
    })
    await manager.broadcast_to_admins({
        "type": "EVENT_CREATED",
        "event": {
            "id": conn_evt.id,
            "event_uid": conn_evt.event_uid,
            "type": conn_evt.type,
            "session_id": None,
            "device_id": device_id,
            "zone_id": None,
            "zone_name": None,
            "product_id": None,
            "product_name": None,
            "confidence": 1.0,
            "status": "PROCESSED",
            "created_at": conn_evt.created_at.isoformat(),
        }
    })

    last_device_heartbeat = 0.0
    try:
        while True:
            msg = await websocket.receive()
            now = utc_now()

            processed = False
            # Handle binary JPEG frame
            if "bytes" in msg and msg["bytes"]:
                raw_bytes = msg["bytes"]
                processed = camera_feed.process_frame_bytes(device_id, raw_bytes)
            elif "text" in msg and msg["text"]:
                txt = msg["text"]
                if txt == "ping":
                    await websocket.send_text("pong")
                elif txt.startswith("{"):
                    try:
                        data = json.loads(txt)
                        if data.get("type") == "ping":
                            await websocket.send_json({"type": "pong"})
                        elif data.get("type") == "frame" and "data" in data:
                            encoded = data["data"]
                            if isinstance(encoded, str) and len(encoded) <= 6 * 1024 * 1024:
                                raw = base64.b64decode(encoded, validate=True)
                                processed = camera_feed.process_frame_bytes(device_id, raw)
                    except Exception:
                        pass

            if processed:
                await process_received_camera_frame(camera_feed.get_latest_frame(), db, device_id)
                if frame_ack_requested:
                    await websocket.send_json({"type":"frame_received","frame_count":camera_feed.frame_count})

            # Keep device last_seen fresh
            # Reduce SQLite write amplification during high-FPS camera streaming.
            if time.monotonic() - last_device_heartbeat >= 3.0:
                dev = db.query(Device).filter_by(device_id=device_id).first()
                if dev:
                    dev.last_seen = now
                    dev.is_online = True
                    db.commit()
                last_device_heartbeat = time.monotonic()

    except (WebSocketDisconnect, Exception):
        pass
    finally:
        manager.disconnect_camera(websocket, device_id)
        dev = db.query(Device).filter_by(device_id=device_id).first()
        if dev:
            dev.is_online = False
            dev.last_seen = utc_now()
            db.commit()

        disc_evt = record_system_event(
            db,
            event_type="DEVICE_DISCONNECTED",
            device_id=device_id,
            status="PROCESSED"
        )

        await manager.broadcast_to_admins({
            "type": "DEVICE_STATUS",
            "device_id": device_id,
            "role": "CAMERA",
            "is_online": False
        })
        await manager.broadcast_to_admins({
            "type": "EVENT_CREATED",
            "event": {
                "id": disc_evt.id,
                "event_uid": disc_evt.event_uid,
                "type": disc_evt.type,
                "session_id": None,
                "device_id": device_id,
                "zone_id": None,
                "zone_name": None,
                "product_id": None,
                "product_name": None,
                "confidence": 1.0,
                "status": "PROCESSED",
                "created_at": disc_evt.created_at.isoformat(),
            }
        })


@app.get("/config.js", include_in_schema=False)
def serve_config_js():
    cfg = FRONTEND_DIR / "config.js"
    if cfg.exists():
        return FileResponse(cfg, media_type="application/javascript")
    from fastapi.responses import Response
    return Response(content='window.SMARTSHELF_CONFIG = { apiBase: "" };', media_type="application/javascript")


@app.get("/shop", include_in_schema=False)
@app.get("/shop/", include_in_schema=False)
def shop_page():
    return FileResponse(FRONTEND_DIR / "shop.html")


@app.get("/bottle", include_in_schema=False)
@app.get("/bottle/", include_in_schema=False)
def bottle_page():
    return FileResponse(FRONTEND_DIR / "bottle.html")


@app.get("/presence", include_in_schema=False)
@app.get("/presence/", include_in_schema=False)
def presence_page():
    """Serve the integrated two-reference calibration UI."""
    page = FRONTEND_DIR / "presence.html"
    if page.exists():
        return FileResponse(page)
    return RedirectResponse(url="/admin")


@app.get("/", include_in_schema=False)
def root():
    """Serve frontend landing portal or redirect to admin."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return RedirectResponse(url="/admin")


@app.get("/api/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Health check endpoint to verify backend service status."""
    return {"status": "ok"}
