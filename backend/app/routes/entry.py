import secrets
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy.orm import Session

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

from ..config import settings
from ..db import get_db
from ..models import EntryToken, CustomerSession, Event, CartItem, Product, Invoice, InvoiceLine, utc_now
from ..schemas import (
    CustomerSessionStatusResponse,
    CheckoutRequest,
    CheckoutResponse,
    InvoiceResponse,
    CameraPairRequest,
    CameraPairResponse,
    CustomerEnterRequest,
    CustomerEnterResponse,
)
from ..ws import manager
from ..services.event_service import get_cart_summary
from ..services.rate_limiter import enter_limiter
from ..services.session_service import check_and_expire_idle_sessions
from ..services.camera_pairing import exchange_pairing_code_for_token
from ..services.shop_scenario import demo_enabled
from ..services.auth import normalize_digits

router = APIRouter(tags=["Entry & Customer"])


def _render_error_page(title_fa: str, title_en: str, message_fa: str, message_en: str) -> str:
    """Renders a standalone dark navy/turquoise styled error page for mobile browser."""
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title_fa} | SMARTSHELF</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #0b132b;
      color: #e0e6ed;
      font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Tahoma, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 1.5rem;
    }}
    .card {{
      background: #1c2541;
      border: 1px solid #3a506b;
      border-radius: 16px;
      max-width: 440px;
      width: 100%;
      padding: 2rem;
      text-align: center;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
    }}
    .icon {{
      font-size: 3.5rem;
      margin-bottom: 1rem;
      color: #e63946;
    }}
    h1 {{
      font-size: 1.4rem;
      color: #ffffff;
      margin-bottom: 0.5rem;
    }}
    h2 {{
      font-size: 1.1rem;
      color: #a0aec0;
      margin-bottom: 1.5rem;
      font-weight: 500;
      direction: ltr;
    }}
    p.fa {{
      font-size: 1rem;
      color: #cbd5e1;
      line-height: 1.6;
      margin-bottom: 0.75rem;
    }}
    p.en {{
      font-size: 0.9rem;
      color: #94a3b8;
      line-height: 1.5;
      direction: ltr;
    }}
    .badge {{
      display: inline-block;
      margin-top: 1.5rem;
      padding: 0.4rem 1rem;
      border-radius: 9999px;
      background: rgba(0, 180, 216, 0.1);
      color: #48cae4;
      font-size: 0.85rem;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">⚠️</div>
    <h1>{title_fa}</h1>
    <h2>{title_en}</h2>
    <p class="fa">{message_fa}</p>
    <p class="en">{message_en}</p>
    <div class="badge">SMARTSHELF</div>
  </div>
</body>
</html>"""


@router.get("/enter", response_class=HTMLResponse)
async def enter_store(request: Request, token: Optional[str] = Query(None, description="Single-use entry token"), db: Session = Depends(get_db)):
    """Customer QR scan entry endpoint."""
    if not token:
        enter_index = FRONTEND_DIR / "enter" / "index.html"
        if enter_index.exists():
            return FileResponse(enter_index)
        return HTMLResponse("<h3>صفحه ورود به فروشگاه</h3>", status_code=200)

    enter_limiter.check(request)
    now = utc_now()

    # 0. Check if store is open
    if not settings.STORE_OPEN and not demo_enabled(db):
        html = _render_error_page(
            title_fa="فروشگاه بسته است",
            title_en="Store is Currently Closed",
            message_fa="در حال حاضر پذیرش مشتری جدید انجام نمی‌شود. لطفاً در ساعات کاری مراجعه فرمایید.",
            message_en="The store is currently closed. Please visit during open hours."
        )
        return HTMLResponse(content=html, status_code=status.HTTP_403_FORBIDDEN)

    # Automatically close any abandoned/idle sessions before checking occupancy
    check_and_expire_idle_sessions(db)

    # 1. Check if store is already occupied by an active customer session
    active_session = db.query(CustomerSession).filter(CustomerSession.status == "ACTIVE").first()
    if active_session:
        html = _render_error_page(
            title_fa="فروشگاه اشغال است",
            title_en="Store is Currently Occupied",
            message_fa="در حال حاضر یک مشتری داخل فروشگاه است. لطفاً منتظر بمانید تا خرید ایشان به پایان برسد.",
            message_en="Another customer is currently in the store. Please wait until they exit."
        )
        return HTMLResponse(content=html, status_code=status.HTTP_409_CONFLICT)

    # 2. Validate token
    entry_token = db.query(EntryToken).filter(EntryToken.token == token).first()
    if not entry_token or entry_token.used_at is not None or entry_token.expires_at < now:
        html = _render_error_page(
            title_fa="کد ورود نامعتبر یا منقضی شده است",
            title_en="Invalid or Expired Entry Code",
            message_fa="این کد ورود منقضی شده یا قبلاً استفاده شده است. لطفاً کد جدیدی را از مانیتور اسکن کنید.",
            message_en="This entry code has expired or has already been used. Please scan the newly displayed QR code."
        )
        return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

    # 3. Mark token as used
    entry_token.used_at = now

    # 4. Generate random session secret and create active session
    session_secret = secrets.token_urlsafe(32)
    new_session = CustomerSession(
        status="ACTIVE",
        entered_at=now,
        session_secret=session_secret
    )
    db.add(new_session)
    db.flush()

    # 5. Record Event in DB
    event = Event(
        event_uid=secrets.token_hex(16),
        type="CUSTOMER_ENTERED",
        session_id=new_session.id,
        confidence=1.0,
        status="PROCESSED",
        created_at=now
    )
    db.add(event)
    db.commit()
    db.refresh(new_session)

    # 6. Notify connected admin dashboard via WebSocket
    await manager.broadcast_to_admins({
        "type": "CUSTOMER_ENTERED",
        "session_id": new_session.id,
        "entered_at": new_session.entered_at.isoformat(),
        "status": "ACTIVE"
    })
    await manager.broadcast_to_admins({
        "type": "EVENT_CREATED",
        "event": {
            "id": event.id,
            "event_uid": event.event_uid,
            "type": event.type,
            "session_id": event.session_id,
            "zone_id": None,
            "zone_name": None,
            "product_id": None,
            "product_name": None,
            "confidence": event.confidence,
            "status": event.status,
            "created_at": event.created_at.isoformat()
        }
    })

    # 7. Redirect mobile browser to customer view with session secret
    return RedirectResponse(
        url=f"/customer?session={session_secret}",
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/api/enter", response_model=CustomerEnterResponse)
async def api_enter_store(
    request: Request,
    payload: CustomerEnterRequest,
    db: Session = Depends(get_db)
):
    """Customer API entry endpoint returning session_secret or structured error."""
    enter_limiter.check(request)
    now = utc_now()

    # 1. Check if store is open
    if not settings.STORE_OPEN and not demo_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="فروشگاه بسته است / Store is closed"
        )

    # 2. Automatically expire idle sessions
    check_and_expire_idle_sessions(db)

    # 3. Check if occupied
    active_session = db.query(CustomerSession).filter(CustomerSession.status == "ACTIVE").first()
    if active_session:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="فروشگاه در حال حاضر اشغال است / Store is occupied"
        )

    # 4. Check token
    entry_token = db.query(EntryToken).filter(EntryToken.token == normalize_digits(payload.token.strip())).first()
    if not entry_token or entry_token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="کد ورود نامعتبر است یا قبلاً استفاده شده است / Invalid or used entry code"
        )

    if entry_token.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="کد ورود منقضی شده است / Entry code expired"
        )

    # 5. Consume token and create session
    entry_token.used_at = now
    session_secret = secrets.token_urlsafe(32)
    new_session = CustomerSession(
        session_secret=session_secret,
        entered_at=now,
        status="ACTIVE"
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    # Record CUSTOMER_ENTERED event
    ent_evt = Event(
        event_uid=f"CUST_ENTER_{new_session.id}_{now.strftime('%Y%m%d%H%M%S%f')}",
        type="CUSTOMER_ENTERED",
        session_id=new_session.id,
        status="PROCESSED",
        created_at=now
    )
    db.add(ent_evt)
    db.commit()
    db.refresh(ent_evt)

    # Broadcast to admin dashboards
    await manager.broadcast_to_admins({
        "type": "CUSTOMER_ENTERED",
        "session_id": new_session.id,
        "entered_at": new_session.entered_at.isoformat()
    })
    await manager.broadcast_to_admins({
        "type": "EVENT_CREATED",
        "event": {
            "id": ent_evt.id,
            "event_uid": ent_evt.event_uid,
            "type": ent_evt.type,
            "session_id": new_session.id,
            "device_id": None,
            "zone_id": None,
            "zone_name": None,
            "product_id": None,
            "product_name": None,
            "confidence": 1.0,
            "status": "PROCESSED",
            "created_at": ent_evt.created_at.isoformat()
        }
    })

    return CustomerEnterResponse(
        session_secret=session_secret,
        session_id=new_session.id,
        status="ACTIVE",
        entered_at=new_session.entered_at.isoformat(),
        message="ورود با موفقیت انجام شد / Successfully entered"
    )


@router.post("/api/camera/pair", response_model=CameraPairResponse)
def pair_camera_device(payload: CameraPairRequest):
    """Pair a camera tablet device using a 6-digit code and issue a device_token."""
    token = exchange_pairing_code_for_token(payload.clean_code, payload.device_id)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="کد جفت‌سازی نامعتبر است یا منقضی شده است / Invalid or expired pairing code"
        )
    return CameraPairResponse(
        device_token=token,
        device_id=payload.device_id,
        message="دستگاه با موفقیت جفت‌سازی شد"
    )


@router.get("/api/customer/session", response_model=CustomerSessionStatusResponse)
def get_customer_session_status(
    secret: str = Query(..., description="Customer session secret"),
    db: Session = Depends(get_db)
):
    """Returns the status of a customer session by secret."""
    check_and_expire_idle_sessions(db)
    session = db.query(CustomerSession).filter(CustomerSession.session_secret == secret).first()
    if not session:
        return CustomerSessionStatusResponse(
            valid=False,
            message="نشست معتبری یافت نشد / Session not found"
        )

    if session.status == "CLOSED":
        return CustomerSessionStatusResponse(
            valid=False,
            session_id=session.id,
            status="CLOSED",
            entered_at=session.entered_at,
            message=f"نشست بسته شده است ({session.exit_reason}) / Session is closed ({session.exit_reason})"
        )

    return CustomerSessionStatusResponse(
        valid=True,
        session_id=session.id,
        status="ACTIVE",
        entered_at=session.entered_at,
        message="جلسه فعال است / Session is active"
    )


@router.get("/api/customer/cart")
def get_customer_cart(
    secret: str = Query(..., description="Customer session secret"),
    db: Session = Depends(get_db)
):
    """Retrieve the current live cart for a customer session."""
    session = db.query(CustomerSession).filter_by(session_secret=secret).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return get_cart_summary(db, session.id)


def format_invoice_dict(invoice: Invoice) -> dict:
    """Format an Invoice ORM instance into a JSON-serializable dictionary."""
    return {
        "id": invoice.id,
        "session_id": invoice.session_id,
        "total": invoice.total,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "lines": [
            {
                "id": line.id,
                "product_name": line.product_name,
                "unit_price": line.unit_price,
                "quantity": line.quantity,
                "line_total": line.line_total,
            }
            for line in invoice.lines
        ],
    }


@router.post("/api/customer/checkout")
async def customer_checkout(
    payload: Optional[CheckoutRequest] = None,
    secret: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Simulated customer checkout and invoice generation in an atomic transaction."""
    session_secret = (payload.secret if payload and payload.secret else None) or secret
    if not session_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session secret is required")

    # 1. Lock and validate session
    cust_session = db.query(CustomerSession).filter_by(session_secret=session_secret).first()
    if not cust_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Idempotency check: if already closed, check if already invoiced (prevent duplicate invoices)
    if cust_session.status != "ACTIVE":
        existing_invoice = db.query(Invoice).filter_by(session_id=cust_session.id).first()
        if existing_invoice:
            return {
                "success": True,
                "message": "پرداخت قبلاً انجام شده است / Checkout already completed",
                "invoice": format_invoice_dict(existing_invoice),
            }
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این نشست بسته شده است / Session is already closed"
        )

    # 2. Check if cart is empty
    cart_items = db.query(CartItem).filter_by(session_id=cust_session.id).all()
    if not cart_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="سبد خرید خالی است. برای خروج بدون پرداخت از دکمه 'خروج بدون خرید' استفاده کنید."
        )

    now = utc_now()

    # 3. Record CHECKOUT_STARTED event
    start_evt = Event(
        event_uid=f"checkout_start_{cust_session.id}_{int(now.timestamp() * 1000)}",
        type="CHECKOUT_STARTED",
        session_id=cust_session.id,
        confidence=1.0,
        status="PROCESSED",
        created_at=now,
    )
    db.add(start_evt)

    # 4. Copy product names and prices snapshot into Invoice and InvoiceLine items
    invoice_lines = []
    total_amount = 0

    for item in cart_items:
        prod = db.query(Product).filter_by(id=item.product_id).first()
        prod_name = prod.name if prod else f"Product #{item.product_id}"
        unit_price = prod.unit_price if prod else 0
        line_total = unit_price * item.quantity
        total_amount += line_total

        line = InvoiceLine(
            product_name=prod_name,
            unit_price=unit_price,
            quantity=item.quantity,
            line_total=line_total,
        )
        invoice_lines.append(line)

    invoice = Invoice(
        session_id=cust_session.id,
        total=total_amount,
        created_at=now,
        lines=invoice_lines,
    )
    db.add(invoice)
    db.flush()

    # 5. Record INVOICE_CREATED event
    inv_evt = Event(
        event_uid=f"inv_created_{invoice.id}",
        type="INVOICE_CREATED",
        session_id=cust_session.id,
        confidence=1.0,
        status="PROCESSED",
        created_at=now,
    )
    db.add(inv_evt)

    # 6. Close customer session
    cust_session.status = "CLOSED"
    cust_session.exited_at = now
    cust_session.exit_reason = "CHECKOUT"

    # 7. Record SESSION_CLOSED event
    close_evt = Event(
        event_uid=f"sess_closed_{cust_session.id}_{int(now.timestamp() * 1000)}",
        type="SESSION_CLOSED",
        session_id=cust_session.id,
        confidence=1.0,
        status="PROCESSED",
        created_at=now,
    )
    db.add(close_evt)

    db.commit()
    db.refresh(invoice)
    db.refresh(cust_session)

    invoice_data = format_invoice_dict(invoice)

    # 8. WebSockets Notifications
    # Notify customer phone
    await manager.broadcast_to_customer(session_secret, {
        "type": "SESSION_CLOSED",
        "exit_reason": "CHECKOUT",
        "invoice": invoice_data,
    })

    # Notify admin dashboard
    await manager.broadcast_to_admins({
        "type": "SESSION_CLOSED",
        "session_id": cust_session.id,
        "exit_reason": "CHECKOUT",
        "exited_at": cust_session.exited_at.isoformat(),
        "invoice_id": invoice.id,
        "total": invoice.total,
    })
    await manager.broadcast_to_admins({
        "type": "EVENT_CREATED",
        "event": {
            "id": inv_evt.id,
            "event_uid": inv_evt.event_uid,
            "type": "INVOICE_CREATED",
            "session_id": cust_session.id,
            "confidence": 1.0,
            "status": "PROCESSED",
            "created_at": inv_evt.created_at.isoformat(),
        },
    })

    return {
        "success": True,
        "message": "پرداخت با موفقیت انجام شد / Checkout successful",
        "invoice": invoice_data,
    }


