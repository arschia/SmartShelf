import io
import pytest
from backend.app.config import settings
from backend.app.models import Product, Zone
from backend.app.services.auth import create_admin_token


@pytest.fixture
def auth_headers():
    token = create_admin_token()
    return {"Authorization": f"Bearer {token}"}


def test_admin_login_success(client):
    """Test login with the correct configured ADMIN_PIN and Persian/Arabic digits."""
    response = client.post("/api/admin/login", json={"pin": settings.ADMIN_PIN})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert len(data["token"]) > 20
    assert "admin_token" in response.cookies

    # Test that Persian digits are converted and accepted
    if settings.ADMIN_PIN == "1234":
        persian_resp = client.post("/api/admin/login", json={"pin": "۱۲۳۴"})
        assert persian_resp.status_code == 200
        arabic_resp = client.post("/api/admin/login", json={"pin": "١٢٣٤"})
        assert arabic_resp.status_code == 200


def test_admin_login_wrong_pin(client):
    """Test login failure with an incorrect PIN."""
    response = client.post("/api/admin/login", json={"pin": "WRONG_PIN_999"})
    assert response.status_code == 401
    assert "Incorrect admin PIN" in response.json()["detail"]


def test_admin_routes_require_authentication(client):
    """Test that admin endpoints reject unauthenticated requests with 401."""
    # List products without auth header
    response = client.get("/api/admin/products")
    assert response.status_code == 401

    # Zones without auth header
    response = client.get("/api/admin/zones")
    assert response.status_code == 401


def test_product_crud_flow(client, auth_headers):
    """Test full Create, Read, Update, Delete flow for products."""
    # 1. Create
    new_product_payload = {
        "sku": "CHIPS-001",
        "name": "چیپس نمکی (Salted Chips)",
        "description": "چیپس ترد نمکی ۶۰ گرمی",
        "unit_price": 28000,
        "is_active": True,
    }
    create_res = client.post("/api/admin/products", json=new_product_payload, headers=auth_headers)
    assert create_res.status_code == 201
    prod_data = create_res.json()
    prod_id = prod_data["id"]
    assert prod_data["sku"] == "CHIPS-001"
    assert prod_data["unit_price"] == 28000

    # 2. Read Single
    get_res = client.get(f"/api/admin/products/{prod_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "چیپس نمکی (Salted Chips)"

    # 3. Read List
    list_res = client.get("/api/admin/products", headers=auth_headers)
    assert list_res.status_code == 200
    skus = [p["sku"] for p in list_res.json()]
    assert "CHIPS-001" in skus

    # 4. Update
    update_payload = {
        "name": "چیپس فلفلی (Pepper Chips)",
        "unit_price": 30000,
    }
    put_res = client.put(f"/api/admin/products/{prod_id}", json=update_payload, headers=auth_headers)
    assert put_res.status_code == 200
    assert put_res.json()["name"] == "چیپس فلفلی (Pepper Chips)"
    assert put_res.json()["unit_price"] == 30000

    # 5. Delete
    del_res = client.delete(f"/api/admin/products/{prod_id}", headers=auth_headers)
    assert del_res.status_code == 200

    # Verify gone
    get_after = client.get(f"/api/admin/products/{prod_id}", headers=auth_headers)
    assert get_after.status_code == 404


def test_product_validation_rules(client, auth_headers):
    """Test validation constraints: price > 0, non-empty name, unique SKU."""
    # Price <= 0 must fail
    res_zero_price = client.post(
        "/api/admin/products",
        json={"sku": "V-001", "name": "Item", "unit_price": 0},
        headers=auth_headers,
    )
    assert res_zero_price.status_code == 422

    res_negative_price = client.post(
        "/api/admin/products",
        json={"sku": "V-002", "name": "Item", "unit_price": -500},
        headers=auth_headers,
    )
    assert res_negative_price.status_code == 422

    # Empty name must fail
    res_empty_name = client.post(
        "/api/admin/products",
        json={"sku": "V-003", "name": "", "unit_price": 1000},
        headers=auth_headers,
    )
    assert res_empty_name.status_code == 422

    # Duplicate SKU must fail with 400
    res1 = client.post(
        "/api/admin/products",
        json={"sku": "UNIQUE-SKU", "name": "First Item", "unit_price": 10000},
        headers=auth_headers,
    )
    assert res1.status_code == 201

    res2 = client.post(
        "/api/admin/products",
        json={"sku": "UNIQUE-SKU", "name": "Second Item", "unit_price": 12000},
        headers=auth_headers,
    )
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"]


def test_zone_assignment_and_slots(client, db_session, auth_headers):
    """Test listing zones and assigning/unassigning products to physical slots."""
    # Create product and zone in DB
    product = Product(sku="ZONE-P1", name="Slot Product 1", unit_price=12000)
    zone = Zone(name="جایگاه تست (Test Slot)", roi_x=10, roi_y=10, roi_w=50, roi_h=50, state="EMPTY")
    db_session.add_all([product, zone])
    db_session.commit()

    # List zones
    zones_res = client.get("/api/admin/zones", headers=auth_headers)
    assert zones_res.status_code == 200
    zone_ids = [z["id"] for z in zones_res.json()]
    assert zone.id in zone_ids

    # Assign product to zone
    assign_res = client.put(
        f"/api/admin/zones/{zone.id}/assign",
        json={"product_id": product.id},
        headers=auth_headers,
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["product_id"] == product.id
    assert assign_res.json()["state"] == "FULL"

    # Unassign product
    unassign_res = client.put(
        f"/api/admin/zones/{zone.id}/assign",
        json={"product_id": None},
        headers=auth_headers,
    )
    assert unassign_res.status_code == 200
    assert unassign_res.json()["product_id"] is None
    assert unassign_res.json()["state"] == "EMPTY"


def test_image_upload_and_validation(client, auth_headers):
    """Test image upload endpoint and rejection of invalid file extensions."""
    # Valid PNG image upload
    file_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    files = {"file": ("test_product.png", io.BytesIO(file_content), "image/png")}

    upload_res = client.post("/api/admin/products/upload-image", files=files, headers=auth_headers)
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert "image_path" in data
    assert data["image_path"].startswith("/static/uploads/")
    assert data["image_path"].endswith(".png")

    # Invalid extension (e.g. .exe)
    bad_files = {"file": ("malicious.exe", io.BytesIO(b"executable"), "application/x-msdownload")}
    bad_res = client.post("/api/admin/products/upload-image", files=bad_files, headers=auth_headers)
    assert bad_res.status_code == 400
    assert "Unsupported file format" in bad_res.json()["detail"]
