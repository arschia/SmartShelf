from sqlalchemy.orm import Session
from ..models import Product, Zone


def seed_initial_data(db: Session) -> dict:
    """Seed 3 demo products for tests/development only; production uses seed_store_data."""
    # Check if products already exist
    existing_products = db.query(Product).count()
    created_products = []
    created_zones = []

    if existing_products == 0:
        sample_products = [
            Product(
                sku="PROD-001",
                name="شیر کاکائو (Chocolate Milk)",
                description="شیر کاکائو فرادما ۲۵۰ میلی‌لیتر",
                image_path="/static/images/chocolate_milk.png",
                unit_price=35000,
                is_active=True,
            ),
            Product(
                sku="PROD-002",
                name="آب معدنی (Mineral Water)",
                description="آب معدنی طبیعی ۵۰۰ میلی‌لیتر",
                image_path="/static/images/water.png",
                unit_price=15000,
                is_active=True,
            ),
            Product(
                sku="PROD-003",
                name="بیسکویت شکلاتی (Chocolate Biscuit)",
                description="بیسکویت کرمدار کاکائویی",
                image_path="/static/images/biscuit.png",
                unit_price=45000,
                is_active=True,
            ),
        ]
        db.add_all(sample_products)
        db.commit()
        for p in sample_products:
            db.refresh(p)
        created_products = sample_products
    else:
        created_products = db.query(Product).order_by(Product.id).limit(3).all()

    # Check if zones already exist
    existing_zones = db.query(Zone).count()
    if existing_zones == 0 and len(created_products) >= 3:
        sample_zones = [
            Zone(
                name="جایگاه ۱ (Slot 1)",
                product_id=created_products[0].id,
                roi_x=0.08,
                roi_y=0.20,
                roi_w=0.25,
                roi_h=0.60,
                state="FULL",
                confidence=1.0,
            ),
            Zone(
                name="جایگاه ۲ (Slot 2)",
                product_id=created_products[1].id,
                roi_x=0.375,
                roi_y=0.20,
                roi_w=0.25,
                roi_h=0.60,
                state="FULL",
                confidence=1.0,
            ),
            Zone(
                name="جایگاه ۳ (Slot 3)",
                product_id=created_products[2].id,
                roi_x=0.67,
                roi_y=0.20,
                roi_w=0.25,
                roi_h=0.60,
                state="FULL",
                confidence=1.0,
            ),
        ]
        db.add_all(sample_zones)
        db.commit()
        for z in sample_zones:
            db.refresh(z)
        created_zones = sample_zones
    else:
        created_zones = db.query(Zone).order_by(Zone.id).limit(3).all()

    return {
        "products": created_products,
        "zones": created_zones,
    }

def seed_store_data(db: Session) -> dict:
    """Create a production-safe store layout: only Hejoo Peach, no demo beverages/snacks.

    The product is deliberately inactive and priced at zero until the owner enters the
    real selling price and confirms the product details in the admin panel. Three fixed
    zones are kept, but only the first zone is assigned to this one product.
    """
    existing_products = db.query(Product).count()
    hejoo = db.query(Product).filter_by(sku="HEJOO-PEACH-001").first()

    if existing_products == 0:
        hejoo = Product(
            sku="HEJOO-PEACH-001",
            name="دلستر هی‌جو هلو",
            description="محصول اولیه SmartShelf؛ قیمت فروش و جزئیات نهایی باید توسط مدیر تأیید شود.",
            image_path="/assets/img/heyjo_peach.png",
            unit_price=0,
            is_active=False,
        )
        db.add(hejoo)
        db.commit()
        db.refresh(hejoo)

    existing_zones = db.query(Zone).count()
    created_zones = []
    if existing_zones == 0:
        assigned_product_id = hejoo.id if hejoo is not None else None
        zones = [
            Zone(
                name="جایگاه ۱ — دلستر هی‌جو هلو",
                product_id=assigned_product_id,
                roi_x=0.08, roi_y=0.20, roi_w=0.25, roi_h=0.60,
                state="UNKNOWN", confidence=0.0,
            ),
            Zone(
                name="جایگاه ۲ — خالی", product_id=None,
                roi_x=0.375, roi_y=0.20, roi_w=0.25, roi_h=0.60,
                state="EMPTY", confidence=1.0,
            ),
            Zone(
                name="جایگاه ۳ — خالی", product_id=None,
                roi_x=0.67, roi_y=0.20, roi_w=0.25, roi_h=0.60,
                state="EMPTY", confidence=1.0,
            ),
        ]
        db.add_all(zones)
        db.commit()
        for zone in zones:
            db.refresh(zone)
        created_zones = zones
    else:
        created_zones = db.query(Zone).order_by(Zone.id).all()

    products = db.query(Product).order_by(Product.id).all()
    return {"products": products, "zones": created_zones}

