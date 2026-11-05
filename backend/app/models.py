from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    LargeBinary
)
from sqlalchemy.orm import relationship
from .db import Base


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    gtin = Column(String(20), nullable=True)
    gtin14 = Column(String(14), unique=True, index=True, nullable=True)
    brand = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    image_path = Column(String(255), nullable=True)
    unit_price = Column(Integer, nullable=False)  # Stored as integer to avoid rounding issues
    is_active = Column(Boolean, default=True, nullable=False)
    stock_quantity = Column(Integer, default=0, nullable=False)

    zones = relationship("Zone", back_populates="product", foreign_keys="[Zone.product_id]")
    cart_items = relationship("CartItem", back_populates="product")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    embeddings = relationship("ProductEmbedding", back_populates="product", cascade="all, delete-orphan")


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    product = relationship("Product", back_populates="images")
    embeddings = relationship("ProductEmbedding", back_populates="image", cascade="all, delete-orphan")


class ProductEmbedding(Base):
    __tablename__ = "product_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    image_id = Column(Integer, ForeignKey("product_images.id", ondelete="CASCADE"), nullable=True, index=True)
    vector = Column(LargeBinary, nullable=False)
    model_version = Column(String(50), nullable=False, default="mobilenetv2-7")
    created_at = Column(DateTime, default=utc_now, nullable=False)

    product = relationship("Product", back_populates="embeddings")
    image = relationship("ProductImage", back_populates="embeddings")


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    roi_x = Column(Float, default=0.0, nullable=False)
    roi_y = Column(Float, default=0.0, nullable=False)
    roi_w = Column(Float, default=0.0, nullable=False)
    roi_h = Column(Float, default=0.0, nullable=False)
    state = Column(String(20), default="EMPTY", nullable=False)  # PRESENT | ABSENT | TRANSITION
    confidence = Column(Float, default=1.0, nullable=False)
    ref_full_features = Column(Text, nullable=True)
    ref_empty_features = Column(Text, nullable=True)
    recognized_product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    recognition_status = Column(String(30), default="UNKNOWN", nullable=False)  # RECOGNIZED | UNKNOWN | NEEDS_REVIEW
    recognition_score = Column(Float, default=0.0, nullable=False)
    last_recognized_at = Column(DateTime, nullable=True)
    last_picked_product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    product = relationship("Product", foreign_keys=[product_id], back_populates="zones")
    recognized_product = relationship("Product", foreign_keys=[recognized_product_id])
    last_picked_product = relationship("Product", foreign_keys=[last_picked_product_id])


class EntryToken(Base):
    __tablename__ = "entry_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(100), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class ShopScenario(Base):
    """One-bottle university scenario. Persists stock and who owns the outstanding pick."""
    __tablename__ = "shop_scenario"
    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, default=False, nullable=False)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    camera_source = Column(String(20), default="browser", nullable=False)
    stock_quantity = Column(Integer, nullable=True)
    pick_session_id = Column(Integer, ForeignKey("customer_sessions.id"), nullable=True)
    generation = Column(Integer, default=0, nullable=False)
    needs_review = Column(Boolean, default=False, nullable=False)


class CustomerSession(Base):
    __tablename__ = "customer_sessions"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(20), default="ACTIVE", nullable=False)  # ACTIVE | CLOSED
    entered_at = Column(DateTime, default=utc_now, nullable=False)
    exited_at = Column(DateTime, nullable=True)
    exit_reason = Column(String(20), nullable=True)  # CHECKOUT | ADMIN | EXPIRED
    session_secret = Column(String(100), unique=True, index=True, nullable=False)

    cart_items = relationship("CartItem", back_populates="session", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="session")
    events = relationship("Event", back_populates="session")


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("customer_sessions.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)

    session = relationship("CustomerSession", back_populates="cart_items")
    product = relationship("Product", back_populates="cart_items")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    event_uid = Column(String(100), unique=True, index=True, nullable=False)
    type = Column(String(50), nullable=False)
    session_id = Column(Integer, ForeignKey("customer_sessions.id"), nullable=True)
    device_id = Column(String(50), nullable=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    confidence = Column(Float, default=1.0, nullable=False)
    status = Column(String(20), default="PROCESSED", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    session = relationship("CustomerSession", back_populates="events")
    zone = relationship("Zone")
    product = relationship("Product")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("customer_sessions.id"), nullable=False)
    total = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    session = relationship("CustomerSession", back_populates="invoices")
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    product_name = Column(String(100), nullable=False)
    unit_price = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    line_total = Column(Integer, nullable=False)

    invoice = relationship("Invoice", back_populates="lines")


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), unique=True, index=True, nullable=False)
    role = Column(String(20), nullable=False)  # CAMERA | CUSTOMER | ADMIN
    last_seen = Column(DateTime, default=utc_now, nullable=False)
    is_online = Column(Boolean, default=True, nullable=False)
