from backend.app.models import Product, Zone
from backend.app.services.seed import seed_store_data


def test_store_seed_contains_only_hejoo_peach_and_three_fixed_slots(db_session):
    result = seed_store_data(db_session)
    products = db_session.query(Product).all()
    zones = db_session.query(Zone).order_by(Zone.id).all()

    assert len(products) == 1
    assert products[0].sku == "HEJOO-PEACH-001"
    assert products[0].name == "دلستر هی‌جو هلو"
    assert products[0].unit_price == 0
    assert products[0].is_active is False
    assert len(zones) == 3
    assert zones[0].product_id == products[0].id
    assert zones[1].product_id is None
    assert zones[2].product_id is None
    assert zones[0].state == "UNKNOWN"
    assert len(result["products"]) == 1


def test_store_seed_is_idempotent(db_session):
    seed_store_data(db_session)
    seed_store_data(db_session)
    assert db_session.query(Product).count() == 1
    assert db_session.query(Zone).count() == 3
