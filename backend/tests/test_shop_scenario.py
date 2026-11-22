import base64
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from backend.app.models import Product, Zone, CustomerSession, CartItem, Event, ShopScenario
from backend.app.services.seed import seed_initial_data
from backend.app.services import shop_scenario as service
from backend.app.routes import shop as routes
from backend.app.config import settings
from backend.app.services.auth import create_admin_token


@pytest.fixture
def demo(db_session,monkeypatch):
    data=seed_initial_data(db_session)
    clock=SimpleNamespace(value=0.)
    runtime=service.ShopRuntime(clock=lambda:clock.value)
    monkeypatch.setattr(service,'shop_runtime',runtime)
    monkeypatch.setattr(routes,'shop_runtime',runtime)
    monkeypatch.setattr(settings,'STORE_OPEN',False)
    cfg=ShopScenario(id=1,enabled=True,zone_id=data['zones'][0].id,product_id=data['products'][0].id,camera_source='browser',generation=1)
    db_session.add(cfg);db_session.commit()
    def feed(observation,n=3,source='browser:test',sequence=None):
        result=None
        for _ in range(n):
            result=runtime.observe(db_session,observation,.9,source,sequence)
            clock.value+=.65
        return result
    def customer():
        c=CustomerSession(session_secret='customer-'+str(db_session.query(CustomerSession).count()),status='ACTIVE')
        db_session.add(c);db_session.commit();return c
    return SimpleNamespace(db=db_session,cfg=cfg,clock=clock,runtime=runtime,feed=feed,customer=customer,product=data['products'][0])


def quantity(demo,customer):
    return sum(i.quantity for i in demo.db.query(CartItem).filter_by(session_id=customer.id))


def test_baseline_pick_return_and_duplicate_frames(demo):
    c=demo.customer();demo.feed('PRESENT')
    assert demo.cfg.stock_quantity==demo.product.stock_quantity==1 and quantity(demo,c)==0
    demo.feed('PRESENT',8)
    assert demo.product.stock_quantity==1
    demo.feed('ABSENT');assert demo.product.stock_quantity==0 and quantity(demo,c)==1
    demo.feed('ABSENT',8);assert quantity(demo,c)==1
    demo.feed('PRESENT');assert demo.product.stock_quantity==1 and quantity(demo,c)==0
    assert demo.db.query(Event).filter_by(type='PRODUCT_PICKED',status='PROCESSED').count()==1
    assert demo.db.query(Event).filter_by(type='PRODUCT_RETURNED',status='PROCESSED').count()==1


def test_no_customer_only_updates_stock(demo):
    demo.feed('PRESENT');demo.feed('ABSENT')
    assert demo.product.stock_quantity==0 and demo.db.query(CartItem).count()==0


def test_restock_after_empty_baseline_is_not_customer_return(demo):
    c=demo.customer();demo.feed('ABSENT');demo.feed('PRESENT')
    assert demo.product.stock_quantity==1 and quantity(demo,c)==0


def test_brief_occlusion_and_unknown_are_not_picks(demo):
    c=demo.customer();demo.feed('PRESENT');demo.feed('ABSENT',1);demo.feed('UNKNOWN',1);demo.feed('PRESENT',2)
    assert quantity(demo,c)==0 and demo.product.stock_quantity==1


def test_session_started_mid_absence_is_not_billed(demo):
    demo.feed('PRESENT');demo.feed('ABSENT',1);c=demo.customer();demo.feed('ABSENT',3)
    assert quantity(demo,c)==0 and demo.product.stock_quantity==0


def test_return_cannot_credit_the_next_customer(demo):
    old=demo.customer();demo.feed('PRESENT');demo.feed('ABSENT');old.status='CLOSED';demo.db.commit()
    new=demo.customer();demo.db.add(CartItem(session_id=new.id,product_id=demo.product.id,quantity=1));demo.db.commit()
    demo.feed('PRESENT')
    assert quantity(demo,new)==1 and quantity(demo,old)==1 and demo.product.stock_quantity==1


def test_restart_and_camera_gap_never_infer_a_purchase(demo):
    c=demo.customer();demo.feed('PRESENT');demo.runtime.reset();demo.feed('PRESENT')
    assert demo.product.stock_quantity==1 and quantity(demo,c)==0
    demo.clock.value+=10;demo.feed('ABSENT')
    assert demo.cfg.needs_review and quantity(demo,c)==0 and demo.product.stock_quantity==0


def test_duplicate_frame_ids_and_second_camera_are_ignored(demo):
    demo.feed('PRESENT',1,sequence=1);demo.clock.value+=1
    assert not demo.feed('PRESENT',1,sequence=1)['accepted']
    assert not demo.feed('PRESENT',1,source='browser:another',sequence=2)['accepted']
    assert demo.cfg.stock_quantity is None


def test_roi_ignores_background_bottle_and_ambiguous_count(demo,monkeypatch):
    zone=demo.db.get(Zone,demo.cfg.zone_id);zone.roi_x=.1;zone.roi_y=.1;zone.roi_w=.3;zone.roi_h=.8
    detections=[{'box':[.7,.1,.9,.8],'confidence':.95}]
    class Detector:
        def detect(self,*_args,**_kw):return {'detections':detections}
    monkeypatch.setattr(service,'get_bottle_detector',lambda:Detector())
    image=np.random.default_rng(42).integers(0,255,(100,100,3),dtype=np.uint8)
    assert demo.runtime.classify(image,demo.cfg,zone)[0]=='ABSENT'
    detections[:]=[{'box':[.15,.2,.3,.7],'confidence':.95}]*2
    assert demo.runtime.classify(image,demo.cfg,zone)[0]=='UNKNOWN'
    assert demo.runtime.classify(np.zeros_like(image),demo.cfg,zone)[0]=='UNKNOWN'


