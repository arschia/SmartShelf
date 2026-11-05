"""Camera Pairing and Device Token Service for Tablet Sensor Authentication."""
import time
import secrets
import re
import json
import base64
import hmac
import hashlib
from typing import Dict, Optional
from threading import Lock

# In-memory storage for 6-digit pairing codes: code -> expiry_timestamp
_pairing_codes: Dict[str, float] = {}

# Active device tokens: token -> {"device_id": str, "created_at": float}
_device_tokens: Dict[str, dict] = {}

_lock = Lock()
DEVICE_TOKEN_TTL = 30 * 86400


def _signed_device_token(device_id, now):
    from ..config import settings
    raw = json.dumps({"device_id":device_id,"created_at":int(now),"nonce":secrets.token_hex(12)},separators=(",",":")).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(settings.SECRET_KEY.encode(),("cam1."+body).encode(),hashlib.sha256).hexdigest()
    return "cam1."+body+"."+signature


def _signed_device_info(token):
    from ..config import settings
    try:
        prefix,body,signature=token.split(".")
        expected=hmac.new(settings.SECRET_KEY.encode(),("cam1."+body).encode(),hashlib.sha256).hexdigest()
        if prefix!="cam1" or not secrets.compare_digest(signature,expected):return None
        info=json.loads(base64.urlsafe_b64decode(body+"="*((-len(body))%4)))
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,50}",info["device_id"]):return None
        age=time.time()-info["created_at"]
        return info if -60<=age<=DEVICE_TOKEN_TTL else None
    except (ValueError,TypeError,KeyError,UnicodeError):
        return None


def create_camera_pairing_code(validity_seconds: int = 300) -> str:
    """Generate a 6-digit pairing code valid for 5 minutes."""
    now = time.time()
    code = f"{secrets.randbelow(900000) + 100000}"
    with _lock:
        # Purge expired codes
        expired = [c for c, exp in _pairing_codes.items() if now >= exp]
        for c in expired:
            _pairing_codes.pop(c, None)

        _pairing_codes[code] = now + validity_seconds
    return code


def exchange_pairing_code_for_token(code: str, device_id: str) -> Optional[str]:
    """Validate 6-digit pairing code and return a unique device_token."""
    now = time.time()
    digit_map = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    clean_code = re.sub(r'[\s\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff]', '', str(code).translate(digit_map))
    if re.fullmatch(r'[0-9]{6}', clean_code) is None:
        return None
    with _lock:
        exp = _pairing_codes.get(clean_code)
        if not exp or now >= exp:
            return None

        # One-time use: consume code immediately
        _pairing_codes.pop(clean_code, None)

        device_token = _signed_device_token(device_id, now)
        _device_tokens[device_token] = {
            "device_id": device_id,
            "created_at": now,
        }
        return device_token


def is_camera_device_token_valid(device_token: Optional[str]) -> bool:
    """Check if provided device_token is valid and active."""
    if not device_token:
        return False
    if device_token.startswith("cam1."):
        return _signed_device_info(device_token) is not None
    with _lock:
        return device_token in _device_tokens


def get_device_info_by_token(device_token: Optional[str]) -> Optional[dict]:
    """Retrieve registered device info for a valid token."""
    if not device_token:
        return None
    if device_token.startswith("cam1."):
        return _signed_device_info(device_token)
    with _lock:
        return _device_tokens.get(device_token)
