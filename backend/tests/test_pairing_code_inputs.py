from backend.app.services.camera_pairing import create_camera_pairing_code


def test_camera_pair_accepts_persian_arabic_and_copied_direction_marks(client):
    for target_digits in ('۰۱۲۳۴۵۶۷۸۹', '٠١٢٣٤٥٦٧٨٩'):
        code = create_camera_pairing_code()
        localized = code.translate(str.maketrans('0123456789', target_digits))
        pasted = '\u200f' + localized[:3] + ' ' + localized[3:] + '\u200e'
        response = client.post('/api/camera/pair', json={'pairing_code': pasted, 'device_id': 'input_tablet'})
        assert response.status_code == 200
        assert response.json()['device_token']
        assert client.post('/api/camera/pair', json={'code': code, 'device_id': 'second_tablet'}).status_code == 400


def test_malformed_code_does_not_consume_valid_code(client):
    code = create_camera_pairing_code()
    for invalid in (code + '7', code[:-1], code[:3] + 'x' + code[3:], ''):
        assert client.post('/api/camera/pair', json={'code': invalid, 'device_id': 'input_tablet'}).status_code == 400
    assert client.post('/api/camera/pair', json={'code': code, 'device_id': 'input_tablet'}).status_code == 200


def test_oversized_pairing_code_is_rejected_before_lookup(client):
    assert client.post('/api/camera/pair', json={'code': '1' * 65, 'device_id': 'input_tablet'}).status_code == 422