def test_demo_entry_tokens_are_six_digit_and_single_use(demo,client,auth_headers):
    result=client.post('/api/admin/token',headers=auth_headers)
    assert result.status_code==200
    code=result.json()['token'];assert len(code)==6 and code.isdigit()
    entered=client.post('/api/enter',json={'token':code})
    assert entered.status_code==200
    assert client.post('/api/enter',json={'token':code}).status_code==409


def test_admin_protection_and_configuration_guard(demo,client,auth_headers):
    assert client.get('/api/shop/status').status_code==401
    assert client.post('/api/shop/configure',json={'enabled':False}).status_code==401
    demo.customer()
    r=client.post('/api/shop/configure',headers=auth_headers,json={'enabled':True,'product_id':demo.product.id,'zone_id':demo.cfg.zone_id,'roi_confirmed':True})
    assert r.status_code==409


def test_real_routes_push_pick_and_return_to_customer_without_refresh(demo,client,auth_headers,monkeypatch):
    # Real entry/session, real HTTP frames, real DB, real admin/customer WebSockets.
    code=client.post('/api/admin/token',headers=auth_headers).json()['token']
    entered=client.post('/api/enter',json={'token':code}).json()
    observations=iter(['PRESENT']*3+['ABSENT']*3+['PRESENT']*3)
    monkeypatch.setattr(demo.runtime,'classify',lambda *_: (next(observations),.95,[]))
    frame=base64.b64encode(cv2.imencode('.jpg',np.zeros((64,96,3),dtype=np.uint8))[1]).decode()
    with client.websocket_connect('/ws/customer') as customer_ws,client.websocket_connect('/ws/admin') as admin_ws:
        customer_ws.send_json({'session_secret':entered['session_secret']})
        assert customer_ws.receive_json()['type']=='CART_SYNC'
        admin_ws.send_json({'token':create_admin_token()})
        assert admin_ws.receive_json()['type']=='AUTH_OK'
        for seq in range(6):
            response=client.post('/api/shop/frame',headers=auth_headers,json={'frame':frame,'stream_id':'test','sequence':seq})
            assert response.status_code==200;demo.clock.value+=.65
        picked=customer_ws.receive_json()
        assert picked['type']=='CART_UPDATED' and picked['action']=='PICKED' and picked['cart']['total_quantity']==1
        for seq in range(6,9):
            assert client.post('/api/shop/frame',headers=auth_headers,json={'frame':frame,'stream_id':'test','sequence':seq}).status_code==200
            demo.clock.value+=.65
        returned=customer_ws.receive_json()
        assert returned['action']=='RETURNED' and returned['cart']['total_quantity']==0
        messages=[]
        while not any(m.get('type')=='CART_UPDATED' and m.get('cart',{}).get('total_quantity')==0 for m in messages):
            messages.append(admin_ws.receive_json())
        assert any(m.get('type')=='SHOP_STATE' and m['shop']['stock_quantity']==0 for m in messages)
    demo.db.expire_all();assert demo.db.get(Product,demo.product.id).stock_quantity==1


def test_pause_resume_same_shelf_keeps_cart_and_stock(demo, client, auth_headers, monkeypatch):
    customer = demo.customer()
    demo.feed('PRESENT')
    demo.feed('ABSENT')
    assert quantity(demo, customer) == 1
    product_stock = demo.product.stock_quantity
    stopped = client.post('/api/shop/configure', headers=auth_headers, json={'enabled': False})
    assert stopped.status_code == 200
    demo.db.refresh(demo.cfg)
    assert not demo.cfg.enabled
    assert demo.cfg.pick_session_id == customer.id
    assert demo.cfg.stock_quantity == 0

    monkeypatch.setattr(routes, 'get_bottle_detector',
                        lambda: SimpleNamespace(status=lambda: {'ready': True}))
    zone = demo.db.get(Zone, demo.cfg.zone_id)
    resumed = client.post('/api/shop/configure', headers=auth_headers, json={
        'enabled': True, 'product_id': demo.product.id, 'zone_id': zone.id,
        'camera_source': 'browser', 'roi_confirmed': True,
        'roi': [zone.roi_x, zone.roi_y, zone.roi_w, zone.roi_h],
    })
    assert resumed.status_code == 200
    demo.db.refresh(demo.cfg)
    assert demo.cfg.enabled
    assert demo.cfg.stock_quantity == 0
    assert demo.cfg.pick_session_id == customer.id
    assert quantity(demo, customer) == 1
    assert demo.product.stock_quantity == product_stock

    # First observation after resume is only a baseline, not a new sale.
    demo.feed('ABSENT')
    assert quantity(demo, customer) == 1
    demo.feed('PRESENT')
    assert quantity(demo, customer) == 0


def test_resume_with_active_customer_rejects_changed_product(demo, client, auth_headers):
    demo.customer()
    other = demo.db.query(Product).filter(Product.id != demo.product.id).first()
    assert other is not None
    response = client.post('/api/shop/configure', headers=auth_headers, json={
        'enabled': True, 'product_id': other.id, 'zone_id': demo.cfg.zone_id,
        'roi_confirmed': True,
    })
    assert response.status_code == 409
