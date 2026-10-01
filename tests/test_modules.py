"""Unit tests for the standalone Onyx Panel modules (no server needed).

Run from the repository root:  python tests/test_modules.py
"""
import base64, hashlib, hmac, json, os, sys, tempfile, time
import urllib.request as _ur

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import onyx_totp, onyx_webapi, onyx_access, onyx_failover, onyx_cascade, onyx_telegram

# ---- TOTP: RFC 6238 reference secret, cross-checked against a local HMAC ref
secret = base64.b32encode(b'12345678901234567890').decode().rstrip('=')
def _ref(counter, digits=6):
    key = base64.b32decode(secret + '=' * (-len(secret) % 8))
    d = hmac.new(key, counter.to_bytes(8, 'big'), hashlib.sha1).digest()
    o = d[-1] & 15
    return str((int.from_bytes(d[o:o+4], 'big') & 0x7fffffff) % (10 ** digits)).zfill(digits)
assert onyx_totp.totp_at(secret, 30) == _ref(1)
assert onyx_totp.verify(secret, _ref(1), timestamp=30)
assert onyx_totp.verify(secret, _ref(2), timestamp=45)      # +-1 window
assert not onyx_totp.verify(secret, _ref(5), timestamp=30)  # wrong code
assert not onyx_totp.verify(secret, 'abc', timestamp=30)    # non digits
assert 'otpauth://totp/Onyx%20Panel:admin?secret=' in onyx_totp.provisioning_uri(secret, 'admin')
print('TOTP OK')

# ---- webapi: tokens, hashing, validation
tok = onyx_webapi.create_token()
k, tok2 = onyx_webapi.new_key('test')
assert tok2.startswith('onx_') and onyx_webapi.find_key([k], tok2) is k
assert onyx_webapi.find_key([k], 'onx_wrong') is None
assert onyx_webapi.public_keys([k]) == [{'id': k['id'], 'name': 'test', 'created': k['created'], 'last_used': 0}]
name, proto, dev = onyx_webapi.check_create({'name': ' client ', 'protocol': 'VLESS', 'devices': '3'})
assert (name, proto, dev) == ('client', 'vless', 3)
for bad in ({'name': ''}, {'name': 'x', 'protocol': 'mieru'}, {'name': 'x', 'protocol': 'vless', 'devices': 99}):
    try:
        onyx_webapi.check_create(bad); raise SystemExit('should fail')
    except ValueError:
        pass
assert onyx_webapi.check_renew({'days': '30'}) == 30
try:
    onyx_webapi.check_renew({'days': 0}); raise SystemExit('should fail')
except ValueError:
    pass
print('WEBAPI OK')

# ---- access journal
st = {}
fresh1 = onyx_access.record_login(st, 'admin', 'admin', '1.2.3.4', 'Mozilla/5.0 test')
fresh2 = onyx_access.record_login(st, 'admin', 'admin', '1.2.3.4', 'Mozilla/5.0 test')
assert fresh1 and not fresh2 and len(st['logins']) == 2 and st['logins'][-1]['new_device'] is False
assert len(onyx_access.last_logins(st, 10)) == 2
assert onyx_access.observer_can_get('/dashboard') and not onyx_access.observer_can_get('/settings')
assert onyx_access.observer_can_post('/logout') and not onyx_access.observer_can_post('/add-user')
print('ACCESS OK')

# ---- failover decisions
cascades = [{'id': 'a', 'enabled': True, 'mode': 'all'},
            {'id': 'b', 'enabled': False, 'mode': 'all'},
            {'id': 'c', 'enabled': False, 'mode': 'users'}]
f = {}
f = onyx_failover.note_result(f, 'a', False); assert onyx_failover.decide(cascades, f) is None
f = onyx_failover.note_result(f, 'a', False)
assert onyx_failover.decide(cascades, f) == {'disable': 'a', 'enable': 'b'}
f = onyx_failover.note_result(f, 'a', True); assert onyx_failover.decide(cascades, f) is None
assert onyx_failover.decide([{'id': 'a', 'enabled': True, 'mode': 'all'}], {'a': 5}) is None  # no standby
print('FAILOVER OK')

# ---- telegram: multipart upload shape (network mocked)
captured = {}
import io as _io
class _Resp(_io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
captured = {}
def fake_urlopen(req, timeout=None):
    captured['body'] = req.data; captured['headers'] = req.headers
    return _Resp(b'{"ok":true}')
_urlopen_orig = _ur.urlopen; _ur.urlopen = fake_urlopen
try:
    onyx_telegram.send_document('123:tok', '42', 'backup.tar.gz', b'PAYLOAD')
finally:
    _ur.urlopen = _urlopen_orig
assert 'multipart/form-data' in captured['headers']['Content-type']
assert b'PAYLOAD' in captured['body'] and b'filename="backup.tar.gz"' in captured['body']
# notify() respects event toggles
_ur.urlopen = fake_urlopen
try:
    assert onyx_telegram.notify({'token': '123:tok', 'chat': '42', 'events': {'logins': False}}, 'logins', 'x') is False
    assert onyx_telegram.notify({'token': '123:tok', 'chat': '42', 'events': {'logins': True}}, 'logins', 'x') is True
finally:
    _ur.urlopen = _urlopen_orig
print('TELEGRAM OK')

# ---- cascade speedtest: clean error path without a real xray binary
res = onyx_cascade.speedtest({'uuid': '0' * 32, 'address': 'example.com', 'port': 443,
                              'network': 'tcp', 'security': 'none', 'stream': {}, 'flow': ''},
                             xray_bin='/nonexistent/xray')
assert not res['ok'] and res['message'], res
print('SPEEDTEST OK')
print('ALL MODULE TESTS PASSED')
