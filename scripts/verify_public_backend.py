"""Read-only HTTP/WSS checks; no real credentials or camera frames are sent."""
import argparse
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def request(url, origin=None):
    headers = {"User-Agent": "SmartShelf-ReadOnly-HealthCheck/1.0"}
    if origin: headers["Origin"] = origin
    req = urllib.request.Request(url, headers=headers)
    # Loopback checks must reach this computer, including on systems with a proxy.
    opener = (urllib.request.build_opener(urllib.request.ProxyHandler({}))
              if urlsplit(url).hostname in ('127.0.0.1', 'localhost', '::1') else None)
    try:
        with (opener.open(req, timeout=8) if opener else urllib.request.urlopen(req, timeout=8)) as resp:
            return resp.status, resp.headers, resp.read(4096)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read(4096)


def https_origin(value):
    value = value.strip().rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query
            or parsed.fragment or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError('Expected an HTTPS origin without credentials, path, query or fragment.')
    return value


def websocket_check(base, origin=None):
    from websockets.sync.client import connect
    from websockets.exceptions import ConnectionClosed
    url = base.replace('https://', 'wss://', 1).replace('http://', 'ws://', 1) + '/ws/admin'
    with connect(url, origin=origin, open_timeout=6, close_timeout=1, proxy=None) as ws:
        ws.send(json.dumps({'token': 'diagnostic-invalid-token'}))
        try:
            ws.recv(timeout=6)
        except ConnectionClosed as exc:
            return exc.rcvd is not None and exc.rcvd.code == 1008
    return False


def collect_checks(base, frontend):
    results = []
    def add(name, success, detail=''):
        results.append({'check': name, 'status': 'PASS' if success else 'FAIL', 'detail': detail})
    try:
        code, headers, body = request(base + '/api/health', frontend)
        try:
            healthy = code == 200 and json.loads(body).get('status') == 'ok'
        except (ValueError, AttributeError):
            healthy = False
        add('backend_health', healthy, f'HTTP {code}')
        add('frontend_cors', headers.get('Access-Control-Allow-Origin') == frontend)
    except Exception as exc:
        add('backend_health', False, type(exc).__name__)
        return results
    for route in ['/api/admin/auth/check', '/api/presence']:
        try:
            code, _, _ = request(base + route)
            add('protected_' + route, code == 401, f'HTTP {code}; expected 401')
        except Exception as exc:
            add('protected_' + route, False, type(exc).__name__)
    try:
        _, headers, _ = request(base + '/api/health', 'https://diagnostic-untrusted.invalid')
        add('untrusted_origin_not_allowed', not headers.get('Access-Control-Allow-Origin'))
    except Exception as exc:
        add('untrusted_origin_not_allowed', False, type(exc).__name__)
    try:
        add('websocket_upgrade_and_auth_rejection', websocket_check(base, frontend), 'Expected close 1008 for invalid token')
    except Exception as exc:
        add('websocket_upgrade_and_auth_rejection', False, type(exc).__name__)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("backend_url", help="https://backend-hostname")
    parser.add_argument("--frontend", default="https://shelf-ir.vercel.app")
    args = parser.parse_args()
    try:
        base = https_origin(args.backend_url)
        frontend = https_origin(args.frontend)
    except ValueError as exc:
        parser.error(str(exc))
    results = collect_checks(base, frontend)
    for result in results:
        print(result['status'] + '  ' + result['check'] + '  ' + result['detail'])
    print('A passing handshake does not verify sustained tablet streaming, recognition or sales readiness.')
    raise SystemExit(0 if all(r['status'] == 'PASS' for r in results) else 1)

if __name__ == "__main__":
    main()
