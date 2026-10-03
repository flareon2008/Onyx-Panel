"""Unit tests for the standalone Onyx Panel modules (no server needed).

Run from the repository root:  python tests/test_modules.py
"""
import base64, hashlib, hmac, os, sys, tempfile
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

# ---- update bell notifications: temp paths, no network, no systemctl
import onyx_update
from pathlib import Path
upd_tmp = Path(tempfile.mkdtemp())
onyx_update.ROOT = upd_tmp
onyx_update.STATUS = upd_tmp / 'status.json'
onyx_update.NOTES = upd_tmp / 'notifications.json'
onyx_update.VERSION = upd_tmp / 'version'
onyx_update.VERSION.write_text('1.6.0', encoding='ascii')
onyx_update.REPO = 'https://github.com/xCodeOn/Onyx-Panel.git'

# release markdown -> plain lines
assert onyx_update.parse_notes('## Изменения\n\n- fix a (abc1234)\n\n* feat b (def5678)\n# Заголовок\nтекст без маркера') == \
    ['fix a (abc1234)', 'feat b (def5678)', 'текст без маркера']
assert onyx_update.parse_notes('') == []
assert onyx_update.repo_slug() == 'xCodeOn/Onyx-Panel'
onyx_update.REPO = 'https://gitlab.com/x/panel.git'
assert onyx_update.repo_slug() == ''
onyx_update.REPO = 'https://github.com/xCodeOn/Onyx-Panel.git'

# add/dedupe/read/clear
onyx_update.add_note('available', 'v1.7.0')
onyx_update.add_note('available', 'v1.7.0')          # dedupe by (kind, version)
assert len(onyx_update.load_notes()) == 1
assert onyx_update.notes_public()['unread'] == 1
onyx_update.mark_notes_read()
assert onyx_update.notes_public()['unread'] == 0
onyx_update.add_note('available', 'v1.7.0')          # re-check keeps read flag
assert onyx_update.load_notes()[0]['read'] is True
assert onyx_update.load_notes()[0]['current'] == '1.6.0'
onyx_update.clear_notes()
assert onyx_update.load_notes() == []

# prune: "available" notes for installed versions disappear, others stay
onyx_update.add_note('available', 'v1.7.0')
onyx_update.add_note('changelog', 'v1.6.9')
onyx_update.prune_available('1.7.0')
kinds = sorted(item['kind'] for item in onyx_update.load_notes())
assert kinds == ['changelog'], kinds
onyx_update.clear_notes()

# finished update -> changelog note, available note pruned, announced marker set
onyx_update.VERSION.write_text('1.7.0', encoding='ascii')
onyx_update.add_note('available', 'v1.7.0')
onyx_update.atomic_json(onyx_update.STATUS, {'phase': 'done', 'target': 'v1.7.0'})
onyx_update.release_notes = lambda tag: (['Новая функция колокольчика (ab12cd3)'], 'https://github.com/xCodeOn/Onyx-Panel/releases/tag/v1.7.0')
status = onyx_update.get_status()
notes = onyx_update.load_notes()
assert status['announced'] == 'v1.7.0', status
assert [n['kind'] for n in notes] == ['changelog'], notes
assert notes[0]['version'] == 'v1.7.0' and notes[0]['changes'] == ['Новая функция колокольчика (ab12cd3)']
assert notes[0]['link'].endswith('/releases/tag/v1.7.0')
assert onyx_update.get_status()['announced'] == 'v1.7.0'      # announced only once
assert len(notes) == 1

# update finished but panel runs a different version -> no announcement
onyx_update.clear_notes()
onyx_update.atomic_json(onyx_update.STATUS, {'phase': 'done', 'target': 'v9.9.9'})
onyx_update.get_status()
assert onyx_update.load_notes() == []
onyx_update.clear_notes()
print('UPDATE NOTIFICATIONS OK')
# ---- node registry sync: version refresh + heal of stale enabled=false
import onyx_nodes
nodes_tmp = Path(tempfile.mkdtemp())
registry = str(nodes_tmp / 'nodes.json')
registry_state = [
    {'id': 'aaaa', 'url': 'https://a.example.com', 'token': 'a' * 43, 'country_code': 'FI',
     'country_name': 'Финляндия', 'name': 'Хельсинки', 'version': '1.8.8', 'enabled': True},
    {'id': 'bbbb', 'url': 'https://b.example.com', 'token': 'b' * 43, 'country_code': 'DE',
     'country_name': 'Германия', 'name': 'Франкфурт', 'version': '1.8.8', 'enabled': False},
]
onyx_nodes.save_nodes(registry, registry_state)

