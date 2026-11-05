from backend.app.models import Product
from backend.app.services.seed import seed_store_data


def test_admin_can_list_unpriced_inactive_startup_product(client, db_session, auth_headers):
    seed_store_data(db_session)
    response = client.get('/api/admin/products', headers=auth_headers)
    assert response.status_code == 200
    product = response.json()[0]
    assert product['sku'] == 'HEJOO-PEACH-001'
    assert product['unit_price'] == 0
    assert product['is_active'] is False


def test_startup_product_needs_real_price_before_activation(client, db_session, auth_headers):
    seed_store_data(db_session)
    product = db_session.query(Product).one()
    response = client.put(f'/api/admin/products/{product.id}', json={'is_active': True}, headers=auth_headers)
    assert response.status_code == 400
    db_session.refresh(product)
    assert product.is_active is False
    response = client.put(f'/api/admin/products/{product.id}', json={'is_active': True, 'unit_price': 25000}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()['is_active'] is True
    assert response.json()['unit_price'] == 25000
