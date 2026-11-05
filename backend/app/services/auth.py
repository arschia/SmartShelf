"""Admin Authentication Service with HMAC-SHA256 Token Signing and Brute-Force Lockout."""
import time
import json
import base64
import hmac
import hashlib
import secrets
from typing import Optional, Dict, List
from threading import Lock
from fastapi import Request, HTTPException, status
from ..config import settings

# Thread-safe in-memory brute force tracker: client_ip -> list of failure timestamps
_failed_attempts: Dict[str, List[float]] = {}
_lockout_until: Dict[str, float] = {}
_auth_lock = Lock()


def get_client_ip(request: Request) -> str:
    """Extract client IP, considering trusted proxies if TRUST_PROXY is enabled."""
    if settings.TRUST_PROXY:
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def check_admin_lockout(request: Request):
    """Check if the requesting IP is currently locked out due to repeated failed PIN attempts."""
    ip = get_client_ip(request)
    now = time.time()
    with _auth_lock:
        lock_time = _lockout_until.get(ip, 0)
        if now < lock_time:
            remaining = int(lock_time - now)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"قفل موقت به دلیل تلاش‌های ناموفق مکرر. لطفاً {remaining} ثانیه دیگر دوباره تلاش کنید. / Account temporarily locked. Try again in {remaining}s."
            )


def record_failed_login(request: Request):
    """Record a failed PIN attempt; trigger a 10-minute lockout after 5 failures in 10 minutes."""
    ip = get_client_ip(request)
    now = time.time()
    with _auth_lock:
        attempts = [t for t in _failed_attempts.get(ip, []) if now - t <= 600]
        attempts.append(now)
        _failed_attempts[ip] = attempts
        if len(attempts) >= 5:
            _lockout_until[ip] = now + 600  # 10 minutes lockout


def record_successful_login(request: Request):
    """Clear failed attempts for this IP on successful login."""
    ip = get_client_ip(request)
    with _auth_lock:
        _failed_attempts.pop(ip, None)
        _lockout_until.pop(ip, None)


_DIGIT_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(text: str) -> str:
    """Convert Eastern Arabic and Persian digits to standard ASCII digits."""
    if not text:
        return ""
    return str(text).translate(_DIGIT_TRANS)


def verify_admin_pin(pin: str) -> bool:
    """Compare provided PIN securely with configured ADMIN_PIN."""
    if not pin or not settings.ADMIN_PIN:
        return False
    clean_pin = normalize_digits(str(pin).strip())
    clean_expected = normalize_digits(str(settings.ADMIN_PIN).strip())
    return secrets.compare_digest(clean_pin.encode("utf-8"), clean_expected.encode("utf-8"))


def create_admin_token(
    expires_in_seconds: Optional[int] = None,
    expires_in_hours: Optional[int] = None,
) -> str:
    """Create a stateless, cryptographically signed HMAC-SHA256 admin token.

    ``expires_in_hours`` is retained for compatibility with the existing test suite
    and older internal callers; production routes use TOKEN_TTL_SECONDS.
    """
    if expires_in_hours is not None:
        ttl = int(expires_in_hours) * 3600
    else:
        ttl = int(expires_in_seconds if expires_in_seconds is not None else settings.TOKEN_TTL_SECONDS)
    if ttl < 60 or ttl > 86400:
        raise ValueError("TOKEN_TTL_SECONDS must be between 60 and 86400 seconds")
    now = int(time.time())
    payload = {
        "sub": "admin",
        "iat": now,
        "exp": now + ttl,
        "jti": secrets.token_hex(12),
    }
    payload_json = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode('ascii').rstrip('=')

    signature = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        payload_b64.encode('ascii'),
        hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode('ascii').rstrip('=')

    return f"{payload_b64}.{sig_b64}"


def revoke_admin_token(token: str):
    """No-op for stateless HMAC tokens or used for client logout."""
    pass


def is_admin_token_valid(token: Optional[str]) -> bool:
    """Verify HMAC signature and expiration timestamp of the admin token."""
    if not token or "." not in token:
        return False

    try:
        parts = token.split(".")
        if len(parts) != 2:
            return False
        payload_b64, sig_b64 = parts

        # Verify signature
        expected_sig = hmac.new(
            settings.SECRET_KEY.encode('utf-8'),
            payload_b64.encode('ascii'),
            hashlib.sha256
        ).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode('ascii').rstrip('=')

        if not secrets.compare_digest(sig_b64, expected_sig_b64):
            return False

        # Pad payload_b64
        rem = len(payload_b64) % 4
        padded = payload_b64 + ("=" * (4 - rem) if rem else "")
        payload_bytes = base64.urlsafe_b64decode(padded)
        payload = json.loads(payload_bytes.decode('utf-8'))

        if payload.get("sub") != "admin":
            return False
        if payload.get("exp", 0) < int(time.time()):
            return False

        return True
    except Exception:
        return False


def get_current_admin(request: Request) -> str:
    """FastAPI dependency to protect admin routes via Authorization: Bearer <token>."""
    token: Optional[str] = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    if not token:
        token = request.headers.get("X-Admin-Token")

    if not token:
        token = request.cookies.get("admin_token")

    if not is_admin_token_valid(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Admin token is missing, expired, or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token