# live probes: a answered with a fresh version, b answers despite enabled=false
live_a = {'id': 'aaaa', 'enabled': True, 'online': True, 'version': '1.9.6'}
live_b = {'id': 'bbbb', 'enabled': True, 'online': True, 'version': '1.9.6'}
assert onyx_nodes.sync_registry(registry, [registry_state[0], registry_state[1]], [live_a, live_b]) is True
merged = {n['id']: n for n in onyx_nodes.load_nodes(registry)}
assert merged['aaaa']['version'] == '1.9.6'
assert merged['bbbb']['version'] == '1.9.6' and merged['bbbb']['enabled'] is True
print('NODE REGISTRY SYNC OK')

# no changes -> no write
assert onyx_nodes.sync_registry(registry, list(merged.values()), [live_a, live_b]) is False
# failed probe (offline, no version) does not heal or touch the record
dead = {'id': 'aaaa', 'enabled': True, 'online': False, 'version': ''}
assert onyx_nodes.sync_registry(registry, [merged['aaaa']], [dead]) is False
# a node deleted while the refresh ran is not resurrected by stale snapshots
onyx_nodes.save_nodes(registry, [dict(merged['bbbb'], version='1.9.6')])
assert onyx_nodes.sync_registry(registry, [merged['aaaa']], [live_a]) is False
assert [n['id'] for n in onyx_nodes.load_nodes(registry)] == ['bbbb']
print('NODE REGISTRY EDGE CASES OK')

# ---- routing rules: normalization and Xray merge shape
import onyx_routing
# typographic dashes normalize to the ASCII hyphen
assert onyx_routing._clean_entry('domain:xn\u2014\u2014p1ai') == 'domain:xn--p1ai'
assert onyx_routing._clean_entry('geoip:ru\u2013test') == 'geoip:ru-test'
assert onyx_routing._clean_entry('') == '' and onyx_routing._clean_entry('  ') == ''
for bad in ('a b', 'do"main', 'x' * 121):
    try:
        onyx_routing._clean_entry(bad); raise SystemExit('should fail: ' + repr(bad))
    except onyx_routing.RoutingError:
        pass
assert onyx_routing._clean_list(['', '  ', 'domain:ru']) == ['domain:ru']
try:
    onyx_routing._clean_list(['domain:ru', 'a b']); raise SystemExit('should fail')
except onyx_routing.RoutingError:
    pass
norm = onyx_routing.normalize({'direct_ips': ['GeoIP:RU', 'geoip:ru', '1.2.3.4', ''],
                               'direct_domains': ['domain:\u0440\u0444'],
                               'ipv4_domains': ['domain:example.com'], 'block_torrents': 1})
assert norm['direct_ips'] == ['GeoIP:RU', '1.2.3.4'] and norm['direct_domains'] == ['domain:\u0440\u0444']
assert norm['ipv4_domains'] == ['domain:example.com'] and norm['block_torrents'] is True
outbounds, rules = onyx_routing.xray_additions(norm)
assert [o['tag'] for o in outbounds] == ['blocked', 'ipv4'], outbounds
assert [r['outboundTag'] for r in rules] == ['blocked', 'direct', 'direct', 'ipv4'], rules
assert onyx_routing.xray_additions(onyx_routing.normalize({})) == ([], [])
routing_tmp = str(Path(tempfile.mkdtemp()) / 'routing.json')
onyx_routing.save(routing_tmp, norm)
reloaded = onyx_routing.load(routing_tmp)
assert reloaded['direct_ips'] == norm['direct_ips'] and reloaded['block_torrents'] is True
assert onyx_routing.load(routing_tmp + '.missing') == onyx_routing.normalize({})
print('ROUTING OK')

# ---- WARP: X25519 (RFC 7748 §6.1), парсер конфига, форма правил для Xray
import onyx_warp
alice_priv = bytes.fromhex('77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a')
assert onyx_warp._x25519_base(alice_priv).hex() == \
    '8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a'
priv_key, pub_key = onyx_warp.keypair()
assert onyx_warp.KEY_RE.match(priv_key) and onyx_warp.KEY_RE.match(pub_key)
assert onyx_warp._x25519_base(bytes.fromhex(base64.b64decode(priv_key).hex())).hex() == \
    base64.b64decode(pub_key).hex()          # pubkey = base * priv

warp_tmp = str(Path(tempfile.mkdtemp()) / 'warp.json')
wgconf = ('[Interface]\nPrivateKey = %s\nAddress = 172.16.0.2/32, fd01::2/128\n'
          'DNS = 1.1.1.1\n\n[Peer]\nPublicKey = %s\nAllowedIPs = 0.0.0.0/0\n'
          'Endpoint = engage.cloudflareclient.com:2408\n' % (priv_key, pub_key))
