import importlib
import json
from pathlib import Path
import pytest


@pytest.fixture
def diagnostics(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'scripts'))
    return importlib.import_module('diagnose_windows')


def test_shareable_report_does_not_export_private_configuration(tmp_path, diagnostics):
    private_pin = 'PrivatePin-DoNotExport'
    private_key = 'PrivateSecret-DoNotExport-0123456789abcdef'
    (tmp_path / '.env').write_text(
        f'ADMIN_PIN={private_pin}\nSECRET_KEY={private_key}\n'
        'STORE_OPEN=false\nPUBLIC_BASE_URL=https://qa-shelf.testnet.ts.net\n'
        'EXTRA_ACCESS_TOKEN=secret-token-never-export\n', encoding='utf-8')
    report = diagnostics.collect_report(root=tmp_path, offline=True)
    serialized = json.dumps(report)
    assert private_pin not in serialized
    assert private_key not in serialized
    assert 'secret-token-never-export' not in serialized
    assert report['configuration']['public_backend_url'] == 'https://qa-shelf.testnet.ts.net'
    assert report['local_checks'] == report['public_checks'] == []


def test_diagnostics_hides_credentials_in_malformed_public_url(tmp_path, diagnostics):
    (tmp_path / '.env').write_text(
        'PUBLIC_BASE_URL=https://admin:private-password@device.testnet.ts.net\n', encoding='utf-8')
    report = diagnostics.collect_report(root=tmp_path, offline=True)
    assert report['configuration']['public_backend_url'] is None
    assert 'private-password' not in json.dumps(report)


def test_http_error_body_is_reported_without_crashing(diagnostics, monkeypatch):
    checker = importlib.import_module('verify_public_backend')
    monkeypatch.setattr(checker, 'request', lambda *args: (502, {}, b'<html>upstream offline</html>'))
    monkeypatch.setattr(checker, 'websocket_check', lambda *args: False)
    checks = checker.collect_checks('https://qa-shelf.testnet.ts.net', 'https://shelf-ir.vercel.app')
    assert checks[0]['status'] == 'FAIL'
    assert checks[-1]['status'] == 'FAIL'