@router.post("/api/customer/exit-empty")
async def customer_exit_empty(
    payload: Optional[CheckoutRequest] = None,
    secret: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Exit store without purchase when cart is empty."""
    session_secret = (payload.secret if payload and payload.secret else None) or secret
    if not session_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session secret is required")

    cust_session = db.query(CustomerSession).filter_by(session_secret=session_secret).first()
    if not cust_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if cust_session.status != "ACTIVE":
        return {"success": True, "message": "Session already closed"}

    # Ensure cart is empty
    cart_count = db.query(CartItem).filter_by(session_id=cust_session.id).count()
    if cart_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="سبد خرید شما شامل اقلامی است. لطفاً کالاها را به قفسه بازگردانید یا پرداخت نمایید."
        )

    now = utc_now()
    cust_session.status = "CLOSED"
    cust_session.exited_at = now
    cust_session.exit_reason = "EMPTY_EXIT"

    close_evt = Event(
        event_uid=f"sess_closed_empty_{cust_session.id}_{int(now.timestamp() * 1000)}",
        type="SESSION_CLOSED",
        session_id=cust_session.id,
        confidence=1.0,
        status="PROCESSED",
        created_at=now,
    )
    db.add(close_evt)
    db.commit()

    await manager.broadcast_to_customer(session_secret, {
        "type": "SESSION_CLOSED",
        "exit_reason": "EMPTY_EXIT",
    })
    await manager.broadcast_to_admins({
        "type": "SESSION_CLOSED",
        "session_id": cust_session.id,
        "exit_reason": "EMPTY_EXIT",
        "exited_at": cust_session.exited_at.isoformat(),
    })

    return {"success": True, "message": "خروج بدون خرید ثبت شد"}
