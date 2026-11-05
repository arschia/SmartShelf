import base64
import io
import json
import zipfile

import cv2
import numpy as np
import pytest

from backend.app.config import settings
from backend.app.routes import bottle as routes
from backend.app.vision.bottle_detector import decode_detections, letterbox
from backend.app.services.bottle_dataset import save_sample, build_dataset_zip


def encoded_image(color=0):
    frame = np.full((80, 120, 3), color, dtype=np.uint8)
    return base64.b64encode(cv2.imencode('.jpg', frame)[1]).decode()


def test_letterbox_coordinates_and_unknown_brand():
    frame = np.zeros((400, 800, 3), dtype=np.uint8)
    tensor, transform = letterbox(frame)
    assert tensor.shape == (1, 3, 640, 640)
    out = np.array([[[160, 240, 480, 400, .9, 39], [0, 0, 20, 20, .9, 0]]])
    found = decode_detections(out, {0:'person',39:'bottle'}, transform, 800, 400)
    assert len(found) == 1
    assert found[0]['box'] == pytest.approx([.25,.25,.75,.75])
    assert found[0]['target'] is None
    assert found[0]['identity'] == 'UNKNOWN'


def test_custom_classes_raw_nms_and_nonfinite():
    output = np.zeros((1, 6, 8), dtype=np.float32)
    output[0,:,0] = [320,320,200,200,.9,.1]
    output[0,:,1] = [321,321,200,200,.8,.1]
    output[0,:,2] = [100,100,50,50,.1,.85]
    found = decode_detections(output,{0:'heyjo_peach',1:'other_bottle'},(1,1,0,0),640,640)
    assert len(found) == 2
    assert {d['target'] for d in found} == {True,False}
    bad = np.array([[[0,0,100,100,np.nan,0],[0,0,100,100,.9,8]]])
    assert decode_detections(bad,{0:'bottle'},(1,1,0,0),640,640) == []


def test_bottle_routes_require_admin(client):
    assert client.get('/api/bottle/status').status_code == 401
    assert client.post('/api/bottle/detect',json={'frame':encoded_image()}).status_code == 401
    assert client.post('/api/bottle/samples',json={}).status_code == 401
    assert client.get('/api/bottle/dataset.zip').status_code == 401


def test_detection_is_read_only_and_tablet_staleness(client, auth_headers, monkeypatch):
    class Fake:
        def detect(self, frame, threshold):
            return {'detections':[], 'bottle_count':0, 'target_count':0,'transactions_enabled':False}
    monkeypatch.setattr(routes,'get_bottle_detector',lambda:Fake())
    res=client.post('/api/bottle/detect',headers=auth_headers,json={'frame':encoded_image()})
    assert res.status_code == 200 and res.json()['transactions_enabled'] is False
    monkeypatch.setattr(routes.camera_feed,'last_frame_time',None)
    assert client.post('/api/bottle/detect',headers=auth_headers,json={'source':'tablet'}).status_code == 409
    assert client.post('/api/bottle/detect',headers=auth_headers,json={'frame':'invalid'}).status_code == 422


def test_explicit_review_invalid_boxes_and_private_export(client,auth_headers,tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'BOTTLE_DATASET_DIR',str(tmp_path))
    payload={'frame':encoded_image(),'environment':'class-1','boxes':[],'reviewed':False}
    assert client.post('/api/bottle/samples',headers=auth_headers,json=payload).status_code == 422
    payload.update(reviewed=True)
    assert client.post('/api/bottle/samples',headers=auth_headers,json=payload).status_code == 422
    payload['boxes']=[{'class_id':0,'box':[.8,.2,.1,.9]}]
    assert client.post('/api/bottle/samples',headers=auth_headers,json=payload).status_code == 422
    payload['boxes']=[{'class_id':0,'box':[.1,.1,.6,.9]}]
    assert client.post('/api/bottle/samples',headers=auth_headers,json=payload).status_code == 200
    payload['environment']='class-2'
    assert client.post('/api/bottle/samples',headers=auth_headers,json=payload).status_code == 409
    assert client.get('/api/bottle/dataset.zip',headers=auth_headers).status_code == 409
    for i in [2,3]:
        payload.update(environment=f'class-{i}',frame=encoded_image(i*60))
        assert client.post('/api/bottle/samples',headers=auth_headers,json=payload).status_code == 200
    res=client.get('/api/bottle/dataset.zip',headers=auth_headers)
    assert res.status_code == 200
    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        report=json.loads(archive.read('dataset_report.json'))
        assert set(report['environment_splits'].values()) == {'train','val','test'}
        assert sum(n.endswith('.jpg') for n in archive.namelist()) == 3


def test_whole_environment_is_held_out(tmp_path):
    for i,env in enumerate(['room-a','room-a','room-b','room-c']):
        save_sample(tmp_path,np.full((40,60,3),i*50,dtype=np.uint8),env,[{'class_id':0,'box':[.2,.2,.8,.9]}])
    blob,report=build_dataset_zip(tmp_path)
    assert report['sample_counts'] == {'train':2,'val':1,'test':1}
    assert report['environment_splits']['room-a'] == 'train'
