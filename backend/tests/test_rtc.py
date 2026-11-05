"""Signaling authorization, cross-device isolation and lossless queue lifecycle."""
import time
import pytest
from backend.app.routes import rtc
from backend.app.services.auth import create_admin_token
from backend.app.services.camera_pairing import create_camera_pairing_code, exchange_pairing_code_for_token
from backend.app.vision.camera_feed import camera_feed


@pytest.fixture(autouse=True)
def rtc_state(monkeypatch):
    rtc.sessions.clear()
    monkeypatch.setenv('RTC_ICE_SERVERS', '[]')
    monkeypatch.setattr(camera_feed, 'active_device_id', 'rtc_tablet')
    monkeypatch.setattr(camera_feed, 'last_frame_time', time.time())
    yield
    rtc.sessions.clear()


def camera_headers(device='rtc_tablet'):
    code = create_camera_pairing_code()
    return {'Authorization': 'Bearer ' + exchange_pairing_code_for_token(code, device)}


def open_session(client, headers):
    response = client.post('/api/rtc/view', json={}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['ice_servers'] == []
    return response.json()['session_id']


def test_auth_and_bound_device(client, auth_headers):
    assert client.post('/api/rtc/view', json={}).status_code == 401
    assert client.post('/api/rtc/camera/poll?device_id=rtc_tablet', json={}).status_code == 401
    sid = open_session(client, auth_headers)
    other_admin = {'Authorization': 'Bearer ' + create_admin_token()}
    assert client.get(f'/api/rtc/view/{sid}', headers=other_admin).status_code == 403
    assert client.post(f'/api/rtc/view/{sid}/signal', json={'type': 'close'}, headers=camera_headers()).status_code == 401
    wrong_device = camera_headers('another_tablet')
    assert client.post('/api/rtc/camera/poll?device_id=rtc_tablet', json={}, headers=wrong_device).status_code == 401
    assert client.post('/api/rtc/camera/poll?device_id=another_tablet', json={}, headers=wrong_device).json()['sessions'] == []
    assert client.post(f'/api/rtc/camera/{sid}/signal?device_id=another_tablet', json={'type': 'close'}, headers=wrong_device).status_code == 403


def test_offer_answer_ice_ack_close(client, auth_headers):
    sid = open_session(client, auth_headers)
    headers = camera_headers()
    offer = {'type': 'offer', 'description': {'type': 'offer', 'sdp': 'v=0\r\n'}}
    ice = {'type': 'ice', 'candidate': {'candidate': 'candidate:test', 'sdpMid': '0'}}
    assert client.post(f'/api/rtc/view/{sid}/signal', json=offer, headers=auth_headers).status_code == 200
    assert client.post(f'/api/rtc/view/{sid}/signal', json=ice, headers=auth_headers).status_code == 200
    def poll(after):
        return client.post('/api/rtc/camera/poll?device_id=rtc_tablet', json={'after': after}, headers=headers).json()['sessions'][0]
    first = poll({})['messages']
    assert [event['type'] for event in first] == ['offer', 'ice']
    assert poll({})['messages'] == first, 'retry before ack must not lose the offer'
    assert poll({sid: 2})['messages'] == []
    answer = {'type': 'answer', 'description': {'type': 'answer', 'sdp': 'v=0\r\n'}}
    assert client.post(f'/api/rtc/camera/{sid}/signal?device_id=rtc_tablet', json=answer, headers=headers).status_code == 200
    assert client.post(f'/api/rtc/camera/{sid}/signal?device_id=rtc_tablet', json=ice, headers=headers).status_code == 200
    response = client.get(f'/api/rtc/view/{sid}', headers=auth_headers)
    assert response.headers['cache-control'] == 'no-store'
    assert [event['type'] for event in response.json()['messages']] == ['answer', 'ice']
    assert client.get(f'/api/rtc/view/{sid}?after=2', headers=auth_headers).json()['messages'] == []
    assert client.post(f'/api/rtc/view/{sid}/signal', json={'type': 'close'}, headers=auth_headers).status_code == 200
    assert poll({sid: 2})['closed'] is True
    assert poll({sid: 2})['messages'][0]['type'] == 'close'


def test_expiry_limits_and_offline_camera(client, auth_headers):
    sid = open_session(client, auth_headers)
    rtc.sessions[sid]['seen'] -= rtc.TTL + 1
    assert client.get(f'/api/rtc/view/{sid}', headers=auth_headers).status_code == 404
    for _ in range(3): open_session(client, auth_headers)
    assert client.post('/api/rtc/view', json={}, headers=auth_headers).status_code == 429
    rtc.sessions.clear()
    camera_feed.last_frame_time = time.time() - 15
    assert client.post('/api/rtc/view', json={}, headers=auth_headers).status_code == 409


def test_payload_validation_and_queue_bound(client, auth_headers):
    sid = open_session(client, auth_headers)
    path = f'/api/rtc/view/{sid}/signal'
    for payload in [[], {'type': 'answer'}, {'type': 'offer', 'description': {'type': 'answer', 'sdp': 'x'}}, {'type': 'ice', 'candidate': 'bad'}, {'type': 'ice', 'candidate': {'candidate': 'x' * 9000}}]:
        assert client.post(path, json=payload, headers=auth_headers).status_code == 422
    assert client.post(path, content='x' * 100000, headers=auth_headers).status_code == 413
    for _ in range(128):
        assert client.post(path, json={'type': 'ice', 'candidate': None}, headers=auth_headers).status_code == 200
    assert client.post(path, json={'type': 'ice', 'candidate': None}, headers=auth_headers).status_code == 429


def test_turn_configuration_authorized_only(client, auth_headers, monkeypatch):
    config = [{'urls': ['turns:relay.example.test:443?transport=tcp'], 'username': 'demo', 'credential': 'test-only'}]
    import json
    monkeypatch.setenv('RTC_ICE_SERVERS', json.dumps(config))
    assert client.post('/api/rtc/view', json={}).status_code == 401
    assert client.post('/api/rtc/view', json={}, headers=auth_headers).json()['ice_servers'] == config
    monkeypatch.setenv('RTC_ICE_SERVERS', '[{"urls":"https://invalid.test"}]')
    assert client.post('/api/rtc/view', json={}, headers=auth_headers).status_code == 503
