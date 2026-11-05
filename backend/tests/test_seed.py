from backend.app.models import Product, Zone
from backend.app.services.seed import seed_initial_data


def test_seed_initial_data_creates_3_products_and_3_zones(db_session):
    """Test that seed_initial_data populates exactly 3 products and 3 zones."""
    assert db_session.query(Product).count() == 0
    assert db_session.query(Zone).count() == 0

    result = seed_initial_data(db_session)

    assert len(result["products"]) == 3
    assert len(result["zones"]) == 3

    products = db_session.query(Product).all()
    assert len(products) == 3
    for p in products:
        assert p.unit_price > 0
        assert p.is_active is True

    zones = db_session.query(Zone).all()
    assert len(zones) == 3
    for z in zones:
        assert z.product_id is not None
        assert z.product is not None
        assert z.state == "FULL"


def test_seed_initial_data_is_idempotent(db_session):
    """Test that running seed_initial_data multiple times does not duplicate data."""
    seed_initial_data(db_session)
    assert db_session.query(Product).count() == 3
    assert db_session.query(Zone).count() == 3

    # Run a second time
    second_result = seed_initial_data(db_session)
    assert len(second_result["products"]) == 3
    assert len(second_result["zones"]) == 3
    assert db_session.query(Product).count() == 3
    assert db_session.query(Zone).count() == 3
