from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from backend.app.services import camera_pairing as pairing
from backend.app.vision.camera_feed import camera_feed
from backend.app.config import settings
from backend.app.models import ShopScenario,CustomerSession
from backend.app.services.seed import seed_initial_data
from backend.app.services import shop_scenario as shop


def token(device='http_tablet'):
    return pairing.exchange_pairing_code_for_token(pairing.create_camera_pairing_code(),device)


def photo():
    image=np.random.default_rng(14).integers(0,255,(64,96,3),dtype=np.uint8)
    return cv2.imencode('.jpg',image)[1].tobytes()


def test_signed_pairing_survives_restart_and_rejects_tampering(monkeypatch):
    value=token();pairing._device_tokens.clear()
    assert pairing.is_camera_device_token_valid(value)
    assert pairing.get_device_info_by_token(value)['device_id']=='http_tablet'
    assert not pairing.is_camera_device_token_valid(value[:-4]+'abcd')
    monkeypatch.setattr(settings,'SECRET_KEY','rotated-secret-for-test')
    assert not pairing.is_camera_device_token_valid(value)


def test_expired_signed_camera_token_is_rejected(monkeypatch):
    value=token();now=pairing.time.time()
    monkeypatch.setattr(pairing,'time',SimpleNamespace(time=lambda:now+31*86400))
    assert not pairing.is_camera_device_token_valid(value)


def test_https_frame_requires_bound_token_and_valid_image(client):
    camera_feed.clear();value=token();headers={'Authorization':'Bearer '+value,'Content-Type':'image/jpeg'}
    assert client.post('/api/camera/frame?device_id=http_tablet',content=photo()).status_code==401
    assert client.post('/api/camera/frame?device_id=other_camera',headers=headers,content=photo()).status_code==401
    assert client.post('/api/camera/frame?device_id=http_tablet',headers=headers,content=b'bad').status_code==422
    result=client.post('/api/camera/frame?device_id=http_tablet',headers=headers,content=photo())
    assert result.status_code==200 and result.json()['type']=='frame_received'
    assert camera_feed.get_stats()['is_live'] and camera_feed.active_device_id=='http_tablet'
    assert client.post('/api/camera/frame?device_id=http_tablet',headers=headers,content=b'x'*(camera_feed.MAX_FRAME_BYTES+1)).status_code==413


def test_wss_frame_ack_is_opt_in_and_camera_identity_is_bound(client):
    value=token()
    with client.websocket_connect('/ws/camera?device_id=http_tablet') as ws:
        ws.send_json({'type':'auth','device_token':value,'frame_ack':True})
        assert ws.receive_json()['frame_ack'] is True
        ws.send_bytes(photo());assert ws.receive_json()['type']=='frame_received'
        ws.send_text('ping');assert ws.receive_text()=='pong'
    with pytest.raises(Exception):
        with client.websocket_connect('/ws/camera?device_id=another_tablet') as ws:
            ws.send_json({'type':'auth','device_token':value});ws.receive_json()


def test_https_fallback_updates_real_customer_cart_over_websocket(client,db_session,monkeypatch):
    seed=seed_initial_data(db_session)
    cfg=ShopScenario(id=1,enabled=True,zone_id=seed['zones'][0].id,product_id=seed['products'][0].id,camera_source='tablet',generation=1)
    customer=CustomerSession(session_secret='http-fallback-test-customer',status='ACTIVE')
    db_session.add_all([cfg,customer]);db_session.commit()
    clock=[0.];runtime=shop.ShopRuntime(clock=lambda:clock[0]);monkeypatch.setattr(shop,'shop_runtime',runtime)
    obs=iter(['PRESENT']*3+['ABSENT']*3+['PRESENT']*3)
    monkeypatch.setattr(runtime,'classify',lambda *_:(next(obs),.9,[]))
    value=token();headers={'Authorization':'Bearer '+value,'Content-Type':'image/jpeg'}
    with client.websocket_connect('/ws/customer') as ws:
        ws.send_json({'session_secret':customer.session_secret});assert ws.receive_json()['type']=='CART_SYNC'
        for i in range(9):
            result=client.post('/api/camera/frame?device_id=http_tablet',headers=headers,content=photo());assert result.status_code==200
            clock[0]+=.65
            if i==5:
                update=ws.receive_json();assert update['action']=='PICKED' and update['cart']['total_quantity']==1
            if i==8:
                update=ws.receive_json();assert update['action']=='RETURNED' and update['cart']['total_quantity']==0