state = onyx_warp.import_config(warp_tmp, wgconf)
assert state['private_key'] == priv_key and state['address'] == '172.16.0.2'
assert state['endpoint'] == 'engage.cloudflareclient.com:2408' and state['users'] == []
for bad in ('[Interface]\nPrivateKey = short\n', '[Peer]\nPublicKey = ' + pub_key,
            '[Interface]\nPrivateKey = %s\n' % priv_key +
            '[Peer]\nPublicKey = %s\nEndpoint = bad host:port\n' % pub_key):
    try:
        onyx_warp.import_config(warp_tmp, bad); raise SystemExit('should fail')
    except onyx_warp.WarpError:
        pass

outbounds, rules = onyx_warp.xray_additions(state, ['aabbccddeeff0011'])
assert outbounds[0]['tag'] == 'warp' and outbounds[0]['protocol'] == 'wireguard'
assert outbounds[0]['settings']['peers'][0]['endpoint'] == 'engage.cloudflareclient.com:2408'
assert rules[0]['user'] == ['panel:aabbccddeeff0011'] and rules[0]['outboundTag'] == 'warp'
assert onyx_warp.xray_additions(state, []) == ([], [])
assert not onyx_warp.configured(onyx_warp.load(warp_tmp + '.missing'))

onyx_warp.set_users(warp_tmp, ['aabbccddeeff0011', '1122334455667788'], True)
assert onyx_warp.has_users(warp_tmp, ['aabbccddeeff0011'])
onyx_warp.set_users(warp_tmp, ['aabbccddeeff0011'], False)
assert not onyx_warp.has_users(warp_tmp, ['aabbccddeeff0011'])
assert onyx_warp.has_users(warp_tmp, ['1122334455667788'])
onyx_warp.reset(warp_tmp)
assert not onyx_warp.configured(onyx_warp.load(warp_tmp))
print('WARP OK')

# ---- Reality: валидация, инбаунд, ссылка
import onyx_reality
priv_r, pub_r = onyx_warp.keypair()
r_tmp = str(Path(tempfile.mkdtemp()) / 'reality.json')
state = onyx_reality.setup(r_tmp, port=2053, dest='www.wildberries.ru:443')
assert state['enabled'] is True and state['port'] == 2053
assert all(onyx_reality.SHORT_ID_RE.match(i) for i in state['short_ids']) and len(state['short_ids']) == 4
assert state['private_key'] != priv_r                     # каждый setup — новые ключи
for bad in ({'port': 80, 'dest': 'a.com:443'}, {'port': 2053, 'dest': 'no port'},
            {'port': 2053, 'dest': 'a.com:443', 'private_key': 'short', 'public_key': pub_r}):
    try:
        s2 = dict(state); s2.update(bad)
        onyx_reality.validate(s2); raise SystemExit('should fail: ' + repr(bad))
    except onyx_reality.RealityError:
        pass
users_r = [{'id': 'aabbccddeeff0011', 'secret': 'S1' * 8, 'protocol': 'vless', 'enabled': True},
           {'id': 'bbbbccccdddd0000', 'secret': 'S2' * 8, 'protocol': 'vless', 'enabled': False},
           {'id': 'ccccdddd0000eeee', 'secret': 'S3' * 8, 'protocol': 'hysteria', 'enabled': True}]
inb = onyx_reality.inbound(state, users_r)
assert inb['tag'] == 'vless-reality' and inb['port'] == 2053 and len(inb['settings']['clients']) == 1
assert inb['settings']['clients'][0]['flow'] == 'xtls-rprx-vision'
assert inb['streamSettings']['realitySettings']['dest'] == 'www.wildberries.ru:443'
assert onyx_reality.inbound(state, []) is None
disabled = dict(state, enabled=False)
assert onyx_reality.inbound(disabled, users_r) is None
link = onyx_reality.link(state, 'S1' * 8, 'Тест · Reality', host='panel.example.com')
assert 'security=reality' in link and 'flow=xtls-rprx-vision' in link
assert '@panel.example.com:2053' in link and 'sni=www.wildberries.ru' in link
from urllib.parse import urlsplit, parse_qs
query = parse_qs(urlsplit(link).query)
assert query['pbk'][0] == state['public_key'] and query['sid'][0] == state['short_ids'][0]
assert query['fp'][0] == 'chrome' and query['spx'][0] == '/'
assert onyx_reality.link(disabled, 'S1' * 8, 'x', host='h') == ''
onyx_reality.reset(r_tmp)
assert not onyx_reality.enabled(onyx_reality.load(r_tmp))
print('REALITY OK')

# ---- Python 3.10 grammar check (Ubuntu 22.04 target): no 3.12+ f-string syntax
import ast
import glob
for _path in sorted(glob.glob(os.path.join(ROOT, 'onyx_*.py'))):
    try:
        ast.parse(open(_path, encoding='utf-8').read(), feature_version=(3, 10))
    except SyntaxError as _e:
        raise SystemExit(_path + ' is not Python 3.10 compatible: ' + _e.msg + ' (line ' + str(_e.lineno) + ')')
print('PY310 GRAMMAR OK')
print('ALL MODULE TESTS PASSED')
