from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = "ok"


# ---------------------------------------------------------------------------
# Admin Auth Schemas
# ---------------------------------------------------------------------------

class AdminLoginRequest(BaseModel):
    pin: str = Field(..., min_length=1, description="Admin PIN code")


class AdminLoginResponse(BaseModel):
    token: str
    message: str = "Login successful"


# ---------------------------------------------------------------------------
# Product Schemas
# ---------------------------------------------------------------------------

class ProductImageResponse(BaseModel):
    id: int
    product_id: int
    file_path: str
    is_primary: bool
    width: Optional[int] = None
    height: Optional[int] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ProductBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50, description="Unique product SKU")
    name: str = Field(..., min_length=1, max_length=100, description="Product name")
    gtin: Optional[str] = Field(None, description="GS1 Barcode string preserving leading zeros")
    gtin14: Optional[str] = Field(None, max_length=14, description="Normalized 14-digit GTIN")
    brand: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    image_path: Optional[str] = None
    unit_price: int = Field(..., gt=0, description="Unit price in local currency, must be > 0")
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    gtin: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = Field(None, max_length=500)
    image_path: Optional[str] = None
    unit_price: Optional[int] = Field(None, gt=0)
    is_active: Optional[bool] = None


class ProductResponse(ProductBase):
    # A production seed is intentionally unpriced and inactive until setup.
    # Request schemas still require positive prices for new/updated products.
    unit_price: int = Field(..., ge=0)
    id: int
    stock_quantity: int = 0
    assigned_zones: List[str] = []
    images: List[ProductImageResponse] = []
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Zone Schemas
# ---------------------------------------------------------------------------

class ZoneBase(BaseModel):
    name: str
    product_id: Optional[int] = None
    roi_x: float = 0.0
    roi_y: float = 0.0
    roi_w: float = 0.0
    roi_h: float = 0.0
    state: str = "PRESENT"
    confidence: float = 1.0
    recognized_product_id: Optional[int] = None
    recognition_status: str = "UNKNOWN"
    recognition_score: float = 0.0


class ZoneRoiUpdate(BaseModel):
    roi_x: float = Field(..., ge=0.0, le=1.0)
    roi_y: float = Field(..., ge=0.0, le=1.0)
    roi_w: float = Field(..., gt=0.0, le=1.0)
    roi_h: float = Field(..., gt=0.0, le=1.0)


class ZoneReferenceCaptureRequest(BaseModel):
    reference_type: str = Field(..., description="FULL or EMPTY")


class ZoneAssignRequest(BaseModel):
    product_id: Optional[int] = Field(None, description="Product ID to assign, or null to unassign")


class ZoneManualCorrectionRequest(BaseModel):
    product_id: int = Field(..., description="Correct product ID to map and train from current zone image")


class ZoneResponse(ZoneBase):
    id: int
    updated_at: datetime
    product: Optional[ProductBase] = None
    recognized_product: Optional[ProductBase] = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Customer Session Schemas
# ---------------------------------------------------------------------------

class SessionResponse(BaseModel):
    id: int
    status: str
    entered_at: datetime
    exited_at: Optional[datetime] = None
    exit_reason: Optional[str] = None
    duration_seconds: Optional[int] = None
    invoice_id: Optional[int] = None
    invoice_total: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class EntryTokenResponse(BaseModel):
    active_session: bool
    token: Optional[str] = None
    expires_in: Optional[int] = None
    enter_url: Optional[str] = None
    message: Optional[str] = None


class CustomerSessionStatusResponse(BaseModel):
    valid: bool
    session_id: Optional[int] = None
    status: Optional[str] = None
    entered_at: Optional[datetime] = None
    message: Optional[str] = None


class DeviceResponse(BaseModel):
    id: int
    device_id: str
    role: str
    last_seen: datetime
    is_online: bool
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Invoice & Checkout Schemas (Phase 7)
# ---------------------------------------------------------------------------

class InvoiceLineResponse(BaseModel):
    id: int
    product_name: str
    unit_price: int
    quantity: int
    line_total: int
    model_config = ConfigDict(from_attributes=True)


class InvoiceResponse(BaseModel):
    id: int
    session_id: int
    total: int
    created_at: datetime
    lines: List[InvoiceLineResponse] = []
    model_config = ConfigDict(from_attributes=True)


class CheckoutRequest(BaseModel):
    secret: Optional[str] = None


class CheckoutResponse(BaseModel):
    success: bool
    message: str
    invoice: Optional[InvoiceResponse] = None


# ---------------------------------------------------------------------------
# Camera Pairing Schemas (Phase 2)
# ---------------------------------------------------------------------------

class CameraPairRequest(BaseModel):
    code: Optional[str] = Field(None, max_length=64)
    pairing_code: Optional[str] = Field(None, max_length=64)
    device_id: str = Field(..., min_length=1, max_length=64, description="Tablet device identifier")

    @property
    def clean_code(self) -> str:
        return (self.code or self.pairing_code or "").strip()


class CameraPairResponse(BaseModel):
    device_token: str
    device_id: str
    message: str = "Device paired successfully"


# ---------------------------------------------------------------------------
# Customer Entry API Schemas (Phase 3)
# ---------------------------------------------------------------------------

class CustomerEnterRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=128, description="QR entry token")


class CustomerEnterResponse(BaseModel):
    session_secret: str
    session_id: int
    status: str = "ACTIVE"
    entered_at: str
    message: str = "ورود با موفقیت انجام شد / Successfully entered"

